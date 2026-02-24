import json
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from statistics import mean
from typing import Any, Dict, Iterable, List, Optional

import jwt
from sqlalchemy import func, or_

from core.auth import ALGORITHM, SECRET_KEY
from core.config import cfg
from core.models.analytics_event import AnalyticsEvent
from core.models.user import User as DBUser
from core.models.wechat_auth import WechatAuth
from core.plan_service import get_user_plan_summary


def analytics_enabled() -> bool:
    return bool(cfg.get("analytics.enabled", True))


def _safe_text(value: Any, limit: int = 255) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text[:limit]


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _to_json_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value[:4000]
    try:
        return json.dumps(value, ensure_ascii=False)[:4000]
    except Exception:
        return _safe_text(value, 4000)


def parse_bearer_user(authorization: str) -> Dict[str, str]:
    token_text = _safe_text(authorization, 2000)
    if not token_text.lower().startswith("bearer "):
        return {}
    token = token_text[7:].strip()
    if not token:
        return {}
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except Exception:
        return {}
    return {
        "username": _safe_text(payload.get("sub"), 50),
    }


def _event_from_payload(payload: Dict[str, Any], fallback: Dict[str, Any] = None) -> Dict[str, Any]:
    source = payload if isinstance(payload, dict) else {}
    fallback_data = fallback if isinstance(fallback, dict) else {}

    metadata = source.get("metadata")
    created_at = source.get("created_at")
    created_time = datetime.now()
    if created_at:
        try:
            created_time = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
        except Exception:
            created_time = datetime.now()

    event_type = _safe_text(source.get("event_type"), 64) or "custom"
    page = _safe_text(source.get("page"), 255)
    feature = _safe_text(source.get("feature"), 120)
    action = _safe_text(source.get("action"), 120)

    return {
        "id": _safe_text(source.get("id"), 64) or uuid.uuid4().hex,
        "owner_id": _safe_text(source.get("owner_id"), 50) or _safe_text(fallback_data.get("owner_id"), 50),
        "user_id": _safe_text(source.get("user_id"), 255) or _safe_text(fallback_data.get("user_id"), 255),
        "username": _safe_text(source.get("username"), 50) or _safe_text(fallback_data.get("username"), 50),
        "session_id": _safe_text(source.get("session_id"), 120) or _safe_text(fallback_data.get("session_id"), 120),
        "event_type": event_type,
        "page": page,
        "feature": feature,
        "action": action,
        "method": _safe_text(source.get("method"), 16),
        "path": _safe_text(source.get("path"), 500),
        "status_code": _to_int(source.get("status_code"), 0),
        "duration_ms": _to_int(source.get("duration_ms"), 0),
        "input_name": _safe_text(source.get("input_name"), 120),
        "input_length": _to_int(source.get("input_length"), 0),
        "value": _safe_text(source.get("value"), 255),
        "metadata_json": _to_json_text(metadata),
        "created_at": created_time,
        "updated_at": datetime.now(),
    }


def save_event(session, payload: Dict[str, Any], fallback: Dict[str, Any] = None) -> AnalyticsEvent:
    data = _event_from_payload(payload, fallback=fallback)
    event = AnalyticsEvent(**data)
    session.add(event)
    return event


def save_events(session, payloads: Iterable[Dict[str, Any]], fallback: Dict[str, Any] = None) -> int:
    if not payloads:
        return 0
    accepted = 0
    for payload in list(payloads)[:200]:
        save_event(session, payload, fallback=fallback)
        accepted += 1
    return accepted


def build_api_event(path: str, method: str, status_code: int, duration_ms: int, user_info: Dict[str, Any], session_id: str = "") -> Dict[str, Any]:
    source_path = _safe_text(path, 500)
    feature = ""
    action = ""
    if source_path.startswith("/api/"):
        parts = [x for x in source_path.split("/") if x]
        if len(parts) >= 4:
            feature = parts[3]
        if len(parts) >= 5:
            action = parts[4]
    return {
        "event_type": "api_request",
        "page": "",
        "feature": feature,
        "action": action,
        "path": source_path,
        "method": _safe_text(method, 16),
        "status_code": int(status_code or 0),
        "duration_ms": max(0, int(duration_ms or 0)),
        "session_id": _safe_text(session_id, 120),
        "username": _safe_text((user_info or {}).get("username"), 50),
        "user_id": _safe_text((user_info or {}).get("user_id"), 255),
        "owner_id": _safe_text((user_info or {}).get("username"), 50),
    }


def _date_key(dt: datetime) -> str:
    return (dt or datetime.now()).strftime("%Y-%m-%d")


def _format_dt(value: Any) -> Optional[str]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return _safe_text(value, 64) or None


def build_analytics_summary(session, days: int = 7, limit: int = 20) -> Dict[str, Any]:
    window = max(1, min(int(days or 7), 90))
    top_n = max(5, min(int(limit or 20), 100))
    since = datetime.now() - timedelta(days=window)

    rows: List[AnalyticsEvent] = session.query(AnalyticsEvent).filter(AnalyticsEvent.created_at >= since).order_by(AnalyticsEvent.created_at.desc()).limit(50000).all()

    total_events = len(rows)
    page_views = 0
    api_requests = 0
    input_events = 0
    login_events = 0

    unique_users = set()
    duration_values = []
    page_counter = defaultdict(int)
    feature_counter = defaultdict(int)
    user_stat_map: Dict[str, Dict[str, Any]] = {}
    session_map: Dict[str, Dict[str, datetime]] = {}
    daily_map: Dict[str, Dict[str, Any]] = {}

    for row in rows:
        event_type = _safe_text(row.event_type, 64)
        username = _safe_text(row.username, 50)
        session_id = _safe_text(row.session_id, 120)
        created_at = row.created_at or datetime.now()
        day = _date_key(created_at)

        if day not in daily_map:
            daily_map[day] = {
                "date": day,
                "events": 0,
                "page_views": 0,
                "api_requests": 0,
                "inputs": 0,
                "users": set(),
            }
        daily_map[day]["events"] += 1
        if username:
            daily_map[day]["users"].add(username)

        if username:
            unique_users.add(username)
            if username not in user_stat_map:
                user_stat_map[username] = {
                    "username": username,
                    "events": 0,
                    "page_views": 0,
                    "api_requests": 0,
                    "input_events": 0,
                    "last_active": created_at,
                }
            info = user_stat_map[username]
            info["events"] += 1
            if created_at > info["last_active"]:
                info["last_active"] = created_at

        if event_type == "page_view":
            page_views += 1
            daily_map[day]["page_views"] += 1
            page_key = _safe_text(row.page, 255) or _safe_text(row.path, 500) or "(unknown)"
            page_counter[page_key] += 1
            if username:
                user_stat_map[username]["page_views"] += 1
        elif event_type == "api_request":
            api_requests += 1
            daily_map[day]["api_requests"] += 1
            duration = int(row.duration_ms or 0)
            if duration > 0:
                duration_values.append(duration)
            feature_key = _safe_text(row.feature, 120) or _safe_text(row.path, 500) or "(api)"
            if row.action:
                feature_key = f"{feature_key}:{_safe_text(row.action, 120)}"
            feature_counter[feature_key] += 1
            if username:
                user_stat_map[username]["api_requests"] += 1
        elif event_type == "input":
            input_events += 1
            daily_map[day]["inputs"] += 1
            feature_key = _safe_text(row.feature, 120) or _safe_text(row.input_name, 120) or "input"
            feature_counter[feature_key] += 1
            if username:
                user_stat_map[username]["input_events"] += 1
        elif event_type in {"login_success", "login_failed"}:
            login_events += 1

        if session_id:
            slot = session_map.get(session_id)
            if not slot:
                session_map[session_id] = {"first": created_at, "last": created_at}
            else:
                if created_at < slot["first"]:
                    slot["first"] = created_at
                if created_at > slot["last"]:
                    slot["last"] = created_at

    avg_duration_ms = round(mean(duration_values), 2) if duration_values else 0
    sorted_durations = sorted(duration_values)
    p95_duration_ms = 0
    if sorted_durations:
        idx = int(len(sorted_durations) * 0.95) - 1
        idx = max(0, min(idx, len(sorted_durations) - 1))
        p95_duration_ms = int(sorted_durations[idx])

    session_durations = []
    for session_data in session_map.values():
        seconds = (session_data["last"] - session_data["first"]).total_seconds()
        session_durations.append(max(0, int(seconds)))

    avg_session_seconds = round(mean(session_durations), 2) if session_durations else 0

    top_pages = [{"page": key, "visits": count} for key, count in sorted(page_counter.items(), key=lambda x: x[1], reverse=True)[:top_n]]
    top_features = [{"feature": key, "events": count} for key, count in sorted(feature_counter.items(), key=lambda x: x[1], reverse=True)[:top_n]]

    top_users = []
    for item in sorted(user_stat_map.values(), key=lambda x: x["events"], reverse=True)[:top_n]:
        top_users.append({
            "username": item["username"],
            "events": item["events"],
            "page_views": item["page_views"],
            "api_requests": item["api_requests"],
            "input_events": item["input_events"],
            "last_active": item["last_active"].isoformat() if item.get("last_active") else None,
        })

    trend = []
    for day in sorted(daily_map.keys()):
        row = daily_map[day]
        trend.append({
            "date": day,
            "events": row["events"],
            "page_views": row["page_views"],
            "api_requests": row["api_requests"],
            "inputs": row["inputs"],
            "users": len(row["users"]),
        })

    recent = []
    for row in rows[:top_n]:
        recent.append({
            "event_type": _safe_text(row.event_type, 64),
            "page": _safe_text(row.page, 255),
            "feature": _safe_text(row.feature, 120),
            "action": _safe_text(row.action, 120),
            "path": _safe_text(row.path, 500),
            "method": _safe_text(row.method, 16),
            "status_code": int(row.status_code or 0),
            "duration_ms": int(row.duration_ms or 0),
            "username": _safe_text(row.username, 50),
            "created_at": row.created_at.isoformat() if row.created_at else None,
        })

    registered_users_total = int(session.query(DBUser).count())
    authorized_users_total = int(
        session.query(WechatAuth.owner_id).filter(
            WechatAuth.token != None,  # noqa: E711
            WechatAuth.token != "",
            WechatAuth.cookie != None,  # noqa: E711
            WechatAuth.cookie != "",
        ).count()
    )

    return {
        "window_days": window,
        "overview": {
            "total_events": total_events,
            "page_views": page_views,
            "api_requests": api_requests,
            "input_events": input_events,
            "login_events": login_events,
            "unique_users": len(unique_users),
            "avg_api_duration_ms": avg_duration_ms,
            "p95_api_duration_ms": p95_duration_ms,
            "avg_session_seconds": avg_session_seconds,
            "registered_users_total": registered_users_total,
            "authorized_users_total": authorized_users_total,
        },
        "top_pages": top_pages,
        "top_features": top_features,
        "top_users": top_users,
        "daily_trend": trend,
        "recent_events": recent,
    }


def list_registered_user_usage(
    session,
    page: int = 1,
    page_size: int = 20,
    keyword: str = "",
) -> Dict[str, Any]:
    current = max(1, int(page or 1))
    size = max(1, min(int(page_size or 20), 200))
    kw = _safe_text(keyword, 120)

    query = session.query(DBUser)
    if kw:
        fuzzy = f"%{kw}%"
        query = query.filter(
            or_(
                DBUser.username.like(fuzzy),
                DBUser.phone.like(fuzzy),
                DBUser.nickname.like(fuzzy),
            )
        )

    total = int(query.count())
    rows: List[DBUser] = (
        query.order_by(DBUser.created_at.desc())
        .offset((current - 1) * size)
        .limit(size)
        .all()
    )

    usernames = [str(item.username or "").strip() for item in rows if str(item.username or "").strip()]
    auth_set = set()
    event_map: Dict[str, Dict[str, Any]] = {}

    if usernames:
        auth_rows = (
            session.query(WechatAuth.owner_id)
            .filter(
                WechatAuth.owner_id.in_(usernames),
                WechatAuth.token != None,  # noqa: E711
                WechatAuth.token != "",
                WechatAuth.cookie != None,  # noqa: E711
                WechatAuth.cookie != "",
            )
            .all()
        )
        auth_set = {str(row[0] or "").strip() for row in auth_rows if str(row[0] or "").strip()}

        event_rows = (
            session.query(
                AnalyticsEvent.username,
                func.max(AnalyticsEvent.created_at).label("last_active"),
                func.count(AnalyticsEvent.id).label("event_count"),
            )
            .filter(AnalyticsEvent.username.in_(usernames))
            .group_by(AnalyticsEvent.username)
            .all()
        )
        for row in event_rows:
            username = str(getattr(row, "username", "") or "").strip()
            if not username:
                continue
            event_map[username] = {
                "event_count": int(getattr(row, "event_count", 0) or 0),
                "last_active": _format_dt(getattr(row, "last_active", None)),
            }

    items = []
    for user in rows:
        summary = get_user_plan_summary(user)
        username = str(user.username or "").strip()
        ai_quota = int(summary.get("ai_quota", 0) or 0)
        ai_used = int(summary.get("ai_used", 0) or 0)
        image_quota = int(summary.get("image_quota", 0) or 0)
        image_used = int(summary.get("image_used", 0) or 0)
        ai_rate = round((ai_used / ai_quota) * 100, 2) if ai_quota > 0 else 0
        image_rate = round((image_used / image_quota) * 100, 2) if image_quota > 0 else 0
        user_events = event_map.get(username, {})

        items.append({
            "username": username,
            "phone": _safe_text(user.phone, 30),
            "nickname": _safe_text(user.nickname, 60),
            "role": _safe_text(user.role, 20),
            "is_active": bool(user.is_active),
            "plan_tier": _safe_text(summary.get("tier"), 30),
            "plan_label": _safe_text(summary.get("label"), 80),
            "ai_quota": ai_quota,
            "ai_used": ai_used,
            "ai_remaining": int(summary.get("ai_remaining", 0) or 0),
            "ai_usage_rate": ai_rate,
            "image_quota": image_quota,
            "image_used": image_used,
            "image_remaining": int(summary.get("image_remaining", 0) or 0),
            "image_usage_rate": image_rate,
            "wechat_authorized": username in auth_set,
            "event_count": int(user_events.get("event_count", 0) or 0),
            "last_active": user_events.get("last_active"),
            "created_at": _format_dt(getattr(user, "created_at", None)),
            "updated_at": _format_dt(getattr(user, "updated_at", None)),
        })

    session.commit()
    return {
        "total": total,
        "page": current,
        "page_size": size,
        "list": items,
    }
