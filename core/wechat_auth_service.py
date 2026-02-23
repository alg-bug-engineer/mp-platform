import json
import uuid
from datetime import datetime
from typing import Dict, Tuple

from core.models.wechat_auth import WechatAuth


def get_wechat_auth(session, owner_id: str) -> WechatAuth:
    user = str(owner_id or "").strip()
    if not user:
        return None
    return session.query(WechatAuth).filter(WechatAuth.owner_id == user).first()


def has_wechat_auth(session, owner_id: str) -> bool:
    item = get_wechat_auth(session, owner_id)
    if not item:
        return False
    return bool((item.token or "").strip() and (item.cookie or "").strip())


def serialize_wechat_auth(item: WechatAuth, mask: bool = True) -> Dict:
    if not item:
        return {
            "authorized": False,
            "token": "",
            "cookie": "",
            "wx_app_name": "",
            "wx_user_name": "",
            "expiry_time": "",
            "updated_at": None,
        }
    token = str(item.token or "")
    cookie = str(item.cookie or "")
    if mask:
        token = (token[:4] + "****" + token[-4:]) if len(token) >= 10 else ("*" * len(token))
        cookie = (cookie[:16] + " ...") if cookie else ""
    return {
        "authorized": bool((item.token or "").strip() and (item.cookie or "").strip()),
        "token": token,
        "cookie": cookie,
        "wx_app_name": item.wx_app_name or "",
        "wx_user_name": item.wx_user_name or "",
        "expiry_time": item.expiry_time or "",
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


def upsert_wechat_auth(
    session,
    owner_id: str,
    token: str,
    cookie: str,
    fingerprint: str = "",
    wx_app_name: str = "",
    wx_user_name: str = "",
    expiry_time: str = "",
    raw_payload: Dict = None,
) -> WechatAuth:
    now = datetime.now()
    user = str(owner_id or "").strip()
    if not user:
        raise ValueError("owner_id 不能为空")
    item = get_wechat_auth(session, user)
    if not item:
        item = WechatAuth(
            id=str(uuid.uuid4()),
            owner_id=user,
            created_at=now,
        )
        session.add(item)
    item.token = str(token or "").strip()
    item.cookie = str(cookie or "").strip()
    item.fingerprint = str(fingerprint or "").strip()
    item.wx_app_name = str(wx_app_name or "").strip()
    item.wx_user_name = str(wx_user_name or "").strip()
    item.expiry_time = str(expiry_time or "").strip()
    item.raw_json = json.dumps(raw_payload or {}, ensure_ascii=False)[:5000]
    item.updated_at = now
    session.commit()
    session.refresh(item)
    return item


def get_token_cookie(session, owner_id: str, allow_global_fallback: bool = True) -> Tuple[str, str]:
    item = get_wechat_auth(session, owner_id)
    if item and (item.token or "").strip() and (item.cookie or "").strip():
        return str(item.token or "").strip(), str(item.cookie or "").strip()
    if allow_global_fallback:
        try:
            from driver.token import wx_cfg

            token = str(wx_cfg.get("token", "")).strip()
            cookie = str(wx_cfg.get("cookie", "")).strip()
            return token, cookie
        except Exception:
            return "", ""
    return "", ""


def migrate_global_auth_to_owner(session, owner_id: str = "admin", overwrite: bool = False) -> Dict:
    """
    将历史全局 wx.lic 授权迁移到用户维度。
    默认迁移到 admin 用户。
    """
    owner = str(owner_id or "admin").strip() or "admin"
    existing = get_wechat_auth(session, owner)
    if existing and not overwrite:
        return {"migrated": False, "reason": "target_exists"}
    try:
        from driver.token import wx_cfg

        token = str(wx_cfg.get("token", "")).strip()
        cookie = str(wx_cfg.get("cookie", "")).strip()
        if not token or not cookie:
            return {"migrated": False, "reason": "global_empty"}
        ext_data = wx_cfg.get("ext_data", {}) or {}
        expiry_time = str(wx_cfg.get("expiry.expiry_time", "")).strip()
        item = upsert_wechat_auth(
            session=session,
            owner_id=owner,
            token=token,
            cookie=cookie,
            fingerprint=str(wx_cfg.get("fingerprint", "")).strip(),
            wx_app_name=str(ext_data.get("wx_app_name", "")).strip(),
            wx_user_name=str(ext_data.get("wx_user_name", "")).strip(),
            expiry_time=expiry_time,
            raw_payload={
                "source": "global_wx_lic",
                "ext_data": ext_data,
            },
        )
        return {"migrated": True, "owner_id": owner, "auth": serialize_wechat_auth(item)}
    except Exception as e:
        return {"migrated": False, "reason": f"error:{e}"}
