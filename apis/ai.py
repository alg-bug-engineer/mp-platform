from typing import List, Optional, Tuple
from datetime import datetime, timedelta
import os
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core.auth import get_current_user
from core.db import DB
from core.models.article import Article
from core.models.base import DATA_STATUS
from core.models.ai_publish_task import AIPublishTask
from core.models.ai_daily_usage import AIDailyUsage
from core.models.user import User as DBUser
from core.config import cfg
from core.ai_service import (
    get_or_create_profile,
    get_platform_profile,
    build_prompt,
    call_openai_compatible,
    recommend_tags_from_title,
    get_compose_options,
    build_image_prompts,
    build_inline_image_prompt,
    generate_images_with_jimeng,
    merge_image_urls_into_markdown,
    refine_draft,
    ensure_markdown_content,
    save_local_draft,
    list_local_drafts,
    get_local_draft,
    update_local_draft,
    delete_local_draft,
    publish_batch_to_wechat_draft,
    enqueue_publish_task,
    serialize_publish_task,
    process_pending_publish_tasks,
    process_publish_task,
    summarize_activity_metrics,
    PUBLISH_STATUS_PENDING,
    PUBLISH_STATUS_FAILED,
)
from core.prompt_templates import get_frontend_options
from core.plan_service import (
    get_user_plan_summary,
    validate_ai_action,
    consume_ai_usage,
    get_plan_catalog,
)
from core.wechat_auth_service import has_wechat_auth
from .base import success_response


router = APIRouter(prefix="/ai", tags=["AI创作"])


def _owner(current_user: dict) -> str:
    return current_user.get("username")


def _should_enqueue_publish_retry(message: str, raw: dict) -> bool:
    text = str(message or "").strip()
    payload = raw if isinstance(raw, dict) else {}
    if payload.get("missing_body_image_titles"):
        return False
    if payload.get("body_image_upload_warnings"):
        return False
    if "正文缺少插图" in text:
        return False
    if "正文图片上传异常" in text:
        return False
    return True


def _extract_first_image_url_from_text(text: str) -> str:
    source = str(text or "")
    markdown_match = re.search(r"!\[[^\]]*\]\((https?://[^)\s]+)[^)]*\)", source, flags=re.IGNORECASE)
    if markdown_match and markdown_match.group(1):
        return str(markdown_match.group(1)).strip()
    html_match = re.search(r"<img[^>]+src=[\"'](https?://[^\"']+)[\"']", source, flags=re.IGNORECASE)
    if html_match and html_match.group(1):
        return str(html_match.group(1)).strip()
    return ""


def _wechat_profile_setup_hint() -> str:
    return "请先在个人中心填写公众号 AppID 与 AppSecret（个人中心 -> 修改个人信息）后再同步"


def _resolve_wechat_openapi_credentials(user: Optional[DBUser], app_id: str, app_secret: str) -> Tuple[str, str, str]:
    req_app_id = str(app_id or "").strip()
    req_app_secret = str(app_secret or "").strip()
    if req_app_id and req_app_secret:
        return req_app_id, req_app_secret, "request"
    if req_app_id or req_app_secret:
        return "", "", "partial_request"
    if user is None:
        return "", "", "missing"
    profile_app_id = str(getattr(user, "wechat_app_id", "") or "").strip()
    profile_app_secret = str(getattr(user, "wechat_app_secret", "") or "").strip()
    if profile_app_id and profile_app_secret:
        return profile_app_id, profile_app_secret, "profile"
    return "", "", "missing"


def _serialize_plan(plan: dict) -> dict:
    data = dict(plan or {})
    reset_at = data.get("quota_reset_at")
    expire_at = data.get("plan_expires_at")
    # Safely serialize datetime fields
    try:
        data["quota_reset_at"] = reset_at.isoformat() if reset_at and hasattr(reset_at, 'isoformat') else None
    except Exception:
        data["quota_reset_at"] = None
    try:
        data["plan_expires_at"] = expire_at.isoformat() if expire_at and hasattr(expire_at, 'isoformat') else None
    except Exception:
        data["plan_expires_at"] = None
    return data


def _daily_ai_limit() -> int:
    try:
        value = int(cfg.get("ai.daily_limit", 60) or 60)
    except Exception:
        value = 60
    return max(1, value)


def _today_key(now: Optional[datetime] = None) -> str:
    target = now or datetime.now()
    return target.strftime("%Y-%m-%d")


def _get_today_usage(session, owner_id: str, now: Optional[datetime] = None) -> Optional[AIDailyUsage]:
    return session.query(AIDailyUsage).filter(
        AIDailyUsage.owner_id == owner_id,
        AIDailyUsage.usage_date == _today_key(now),
    ).first()


def _daily_usage_snapshot(session, owner_id: str, now: Optional[datetime] = None) -> dict:
    limit = _daily_ai_limit()
    usage = _get_today_usage(session, owner_id, now=now)
    used = int(getattr(usage, "used_count", 0) or 0)
    used = max(0, used)
    return {
        "limit": limit,
        "used": used,
        "remaining": max(0, limit - used),
        "date": _today_key(now),
    }


def _consume_daily_ai_usage(session, owner_id: str, amount: int = 1, now: Optional[datetime] = None) -> dict:
    amount_value = max(0, int(amount or 0))
    target = now or datetime.now()
    usage = _get_today_usage(session, owner_id, now=target)
    if usage is None:
        usage = AIDailyUsage(
            id=f"{owner_id}:{_today_key(target)}",
            owner_id=owner_id,
            usage_date=_today_key(target),
            used_count=0,
            created_at=target,
            updated_at=target,
        )
        session.add(usage)
    usage.used_count = int(getattr(usage, "used_count", 0) or 0) + amount_value
    usage.updated_at = target
    return _daily_usage_snapshot(session, owner_id, now=target)


class AIComposeRequest(BaseModel):
    instruction: str = Field(default="", max_length=4000)
    platform: str = Field(default="wechat", max_length=32)
    style: str = Field(default="专业深度", max_length=64)
    length: str = Field(default="medium", max_length=32)
    image_count: int = Field(default=0, ge=0, le=9)
    audience: str = Field(default="", max_length=200)
    tone: str = Field(default="", max_length=200)
    generate_images: bool = Field(default=True)
    force_refresh: bool = Field(default=False)


class DraftPublishItem(BaseModel):
    title: str = Field(default="", max_length=200)
    content: str = Field(default="", max_length=20000)
    digest: str = Field(default="", max_length=300)
    author: str = Field(default="", max_length=64)
    cover_url: str = Field(default="", max_length=1000)


class DraftPublishRequest(BaseModel):
    title: str = Field(default="", max_length=200)
    content: str = Field(default="", max_length=20000)
    digest: str = Field(default="", max_length=300)
    author: str = Field(default="", max_length=64)
    cover_url: str = Field(default="", max_length=1000)
    platform: str = Field(default="wechat", max_length=32)
    mode: str = Field(default="create", max_length=32)
    sync_to_wechat: bool = Field(default=True)
    queue_on_fail: bool = Field(default=True)
    max_retries: int = Field(default=3, ge=1, le=8)
    wechat_app_id: str = Field(default="", max_length=128)
    wechat_app_secret: str = Field(default="", max_length=256)
    items: List[DraftPublishItem] = Field(default_factory=list)


class PublishTaskProcessRequest(BaseModel):
    limit: int = Field(default=10, ge=1, le=100)


class TagRecommendItem(BaseModel):
    article_id: str = Field(default="")
    title: str = Field(default="", max_length=500)


class TagRecommendRequest(BaseModel):
    items: List[TagRecommendItem] = Field(default_factory=list)
    limit: int = Field(default=6, ge=1, le=20)


class DraftUpdateRequest(BaseModel):
    title: Optional[str] = Field(default=None, max_length=200)
    content: Optional[str] = Field(default=None, max_length=50000)
    platform: Optional[str] = Field(default=None, max_length=32)
    mode: Optional[str] = Field(default=None, max_length=32)


class DraftSyncRequest(BaseModel):
    title: Optional[str] = Field(default=None, max_length=200)
    content: Optional[str] = Field(default=None, max_length=50000)
    digest: str = Field(default="", max_length=300)
    author: str = Field(default="", max_length=64)
    cover_url: str = Field(default="", max_length=1000)
    platform: str = Field(default="wechat", max_length=32)
    queue_on_fail: bool = Field(default=True)
    max_retries: int = Field(default=3, ge=1, le=8)
    wechat_app_id: str = Field(default="", max_length=128)
    wechat_app_secret: str = Field(default="", max_length=256)


class InlineIllustrationRequest(BaseModel):
    selected_text: str = Field(default="", max_length=3000)
    context_text: str = Field(default="", max_length=12000)
    platform: str = Field(default="wechat", max_length=32)
    style: str = Field(default="专业深度", max_length=64)


@router.get("/profile", summary="获取AI配置（平台统一）")
async def get_profile(current_user: dict = Depends(get_current_user)):
    return success_response(get_platform_profile(mask_secret=True))


@router.put("/profile", summary="更新AI配置（禁用）")
async def put_profile(payload: dict, current_user: dict = Depends(get_current_user)):
    raise HTTPException(status_code=403, detail="平台统一提供 AI 能力，不支持用户修改 AI 配置")


@router.get("/compose/options", summary="获取创作选项")
async def compose_options(current_user: dict = Depends(get_current_user)):
    # 使用新的场景化描述
    return success_response(get_frontend_options())


@router.get("/plans", summary="获取套餐目录")
async def plan_catalog(current_user: dict = Depends(get_current_user)):
    return success_response(get_plan_catalog())


@router.get("/workbench/overview", summary="获取创作中台概览")
async def workbench_overview(current_user: dict = Depends(get_current_user)):
    session = DB.get_session()
    owner_id = _owner(current_user)
    user = session.query(DBUser).filter(DBUser.username == owner_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    plan = get_user_plan_summary(user)
    session.commit()

    from core.models.feed import Feed
    mp_count = session.query(Feed).filter(Feed.owner_id == owner_id).count()
    article_count = session.query(Article).filter(
        Article.owner_id == owner_id,
        Article.status != DATA_STATUS.DELETED,
    ).count()
    unread_count = session.query(Article).filter(
        Article.owner_id == owner_id,
        Article.status != DATA_STATUS.DELETED,
        Article.is_read != 1,
    ).count()

    wx_authorized = has_wechat_auth(session, owner_id)
    all_drafts = list_local_drafts(owner_id, limit=99999)
    daily_ai = _daily_usage_snapshot(session, owner_id)
    recent_tasks = session.query(AIPublishTask).filter(
        AIPublishTask.owner_id == owner_id,
        AIPublishTask.created_at >= (datetime.now() - timedelta(days=6)),
    ).all()
    activity = summarize_activity_metrics(all_drafts, recent_tasks, days=7)
    whitelist_raw = str(
        cfg.get("wechat.whitelist_ips", "")
        or os.getenv("WECHAT_WHITELIST_IPS", "")
    ).strip()
    whitelist_ips = [x for x in re.split(r"[,\s;]+", whitelist_raw) if str(x).strip()]
    whitelist_guide = str(
        cfg.get(
            "wechat.whitelist_guide",
            "请在微信公众平台 -> 设置与开发 -> 基本配置 -> IP 白名单 中添加平台出口 IP，再进行草稿箱同步。",
        )
    ).strip()
    whitelist_doc_url = str(
        cfg.get(
            "wechat.whitelist_doc_url",
            "https://mp.weixin.qq.com/",
        )
    ).strip()

    return success_response({
        "plan": _serialize_plan(plan),
        "plan_catalog": get_plan_catalog(),
        "stats": {
            "mp_count": mp_count,
            "article_count": article_count,
            "unread_count": unread_count,
            "local_draft_count": len(all_drafts),
            "pending_publish_count": session.query(AIPublishTask).filter(
                AIPublishTask.owner_id == owner_id,
                AIPublishTask.status.in_([PUBLISH_STATUS_PENDING, PUBLISH_STATUS_FAILED]),
            ).count(),
            "daily_ai_limit": daily_ai.get("limit", 0),
            "daily_ai_used": daily_ai.get("used", 0),
            "daily_ai_remaining": daily_ai.get("remaining", 0),
            "daily_ai_date": daily_ai.get("date", ""),
        },
        "activity": activity,
        "wechat_auth": {
            "authorized": wx_authorized,
            "hint": "如需一键投递公众号草稿箱，请先完成扫码授权",
        },
        "wechat_openapi": {
            "app_id_set": bool(str(getattr(user, "wechat_app_id", "") or "").strip()),
            "app_secret_set": bool(str(getattr(user, "wechat_app_secret", "") or "").strip()),
            "configured": bool(
                str(getattr(user, "wechat_app_id", "") or "").strip()
                and str(getattr(user, "wechat_app_secret", "") or "").strip()
            ),
            "hint": _wechat_profile_setup_hint(),
        },
        "wechat_whitelist": {
            "ips": whitelist_ips,
            "guide": whitelist_guide,
            "doc_url": whitelist_doc_url,
        },
        "recent_drafts": all_drafts[:5],
    })


@router.get("/drafts", summary="获取草稿历史")
async def get_drafts(
    limit: int = Query(20, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
):
    return success_response(list_local_drafts(_owner(current_user), limit=limit))


@router.put("/drafts/{draft_id}", summary="更新本地草稿")
async def update_draft(
    draft_id: str,
    payload: DraftUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    owner_id = _owner(current_user)
    current = get_local_draft(owner_id, draft_id)
    if not current:
        raise HTTPException(status_code=404, detail="草稿不存在")
    next_title = payload.title if payload.title is not None else str(current.get("title", ""))
    next_content = payload.content if payload.content is not None else str(current.get("content", ""))
    if not str(next_content or "").strip():
        raise HTTPException(status_code=400, detail="草稿内容不能为空")
    next_platform = payload.platform if payload.platform is not None else str(current.get("platform", "wechat"))
    next_mode = payload.mode if payload.mode is not None else str(current.get("mode", "create"))
    updated = update_local_draft(
        owner_id=owner_id,
        draft_id=draft_id,
        title=next_title,
        content=next_content,
        platform=next_platform,
        mode=next_mode,
        metadata=current.get("metadata", {}),
    )
    if not updated:
        raise HTTPException(status_code=404, detail="草稿不存在")
    return success_response(updated, message="草稿已更新")


@router.delete("/drafts/{draft_id}", summary="删除本地草稿")
async def remove_draft(
    draft_id: str,
    current_user: dict = Depends(get_current_user),
):
    ok = delete_local_draft(_owner(current_user), draft_id)
    if not ok:
        raise HTTPException(status_code=404, detail="草稿不存在")
    return success_response({"id": draft_id, "deleted": True}, message="草稿已删除")


@router.post("/drafts/{draft_id}/sync", summary="将本地草稿同步到平台")
async def sync_draft(
    draft_id: str,
    payload: DraftSyncRequest,
    current_user: dict = Depends(get_current_user),
):
    owner_id = _owner(current_user)
    session = DB.get_session()
    draft = get_local_draft(owner_id, draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="草稿不存在")

    platform = str(payload.platform or draft.get("platform") or "wechat").strip().lower()
    if platform != "wechat":
        raise HTTPException(status_code=400, detail="当前仅支持同步到微信公众号草稿箱")

    user = session.query(DBUser).filter(DBUser.username == owner_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    wechat_app_id, wechat_app_secret, source = _resolve_wechat_openapi_credentials(
        user=user,
        app_id=payload.wechat_app_id,
        app_secret=payload.wechat_app_secret,
    )
    if source == "partial_request":
        raise HTTPException(status_code=400, detail="AppID 与 AppSecret 需要同时填写")
    if not wechat_app_id or not wechat_app_secret:
        raise HTTPException(status_code=400, detail=_wechat_profile_setup_hint())
    can_sync, reason, _ = validate_ai_action(user, mode="create", publish_to_wechat=True)
    if not can_sync:
        raise HTTPException(status_code=403, detail=reason)

    metadata = draft.get("metadata", {}) if isinstance(draft.get("metadata"), dict) else {}
    item = {
        "title": (payload.title or draft.get("title") or "AI 创作草稿").strip(),
        "content": (payload.content if payload.content is not None else draft.get("content") or "").strip(),
        "digest": (payload.digest or metadata.get("digest") or "").strip(),
        "author": (payload.author or metadata.get("author") or "").strip(),
        "cover_url": (
            payload.cover_url
            or _extract_first_image_url_from_text(payload.content if payload.content is not None else draft.get("content") or "")
            or metadata.get("cover_url")
            or ""
        ).strip(),
    }
    if not item["content"]:
        raise HTTPException(status_code=400, detail="草稿内容为空，无法同步")

    synced, message, raw = publish_batch_to_wechat_draft(
        [item],
        owner_id=owner_id,
        session=session,
        wechat_app_id=wechat_app_id,
        wechat_app_secret=wechat_app_secret,
    )
    queued_task = None
    # 官方接口模式（pipeline 同款）暂不进重试队列，避免缺少密钥上下文。
    can_enqueue = False
    if (not synced) and payload.queue_on_fail and can_enqueue:
        task = enqueue_publish_task(
            session=session,
            owner_id=owner_id,
            article_id=str(draft.get("article_id") or ""),
            title=item["title"],
            content=item["content"],
            digest=item["digest"],
            author=item["author"],
            cover_url=item["cover_url"],
            platform=platform,
            max_retries=payload.max_retries,
        )
        queued_task = serialize_publish_task(task)
        message = f"{message}，已进入重试队列 1 条"
    elif (not synced) and payload.queue_on_fail and not can_enqueue:
        message = f"{message}（官方接口模式暂不支持重试队列）"
    session.commit()
    return success_response(
        {
            "wechat": {
                "requested": True,
                "synced": bool(synced),
                "message": message,
                "raw": raw,
                "queued": 1 if queued_task else 0,
            },
            "queued_task": queued_task,
        },
        message=message,
    )


@router.get("/publish/tasks", summary="获取草稿投递队列")
async def get_publish_tasks(
    status: str = Query("", max_length=32),
    limit: int = Query(30, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
):
    session = DB.get_session()
    query = session.query(AIPublishTask).filter(AIPublishTask.owner_id == _owner(current_user))
    status_text = (status or "").strip().lower()
    if status_text:
        query = query.filter(AIPublishTask.status == status_text)
    tasks = query.order_by(AIPublishTask.created_at.desc()).limit(limit).all()
    return success_response([serialize_publish_task(task) for task in tasks])


@router.post("/publish/tasks/process", summary="手动处理投递队列")
async def process_publish_tasks(
    payload: PublishTaskProcessRequest,
    current_user: dict = Depends(get_current_user),
):
    session = DB.get_session()
    result = process_pending_publish_tasks(
        session=session,
        owner_id=_owner(current_user),
        limit=payload.limit,
    )
    return success_response(result)


@router.post("/publish/tasks/{task_id}/retry", summary="手动重试指定投递任务")
async def retry_publish_task(
    task_id: str,
    current_user: dict = Depends(get_current_user),
):
    session = DB.get_session()
    task = session.query(AIPublishTask).filter(
        AIPublishTask.id == task_id,
        AIPublishTask.owner_id == _owner(current_user),
    ).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    task.status = PUBLISH_STATUS_PENDING
    task.retries = 0
    task.next_retry_at = datetime.now()
    session.commit()
    ok, message = process_publish_task(session, task)
    return success_response({
        "ok": ok,
        "message": message,
        "task": serialize_publish_task(task),
    })


@router.delete("/publish/tasks/{task_id}", summary="删除指定投递任务")
async def delete_publish_task(
    task_id: str,
    current_user: dict = Depends(get_current_user),
):
    session = DB.get_session()
    task = session.query(AIPublishTask).filter(
        AIPublishTask.id == task_id,
        AIPublishTask.owner_id == _owner(current_user),
    ).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    session.delete(task)
    session.commit()
    return success_response({"id": task_id, "deleted": True}, message="任务已删除")


@router.post("/tags/recommend", summary="推荐标签（本地规则）")
async def recommend_tags(payload: TagRecommendRequest, current_user: dict = Depends(get_current_user)):
    data = []
    for item in payload.items:
        tags = recommend_tags_from_title(item.title, limit=payload.limit)
        data.append({
            "article_id": item.article_id,
            "title": item.title,
            "tags": tags,
        })
    return success_response(data)


async def _run(mode: str, article_id: str, payload: AIComposeRequest, current_user: dict):
    session = DB.get_session()
    owner_id = _owner(current_user)
    article = session.query(Article).filter(
        Article.id == article_id,
        Article.owner_id == owner_id,
        Article.status != DATA_STATUS.DELETED,
    ).first()
    if not article:
        raise HTTPException(status_code=404, detail="文章不存在")

    user = session.query(DBUser).filter(DBUser.username == owner_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    create_options = {
        "platform": payload.platform,
        "style": payload.style,
        "length": payload.length,
        "image_count": payload.image_count,
        "audience": payload.audience,
        "tone": payload.tone,
        "generate_images": payload.generate_images,
    }
    instruction_text = (payload.instruction or "").strip()

    requested_images = payload.image_count if (mode == "create" and payload.generate_images) else 0
    ok, reason, _ = validate_ai_action(user, mode=mode, image_count=requested_images)
    if not ok:
        raise HTTPException(status_code=403, detail=reason)
    daily_usage = _daily_usage_snapshot(session, owner_id)
    if daily_usage["remaining"] <= 0:
        raise HTTPException(
            status_code=429,
            detail=f"今日 AI 调用次数已达上限（{daily_usage['limit']}次），请明天 00:00 后再试",
        )

    profile = get_or_create_profile(session, owner_id)

    system_prompt, user_prompt = build_prompt(
        mode=mode,
        title=article.title or "",
        content=article.content or article.description or "",
        instruction=instruction_text,
        create_options=create_options,
    )

    text = call_openai_compatible(profile, system_prompt, user_prompt)
    text = refine_draft(
        profile=profile,
        mode=mode,
        draft=text,
        title=article.title or "",
        create_options=create_options,
        instruction=instruction_text,
    )
    text = ensure_markdown_content(mode=mode, title=article.title or "AI 草稿", text=text)

    result = {
        "article_id": article.id,
        "mode": mode,
        "result": text,
        "recommended_tags": recommend_tags_from_title(article.title or ""),
        "options": create_options,
        "source_title": article.title or "",
    }

    if mode == "create":
        prompts = build_image_prompts(
            title=article.title or "",
            platform=payload.platform,
            style=payload.style,
            image_count=payload.image_count,
            content=text,
        )
        image_urls = []
        image_notice = ""
        if payload.generate_images and prompts:
            image_urls, image_notice = generate_images_with_jimeng(prompts)
            if image_urls:
                text = merge_image_urls_into_markdown(text, image_urls)
                result["result"] = text
        result["image_prompts"] = prompts
        result["images"] = image_urls
        result["image_notice"] = image_notice

    local_draft = save_local_draft(
        owner_id=owner_id,
        article_id=article.id,
        title=(article.title or "AI 创作草稿").strip(),
        content=result.get("result", ""),
        platform=payload.platform or "wechat",
        mode=mode,
        metadata={
            "digest": "",
            "author": "",
            "cover_url": _extract_first_image_url_from_text(result.get("result", "")),
            "instruction": instruction_text,
            "options": create_options,
        },
    )

    daily_usage = _consume_daily_ai_usage(session, owner_id, amount=1)
    consume_ai_usage(user, image_count=requested_images)
    summary = get_user_plan_summary(user)
    session.commit()
    result["plan"] = _serialize_plan(summary)
    result["daily_ai"] = daily_usage
    result["from_cache"] = False
    result["cached_at"] = ""
    result["result_id"] = ""
    result["local_draft"] = local_draft
    return success_response(result)


@router.post("/articles/{article_id}/publish-draft", summary="发布到草稿箱（本地+公众号）")
async def publish_draft(article_id: str, payload: DraftPublishRequest, current_user: dict = Depends(get_current_user)):
    session = DB.get_session()
    owner_id = _owner(current_user)

    article = session.query(Article).filter(
        Article.id == article_id,
        Article.owner_id == owner_id,
        Article.status != DATA_STATUS.DELETED,
    ).first()
    if not article:
        raise HTTPException(status_code=404, detail="文章不存在")

    user = session.query(DBUser).filter(DBUser.username == owner_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    publish_items = []
    if payload.items:
        for item in payload.items:
            content_text = (item.content or "").strip()
            if not content_text:
                continue
            publish_items.append(
                {
                    "title": (item.title or article.title or "AI 创作草稿").strip(),
                    "content": content_text,
                    "digest": item.digest or "",
                    "author": item.author or "",
                    "cover_url": (item.cover_url or _extract_first_image_url_from_text(content_text) or ""),
                }
            )
    else:
        content = (payload.content or "").strip()
        if not content:
            raise HTTPException(status_code=400, detail="发布内容不能为空")
        publish_items.append(
            {
                "title": (payload.title or article.title or "AI 创作草稿").strip(),
                "content": content,
                "digest": payload.digest or "",
                "author": payload.author or "",
                "cover_url": (payload.cover_url or _extract_first_image_url_from_text(content) or ""),
            }
        )

    local_records = []
    for item in publish_items:
        local_records.append(
            save_local_draft(
                owner_id=owner_id,
                article_id=article.id,
                title=item["title"],
                content=item["content"],
                platform=payload.platform or "wechat",
                mode=payload.mode or "create",
                metadata={
                    "digest": item["digest"],
                    "author": item["author"],
                    "cover_url": item["cover_url"],
                },
            )
        )

    queued_tasks = []
    wechat_result = {
        "requested": bool(payload.sync_to_wechat),
        "synced": False,
        "message": "仅保存到本地草稿箱",
        "raw": {},
        "queued": 0,
    }

    if payload.sync_to_wechat:
        wechat_app_id, wechat_app_secret, source = _resolve_wechat_openapi_credentials(
            user=user,
            app_id=payload.wechat_app_id,
            app_secret=payload.wechat_app_secret,
        )
        if source == "partial_request":
            wechat_result["message"] = "已保存本地草稿，公众号同步未执行：AppID 与 AppSecret 需要同时填写"
        elif not wechat_app_id or not wechat_app_secret:
            wechat_result["message"] = f"已保存本地草稿，公众号同步未执行：{_wechat_profile_setup_hint()}"
        else:
            ok, reason, _ = validate_ai_action(user, mode="create", publish_to_wechat=True)
            if not ok:
                wechat_result["message"] = f"已保存本地草稿，公众号同步未执行：{reason}"
            else:
                synced, message, raw = publish_batch_to_wechat_draft(
                    publish_items,
                    owner_id=owner_id,
                    session=session,
                    wechat_app_id=wechat_app_id,
                    wechat_app_secret=wechat_app_secret,
                )
                wechat_result = {
                    "requested": True,
                    "synced": bool(synced),
                    "message": message,
                    "raw": raw,
                    "queued": 0,
                }
                # 官方接口模式（pipeline 同款）暂不进重试队列，避免缺少密钥上下文。
                can_enqueue = False
                if not synced and payload.queue_on_fail and can_enqueue:
                    for item in publish_items:
                        task = enqueue_publish_task(
                            session=session,
                            owner_id=owner_id,
                            article_id=article.id,
                            title=item["title"],
                            content=item["content"],
                            digest=item["digest"],
                            author=item["author"],
                            cover_url=item["cover_url"],
                            platform=payload.platform or "wechat",
                            max_retries=payload.max_retries,
                        )
                        queued_tasks.append(serialize_publish_task(task))
                    wechat_result["queued"] = len(queued_tasks)
                    wechat_result["message"] = (
                        f'{message}，已进入重试队列 {len(queued_tasks)} 条'
                        if queued_tasks else message
                    )
                elif not synced and payload.queue_on_fail and not can_enqueue:
                    wechat_result["message"] = f"{message}（官方接口模式暂不支持重试队列）"

    plan = get_user_plan_summary(user)
    session.commit()

    return success_response({
        "local_draft": local_records[0] if len(local_records) == 1 else local_records,
        "local_drafts": local_records,
        "wechat": wechat_result,
        "queued_tasks": queued_tasks,
        "plan": _serialize_plan(plan),
    })


@router.post("/articles/{article_id}/analyze", summary="一键分析")
async def analyze(article_id: str, payload: AIComposeRequest, current_user: dict = Depends(get_current_user)):
    return await _run("analyze", article_id, payload, current_user)


@router.post("/articles/{article_id}/create", summary="一键创作")
async def create(article_id: str, payload: AIComposeRequest, current_user: dict = Depends(get_current_user)):
    return await _run("create", article_id, payload, current_user)


@router.post("/articles/{article_id}/rewrite", summary="一键仿写")
async def rewrite(article_id: str, payload: AIComposeRequest, current_user: dict = Depends(get_current_user)):
    return await _run("rewrite", article_id, payload, current_user)


@router.post("/articles/{article_id}/illustrate", summary="根据选中文本生成内容配图")
async def illustrate(
    article_id: str,
    payload: InlineIllustrationRequest,
    current_user: dict = Depends(get_current_user),
):
    session = DB.get_session()
    owner_id = _owner(current_user)
    article = session.query(Article).filter(
        Article.id == article_id,
        Article.owner_id == owner_id,
        Article.status != DATA_STATUS.DELETED,
    ).first()
    if not article:
        raise HTTPException(status_code=404, detail="文章不存在")

    user = session.query(DBUser).filter(DBUser.username == owner_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    selected_text = str(payload.selected_text or "").strip()
    if len(selected_text) < 6:
        raise HTTPException(status_code=400, detail="请先选中一段内容后再生成配图")

    ok, reason, _ = validate_ai_action(user, mode="create", image_count=1)
    if not ok:
        raise HTTPException(status_code=403, detail=reason)
    daily_usage = _daily_usage_snapshot(session, owner_id)
    if daily_usage["remaining"] <= 0:
        raise HTTPException(
            status_code=429,
            detail=f"今日 AI 调用次数已达上限（{daily_usage['limit']}次），请明天 00:00 后再试",
        )

    prompt = build_inline_image_prompt(
        title=article.title or "",
        selected_text=selected_text,
        platform=payload.platform,
        style=payload.style,
        context_text=(payload.context_text or "")[:1200],
    )
    image_urls, image_notice = generate_images_with_jimeng([prompt])

    next_daily_usage = _consume_daily_ai_usage(session, owner_id, amount=1)
    consume_ai_usage(user, image_count=1)
    plan = get_user_plan_summary(user)
    session.commit()

    return success_response(
        {
            "article_id": article.id,
            "selected_text": selected_text,
            "prompt": prompt,
            "image_url": image_urls[0] if image_urls else "",
            "images": image_urls,
            "image_notice": image_notice,
            "plan": _serialize_plan(plan),
            "daily_ai": next_daily_usage,
        },
        message="已生成内容配图" if image_urls else "配图生成未返回图片，已提供提示词",
    )
