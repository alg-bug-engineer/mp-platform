import json
import threading
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.ai_service import (
    build_image_prompts,
    build_prompt,
    call_openai_compatible,
    extract_first_image_url_from_text,
    generate_images_with_jimeng,
    get_or_create_profile,
    merge_image_urls_into_markdown,
    recommend_tags_from_title,
    refine_draft,
    save_local_draft,
)
from core.config import cfg
from core.db import DB
from core.log import logger
from core.models.ai_compose_task import AIComposeTask
from core.models.ai_daily_usage import AIDailyUsage
from core.models.article import Article
from core.models.base import DATA_STATUS
from core.models.user import User as DBUser
from core.plan_service import consume_ai_usage, get_user_plan_summary, validate_ai_action

COMPOSE_TASK_STATUS_PENDING = "pending"
COMPOSE_TASK_STATUS_PROCESSING = "processing"
COMPOSE_TASK_STATUS_SUCCESS = "success"
COMPOSE_TASK_STATUS_FAILED = "failed"
COMPOSE_TASK_STATUS_TERMINAL = {
    COMPOSE_TASK_STATUS_SUCCESS,
    COMPOSE_TASK_STATUS_FAILED,
}

_WORKER_LOCK = threading.Lock()
_WORKER_STARTED = False
_WORKER_THREADS: List[threading.Thread] = []
_DRAFT_WRITE_LOCK = threading.Lock()


class ComposeTaskError(Exception):
    pass


def _daily_ai_limit() -> int:
    try:
        value = int(cfg.get("ai.daily_limit", 60) or 60)
    except Exception:
        value = 60
    return max(1, value)


def _safe_int(value: Any, default: int, min_value: int = 1, max_value: int = 9999) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    return max(min_value, min(max_value, parsed))


def _safe_float(value: Any, default: float, min_value: float = 0.1, max_value: float = 60.0) -> float:
    try:
        parsed = float(value)
    except Exception:
        parsed = default
    return max(min_value, min(max_value, parsed))


def _today_key(now: Optional[datetime] = None) -> str:
    target = now or datetime.now()
    return target.strftime("%Y-%m-%d")


def _get_today_usage(session, owner_id: str, now: Optional[datetime] = None) -> Optional[AIDailyUsage]:
    return session.query(AIDailyUsage).filter(
        AIDailyUsage.owner_id == owner_id,
        AIDailyUsage.usage_date == _today_key(now),
    ).first()


def _daily_usage_snapshot(session, owner_id: str, now: Optional[datetime] = None) -> Dict[str, Any]:
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


def _consume_daily_ai_usage(session, owner_id: str, amount: int = 1, now: Optional[datetime] = None) -> Dict[str, Any]:
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


def _serialize_plan(plan: Dict[str, Any]) -> Dict[str, Any]:
    data = dict(plan or {})
    reset_at = data.get("quota_reset_at")
    expire_at = data.get("plan_expires_at")
    try:
        data["quota_reset_at"] = reset_at.isoformat() if reset_at and hasattr(reset_at, "isoformat") else None
    except Exception:
        data["quota_reset_at"] = None
    try:
        data["plan_expires_at"] = expire_at.isoformat() if expire_at and hasattr(expire_at, "isoformat") else None
    except Exception:
        data["plan_expires_at"] = None
    return data


def _parse_json(text: Any) -> Dict[str, Any]:
    try:
        payload = json.loads(str(text or "{}"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _build_create_options(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "platform": str(payload.get("platform", "wechat") or "wechat").strip().lower(),
        "style": str(payload.get("style", "专业深度") or "专业深度").strip(),
        "length": str(payload.get("length", "medium") or "medium").strip().lower(),
        "image_count": max(0, min(9, int(payload.get("image_count", 2) or 2))),
        "audience": str(payload.get("audience", "") or "").strip(),
        "tone": str(payload.get("tone", "") or "").strip(),
        "generate_images": bool(payload.get("generate_images", True)),
    }


def serialize_compose_task(task: AIComposeTask, include_result: bool = False) -> Dict[str, Any]:
    data = {
        "id": task.id,
        "owner_id": task.owner_id,
        "article_id": task.article_id,
        "mode": task.mode,
        "status": task.status,
        "status_message": task.status_message or "",
        "error_message": task.error_message or "",
        "request_payload": _parse_json(task.request_payload),
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "finished_at": task.finished_at.isoformat() if task.finished_at else None,
    }
    if include_result:
        data["result_payload"] = _parse_json(task.result_json)
    return data


def enqueue_compose_task(
    session,
    owner_id: str,
    article_id: str,
    mode: str,
    request_payload: Dict[str, Any],
) -> AIComposeTask:
    now = datetime.now()
    task = AIComposeTask(
        id=str(uuid.uuid4()),
        owner_id=str(owner_id or "").strip(),
        article_id=str(article_id or "").strip(),
        mode=str(mode or "").strip().lower(),
        request_payload=json.dumps(request_payload or {}, ensure_ascii=False),
        status=COMPOSE_TASK_STATUS_PENDING,
        status_message="任务已进入队列",
        created_at=now,
        updated_at=now,
        started_at=None,
        finished_at=None,
    )
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


def count_compose_tasks(
    session,
    owner_id: str = "",
    statuses: Optional[Sequence[str]] = None,
) -> int:
    query = session.query(AIComposeTask)
    owner = str(owner_id or "").strip()
    if owner:
        query = query.filter(AIComposeTask.owner_id == owner)
    status_list = [str(x or "").strip().lower() for x in (statuses or []) if str(x or "").strip()]
    if status_list:
        query = query.filter(AIComposeTask.status.in_(status_list))
    return int(query.count() or 0)


def list_compose_tasks(
    session,
    owner_id: str,
    statuses: Optional[Sequence[str]] = None,
    limit: int = 30,
) -> List[AIComposeTask]:
    query = session.query(AIComposeTask).filter(AIComposeTask.owner_id == str(owner_id or "").strip())
    status_list = [str(x or "").strip().lower() for x in (statuses or []) if str(x or "").strip()]
    if status_list:
        query = query.filter(AIComposeTask.status.in_(status_list))
    return query.order_by(AIComposeTask.created_at.desc()).limit(max(1, int(limit or 30))).all()


def _mark_task_processing(session, task: AIComposeTask, now: datetime) -> bool:
    try:
        affected = session.query(AIComposeTask).filter(
            AIComposeTask.id == task.id,
            AIComposeTask.status == COMPOSE_TASK_STATUS_PENDING,
        ).update(
            {
                AIComposeTask.status: COMPOSE_TASK_STATUS_PROCESSING,
                AIComposeTask.status_message: "任务处理中",
                AIComposeTask.started_at: now,
                AIComposeTask.updated_at: now,
            },
            synchronize_session=False,
        )
        session.commit()
        if int(affected or 0) <= 0:
            return False
        session.refresh(task)
        return True
    except Exception:
        session.rollback()
        return False


def _run_compose_pipeline(session, task: AIComposeTask) -> Dict[str, Any]:
    owner_id = str(task.owner_id or "").strip()
    article_id = str(task.article_id or "").strip()
    mode = str(task.mode or "").strip().lower()
    payload = _parse_json(task.request_payload)

    article = session.query(Article).filter(
        Article.id == article_id,
        Article.owner_id == owner_id,
        Article.status != DATA_STATUS.DELETED,
    ).first()
    if not article:
        raise ComposeTaskError("文章不存在")

    user = session.query(DBUser).filter(DBUser.username == owner_id).first()
    if not user:
        raise ComposeTaskError("用户不存在")

    create_options = _build_create_options(payload)
    instruction_text = str(payload.get("instruction", "") or "").strip()
    requested_images = create_options["image_count"] if (mode == "create" and create_options["generate_images"]) else 0

    ok, reason, _ = validate_ai_action(user, mode=mode, image_count=requested_images)
    if not ok:
        raise ComposeTaskError(reason)

    daily_usage = _daily_usage_snapshot(session, owner_id)
    if daily_usage["remaining"] <= 0:
        raise ComposeTaskError(f"今日 AI 调用次数已达上限（{daily_usage['limit']}次），请明天 00:00 后再试")

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
            platform=create_options["platform"],
            style=create_options["style"],
            image_count=create_options["image_count"],
            content=text,
        )
        image_urls: List[str] = []
        image_notice = ""
        if create_options["generate_images"] and prompts:
            image_urls, image_notice = generate_images_with_jimeng(prompts)
            if image_urls:
                text = merge_image_urls_into_markdown(text, image_urls)
                result["result"] = text
        result["image_prompts"] = prompts
        result["images"] = image_urls
        result["image_notice"] = image_notice

    with _DRAFT_WRITE_LOCK:
        local_draft = save_local_draft(
            owner_id=owner_id,
            article_id=article.id,
            title=(article.title or "AI 创作草稿").strip(),
            content=result.get("result", ""),
            platform=create_options["platform"],
            mode=mode,
            metadata={
                "digest": "",
                "author": "",
                "cover_url": extract_first_image_url_from_text(result.get("result", "")),
                "instruction": instruction_text,
                "options": create_options,
            },
        )

    next_daily_usage = _consume_daily_ai_usage(session, owner_id, amount=1)
    consume_ai_usage(user, image_count=requested_images)
    summary = get_user_plan_summary(user)
    result["plan"] = _serialize_plan(summary)
    result["daily_ai"] = next_daily_usage
    result["from_cache"] = False
    result["cached_at"] = ""
    result["result_id"] = ""
    result["local_draft"] = local_draft
    return result


def process_compose_task(session, task: AIComposeTask) -> Tuple[bool, str]:
    now = datetime.now()
    if str(task.status or "").strip().lower() in COMPOSE_TASK_STATUS_TERMINAL:
        return task.status == COMPOSE_TASK_STATUS_SUCCESS, "任务已处理"
    if not _mark_task_processing(session, task, now):
        return False, "任务状态已变更"

    try:
        result = _run_compose_pipeline(session, task)
        task.status = COMPOSE_TASK_STATUS_SUCCESS
        task.status_message = "任务完成"
        task.error_message = ""
        task.result_json = json.dumps(result, ensure_ascii=False)
        task.updated_at = datetime.now()
        task.finished_at = task.updated_at
        session.commit()
        return True, "任务完成"
    except ComposeTaskError as e:
        session.rollback()
        message = str(e or "任务失败").strip() or "任务失败"
    except Exception as e:
        session.rollback()
        logger.exception("处理 AI 创作任务失败 task_id=%s", str(task.id or ""))
        message = f"系统异常: {str(e)}"

    fail_row = session.query(AIComposeTask).filter(AIComposeTask.id == task.id).first()
    if fail_row:
        fail_row.status = COMPOSE_TASK_STATUS_FAILED
        fail_row.status_message = "任务失败"
        fail_row.error_message = message[:2000]
        fail_row.updated_at = datetime.now()
        fail_row.finished_at = fail_row.updated_at
        session.commit()
    return False, message


def process_pending_compose_tasks(session, owner_id: str = "", limit: int = 10) -> Dict[str, Any]:
    query = session.query(AIComposeTask).filter(AIComposeTask.status == COMPOSE_TASK_STATUS_PENDING)
    owner = str(owner_id or "").strip()
    if owner:
        query = query.filter(AIComposeTask.owner_id == owner)
    tasks = query.order_by(AIComposeTask.created_at.asc()).limit(max(1, int(limit or 10))).all()
    details = []
    success = 0
    failed = 0
    for task in tasks:
        ok, message = process_compose_task(session, task)
        if ok:
            success += 1
        else:
            failed += 1
        details.append(
            {
                "id": task.id,
                "status": task.status,
                "message": message,
            }
        )
    return {
        "total": len(tasks),
        "success": success,
        "failed": failed,
        "details": details,
    }


def _worker_loop(worker_index: int) -> None:
    idle_sleep = _safe_float(cfg.get("ai.compose_queue_idle_sleep_seconds", 1.0), default=1.0, min_value=0.2, max_value=10.0)
    batch_size = _safe_int(cfg.get("ai.compose_queue_batch_size", 3), default=3, min_value=1, max_value=20)
    while True:
        handled = 0
        session = None
        try:
            session = DB.get_session()
            result = process_pending_compose_tasks(session=session, owner_id="", limit=batch_size)
            handled = int(result.get("total", 0) or 0)
        except Exception:
            logger.exception("AI 创作队列 worker 异常 worker=%s", worker_index)
        finally:
            if session is not None and hasattr(session, "close"):
                try:
                    session.close()
                except Exception:
                    pass
        if handled <= 0:
            time.sleep(idle_sleep)


def start_compose_queue_workers() -> int:
    global _WORKER_STARTED
    with _WORKER_LOCK:
        if _WORKER_STARTED:
            return len(_WORKER_THREADS)
        worker_count = _safe_int(cfg.get("ai.compose_queue_workers", 3), default=3, min_value=1, max_value=8)
        for idx in range(worker_count):
            t = threading.Thread(
                target=_worker_loop,
                args=(idx + 1,),
                daemon=True,
                name=f"ai-compose-worker-{idx + 1}",
            )
            t.start()
            _WORKER_THREADS.append(t)
        _WORKER_STARTED = True
        logger.info("AI 创作队列 worker 已启动: %s", worker_count)
        return len(_WORKER_THREADS)
