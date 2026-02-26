"""
core/csdn_auth_service.py

管理用户 CSDN 的 Playwright storage_state（含 cookies + localStorage）。
对标 core/wechat_auth_service.py，用于替代 cookie-based 登录。
"""
import json
import uuid
from datetime import datetime
from typing import Dict, Optional

from core.models.csdn_auth import CsdnAuth


def get_csdn_auth(session, owner_id: str) -> Optional[CsdnAuth]:
    user = str(owner_id or "").strip()
    if not user:
        return None
    return session.query(CsdnAuth).filter(CsdnAuth.owner_id == user).first()


def upsert_csdn_auth(
    session,
    owner_id: str,
    storage_state: dict,
    csdn_username: str = "",
    status: str = "valid",
) -> CsdnAuth:
    now = datetime.now()
    user = str(owner_id or "").strip()
    if not user:
        raise ValueError("owner_id 不能为空")
    item = get_csdn_auth(session, user)
    if not item:
        item = CsdnAuth(
            id=str(uuid.uuid4()),
            owner_id=user,
            created_at=now,
        )
        session.add(item)
    item.storage_state = json.dumps(storage_state or {}, ensure_ascii=False)
    item.status = str(status or "valid")
    item.csdn_username = str(csdn_username or "").strip()
    item.updated_at = now
    session.commit()
    session.refresh(item)
    return item


def mark_csdn_auth_expired(session, owner_id: str) -> None:
    item = get_csdn_auth(session, owner_id)
    if item:
        item.status = "expired"
        item.updated_at = datetime.now()
        session.commit()


def get_storage_state(session, owner_id: str) -> Optional[dict]:
    """返回有效的 storage_state dict，若不存在或已过期则返回 None。"""
    item = get_csdn_auth(session, owner_id)
    if not item or item.status != "valid":
        return None
    raw = str(item.storage_state or "").strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def serialize_csdn_auth(item: Optional[CsdnAuth]) -> Dict:
    if not item:
        return {
            "authorized": False,
            "status": "expired",
            "csdn_username": "",
            "updated_at": None,
        }
    return {
        "authorized": item.status == "valid" and bool((item.storage_state or "").strip()),
        "status": item.status or "expired",
        "csdn_username": item.csdn_username or "",
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }
