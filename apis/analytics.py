from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from core.auth import get_current_user
from core.db import DB
from core.analytics_service import (
    analytics_enabled,
    build_analytics_summary,
    list_registered_user_usage,
    parse_bearer_user,
    save_event,
    save_events,
)
from core.product_mode import (
    PRODUCT_MODE_ALL_FREE,
    PRODUCT_MODE_COMMERCIAL,
    get_runtime_flags,
    set_product_mode,
)
from .base import success_response


router = APIRouter(prefix="/analytics", tags=["运营分析"])


class EventItem(BaseModel):
    event_type: str = Field(default="custom", max_length=64)
    page: str = Field(default="", max_length=255)
    feature: str = Field(default="", max_length=120)
    action: str = Field(default="", max_length=120)
    method: str = Field(default="", max_length=16)
    path: str = Field(default="", max_length=500)
    status_code: int = Field(default=0)
    duration_ms: int = Field(default=0)
    input_name: str = Field(default="", max_length=120)
    input_length: int = Field(default=0)
    value: str = Field(default="", max_length=255)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    session_id: str = Field(default="", max_length=120)
    created_at: Optional[str] = Field(default=None)


class EventBatchRequest(BaseModel):
    events: List[EventItem] = Field(default_factory=list)


class RuntimeModeUpdate(BaseModel):
    mode: str = Field(default=PRODUCT_MODE_ALL_FREE, max_length=32)


def _require_admin(current_user: dict):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权限执行")


@router.post("/events", summary="写入前端埋点事件")
async def collect_events(payload: EventBatchRequest, request: Request):
    if not analytics_enabled():
        return success_response({"accepted": 0}, message="埋点已关闭")

    session = DB.get_session()
    try:
        auth_user = parse_bearer_user(request.headers.get("Authorization", ""))
        session_id = str(request.headers.get("X-Session-Id", "") or "").strip()[:120]
        fallback = {
            "username": auth_user.get("username", ""),
            "owner_id": auth_user.get("username", ""),
            "session_id": session_id,
        }
        accepted = save_events(session, [event.model_dump() for event in payload.events], fallback=fallback)
        session.commit()
        return success_response({"accepted": accepted})
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=400, detail=f"写入埋点失败: {e}")
    finally:
        session.close()


@router.get("/summary", summary="获取运营统计汇总")
async def analytics_summary(
    days: int = Query(7, ge=1, le=90),
    limit: int = Query(20, ge=5, le=100),
    current_user: dict = Depends(get_current_user),
):
    _require_admin(current_user)
    if not analytics_enabled():
        return success_response({"window_days": days, "overview": {}, "top_pages": [], "top_features": [], "top_users": [], "daily_trend": [], "recent_events": []})

    session = DB.get_session()
    try:
        data = build_analytics_summary(session, days=days, limit=limit)
        data["runtime"] = {
            **get_runtime_flags(),
            "analytics_enabled": True,
            "updated_at": datetime.now().isoformat(),
        }
        return success_response(data)
    finally:
        session.close()


@router.get("/users", summary="获取注册用户使用情况（全量分页）")
async def analytics_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    keyword: str = Query("", max_length=120),
    current_user: dict = Depends(get_current_user),
):
    _require_admin(current_user)
    session = DB.get_session()
    try:
        data = list_registered_user_usage(
            session=session,
            page=page,
            page_size=page_size,
            keyword=keyword,
        )
        return success_response(data)
    finally:
        session.close()


@router.get("/runtime", summary="获取运营模式")
async def get_runtime_settings(current_user: dict = Depends(get_current_user)):
    return success_response({
        **get_runtime_flags(),
        "analytics_enabled": analytics_enabled(),
    })


@router.put("/runtime", summary="更新运营模式")
async def update_runtime_settings(payload: RuntimeModeUpdate, current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    next_mode = set_product_mode(payload.mode)
    return success_response({
        **get_runtime_flags(),
        "analytics_enabled": analytics_enabled(),
        "mode": next_mode,
        "mode_options": [PRODUCT_MODE_ALL_FREE, PRODUCT_MODE_COMMERCIAL],
    }, message="运营模式已更新")


@router.post("/event", summary="写入单条埋点")
async def collect_event(payload: EventItem, request: Request):
    if not analytics_enabled():
        return success_response({"accepted": 0}, message="埋点已关闭")

    session = DB.get_session()
    try:
        auth_user = parse_bearer_user(request.headers.get("Authorization", ""))
        session_id = str(request.headers.get("X-Session-Id", "") or "").strip()[:120]
        fallback = {
            "username": auth_user.get("username", ""),
            "owner_id": auth_user.get("username", ""),
            "session_id": session_id,
        }
        save_event(session, payload.model_dump(), fallback=fallback)
        session.commit()
        return success_response({"accepted": 1})
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=400, detail=f"写入埋点失败: {e}")
    finally:
        session.close()
