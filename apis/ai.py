from typing import List, Optional
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
from core.models.user import User as DBUser
from core.config import cfg
from core.ai_service import (
    get_or_create_profile,
    update_profile,
    profile_to_dict,
    build_prompt,
    call_openai_compatible,
    recommend_tags_from_title,
    get_compose_options,
    build_image_prompts,
    generate_images_with_jimeng,
    merge_image_urls_into_markdown,
    refine_draft,
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


def _serialize_plan(plan: dict) -> dict:
    data = dict(plan or {})
    reset_at = data.get("quota_reset_at")
    expire_at = data.get("plan_expires_at")
    data["quota_reset_at"] = reset_at.isoformat() if reset_at else None
    data["plan_expires_at"] = expire_at.isoformat() if expire_at else None
    return data


class AIProfileUpsert(BaseModel):
    base_url: str = Field(default="https://api.moonshot.cn/v1")
    api_key: str = Field(default="")
    model_name: str = Field(default="kimi-k2-0711-preview")
    temperature: int = Field(default=70, ge=0, le=100)


class AIComposeRequest(BaseModel):
    instruction: str = Field(default="", max_length=4000)
    platform: str = Field(default="wechat", max_length=32)
    style: str = Field(default="专业深度", max_length=64)
    length: str = Field(default="medium", max_length=32)
    image_count: int = Field(default=0, ge=0, le=9)
    audience: str = Field(default="", max_length=200)
    tone: str = Field(default="", max_length=200)
    generate_images: bool = Field(default=True)


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


@router.get("/profile", summary="获取AI配置")
async def get_profile(current_user: dict = Depends(get_current_user)):
    session = DB.get_session()
    profile = get_or_create_profile(session, _owner(current_user))
    return success_response(profile_to_dict(profile, include_secret=False))


@router.put("/profile", summary="更新AI配置")
async def put_profile(payload: AIProfileUpsert, current_user: dict = Depends(get_current_user)):
    session = DB.get_session()
    profile = update_profile(
        session=session,
        owner_id=_owner(current_user),
        base_url=payload.base_url,
        api_key=payload.api_key,
        model_name=payload.model_name,
        temperature=payload.temperature,
    )
    return success_response(profile_to_dict(profile, include_secret=False), message="AI配置已更新")


@router.get("/compose/options", summary="获取创作选项")
async def compose_options(current_user: dict = Depends(get_current_user)):
    return success_response(get_compose_options())


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
        },
        "activity": activity,
        "wechat_auth": {
            "authorized": wx_authorized,
            "hint": "如需一键投递公众号草稿箱，请先完成扫码授权",
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
            or metadata.get("cover_url")
            or _extract_first_image_url_from_text(payload.content if payload.content is not None else draft.get("content") or "")
            or ""
        ).strip(),
    }
    if not item["content"]:
        raise HTTPException(status_code=400, detail="草稿内容为空，无法同步")

    synced, message, raw = publish_batch_to_wechat_draft(
        [item],
        owner_id=owner_id,
        session=session,
    )
    queued_task = None
    can_enqueue = _should_enqueue_publish_retry(message, raw)
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
        message = f"{message}（该错误类型不会进入重试队列）"
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

    requested_images = payload.image_count if (mode == "create" and payload.generate_images) else 0
    ok, reason, _ = validate_ai_action(user, mode=mode, image_count=requested_images)
    if not ok:
        raise HTTPException(status_code=403, detail=reason)

    profile = get_or_create_profile(session, owner_id)
    create_options = {
        "platform": payload.platform,
        "style": payload.style,
        "length": payload.length,
        "image_count": payload.image_count,
        "audience": payload.audience,
        "tone": payload.tone,
    }

    system_prompt, user_prompt = build_prompt(
        mode=mode,
        title=article.title or "",
        content=article.content or article.description or "",
        instruction=(payload.instruction or "").strip(),
        create_options=create_options,
    )

    text = call_openai_compatible(profile, system_prompt, user_prompt)
    text = refine_draft(
        profile=profile,
        mode=mode,
        draft=text,
        title=article.title or "",
        create_options=create_options,
        instruction=(payload.instruction or "").strip(),
    )

    result = {
        "article_id": article.id,
        "mode": mode,
        "result": text,
        "recommended_tags": recommend_tags_from_title(article.title or ""),
        "options": create_options,
    }

    if mode == "create":
        prompts = build_image_prompts(
            title=article.title or "",
            platform=payload.platform,
            style=payload.style,
            image_count=payload.image_count,
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

    consume_ai_usage(user, image_count=requested_images)
    summary = get_user_plan_summary(user)
    session.commit()
    result["plan"] = _serialize_plan(summary)
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
        ok, reason, _ = validate_ai_action(user, mode="create", publish_to_wechat=True)
        if not ok:
            wechat_result["message"] = f"已保存本地草稿，公众号同步未执行：{reason}"
        else:
            synced, message, raw = publish_batch_to_wechat_draft(
                publish_items,
                owner_id=owner_id,
                session=session,
            )
            wechat_result = {
                "requested": True,
                "synced": bool(synced),
                "message": message,
                "raw": raw,
                "queued": 0,
            }
            can_enqueue = _should_enqueue_publish_retry(message, raw)
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
                wechat_result["message"] = f"{message}（该错误类型不会进入重试队列）"

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
