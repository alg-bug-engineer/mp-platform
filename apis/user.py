from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Query
from core.auth import get_current_user
from core.db import DB
from core.models import User as DBUser
from core.auth import pwd_context
import os
import uuid
import json
from datetime import datetime
from sqlalchemy import func, or_
from core.plan_service import (
    get_user_plan_summary,
    get_plan_catalog,
    normalize_plan_tier,
    get_plan_definition,
)
from core.wechat_auth_service import serialize_wechat_auth, get_wechat_auth
from .base import success_response, error_response
router = APIRouter(prefix="/user", tags=["用户管理"])


def _require_admin(current_user: dict):
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=error_response(
                code=40301,
                message="无权限执行此操作"
            )
        )

@router.get("", summary="获取用户信息")
async def get_user_info(current_user: dict = Depends(get_current_user)):
    session = DB.get_session()
    try:
        user = session.query(DBUser).filter(
            DBUser.username == current_user["username"]
        ).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response(
                    code=40401,
                    message="用户不存在"
                )
            )
        plan = get_user_plan_summary(user)
        session.commit()
        return success_response({
            "username": user.username,
            "phone": user.phone or "",
            "nickname": user.nickname if user.nickname else user.username,
            "avatar": user.avatar if user.avatar else "/static/default-avatar.png",
            "email": user.email if user.email else "",
            "wechat_app_id": str(getattr(user, "wechat_app_id", "") or ""),
            "wechat_app_secret_set": bool(str(getattr(user, "wechat_app_secret", "") or "").strip()),
            "role": user.role,
            "is_active": user.is_active,
            "plan": {
                **plan,
                "quota_reset_at": plan["quota_reset_at"].isoformat() if plan.get("quota_reset_at") else None,
                "plan_expires_at": plan["plan_expires_at"].isoformat() if plan.get("plan_expires_at") else None,
            },
        })
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_201_CREATED,
            detail=error_response(
                code=50001,
                message="获取用户信息失败"
            )
        )

@router.get("/list", summary="获取用户列表")
async def get_user_list(
    current_user: dict = Depends(get_current_user),
    page: int = 1,
    page_size: int = 10,
    keyword: str = Query("", max_length=120),
):
    """获取所有用户列表（仅管理员可用）"""
    session = DB.get_session()
    try:
        _require_admin(current_user)

        query = session.query(DBUser)
        kw = str(keyword or "").strip()
        if kw:
            fuzzy = f"%{kw}%"
            query = query.filter(
                or_(
                    DBUser.username.like(fuzzy),
                    DBUser.phone.like(fuzzy),
                    DBUser.nickname.like(fuzzy),
                )
            )

        total = query.count()
        users = (
            query.order_by(DBUser.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        usernames = [str(item.username or "").strip() for item in users if str(item.username or "").strip()]
        auth_map = {}
        mp_count_map = {}
        article_count_map = {}
        event_map = {}

        if usernames:
            from core.models.wechat_auth import WechatAuth
            from core.models.feed import Feed
            from core.models.article import Article
            from core.models.analytics_event import AnalyticsEvent

            auth_rows = session.query(WechatAuth).filter(WechatAuth.owner_id.in_(usernames)).all()
            auth_map = {str(item.owner_id or "").strip(): item for item in auth_rows if str(item.owner_id or "").strip()}

            mp_rows = (
                session.query(Feed.owner_id, func.count(Feed.id).label("count"))
                .filter(Feed.owner_id.in_(usernames))
                .group_by(Feed.owner_id)
                .all()
            )
            mp_count_map = {str(row[0] or "").strip(): int(row[1] or 0) for row in mp_rows if str(row[0] or "").strip()}

            article_rows = (
                session.query(Article.owner_id, func.count(Article.id).label("count"))
                .filter(Article.owner_id.in_(usernames))
                .group_by(Article.owner_id)
                .all()
            )
            article_count_map = {str(row[0] or "").strip(): int(row[1] or 0) for row in article_rows if str(row[0] or "").strip()}

            event_rows = (
                session.query(
                    AnalyticsEvent.username,
                    func.count(AnalyticsEvent.id).label("event_count"),
                    func.max(AnalyticsEvent.created_at).label("last_active"),
                )
                .filter(AnalyticsEvent.username.in_(usernames))
                .group_by(AnalyticsEvent.username)
                .all()
            )
            for row in event_rows:
                uname = str(getattr(row, "username", "") or "").strip()
                if not uname:
                    continue
                event_map[uname] = {
                    "event_count": int(getattr(row, "event_count", 0) or 0),
                    "last_active": getattr(row, "last_active", None),
                }

        # 格式化返回数据
        user_list = []
        for user in users:
            username = str(user.username or "").strip()
            plan = get_user_plan_summary(user)
            auth_item = auth_map.get(username)
            auth_serialized = serialize_wechat_auth(auth_item, mask=True)
            event_info = event_map.get(username, {})
            user_list.append({
                "username": username,
                "phone": user.phone or "",
                "nickname": user.nickname if user.nickname else user.username,
                "avatar": user.avatar if user.avatar else "/static/default-avatar.png",
                "email": user.email if user.email else "",
                "role": user.role,
                "is_active": user.is_active,
                "plan_tier": plan["tier"],
                "plan_label": plan["label"],
                "ai_quota": plan["ai_quota"],
                "ai_used": plan["ai_used"],
                "image_quota": plan["image_quota"],
                "image_used": plan["image_used"],
                "wechat_authorized": bool(auth_serialized.get("authorized")),
                "wechat_auth": auth_serialized,
                "mp_count": int(mp_count_map.get(username, 0)),
                "article_count": int(article_count_map.get(username, 0)),
                "event_count": int(event_info.get("event_count", 0) or 0),
                "last_active": event_info.get("last_active").isoformat() if event_info.get("last_active") else None,
                "created_at": user.created_at.strftime("%Y-%m-%d %H:%M:%S") if user.created_at else "",
                "updated_at": user.updated_at.strftime("%Y-%m-%d %H:%M:%S") if user.updated_at else ""
            })
        session.commit()

        return success_response({
            "total": total,
            "page": page,
            "page_size": page_size,
            "keyword": kw,
            "list": user_list
        })
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(
                code=50002,
                message=f"获取用户列表失败: {str(e)}"
            )
        )

@router.post("", summary="添加用户")
async def add_user(
    user_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """添加新用户"""
    session = DB.get_session()
    try:
        _require_admin(current_user)

        # 验证输入数据
        required_fields = ["username", "password", "email"]
        for field in required_fields:
            if field not in user_data:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=error_response(
                        code=40001,
                        message=f"缺少必填字段: {field}"
                    )
                )

        # 检查用户名是否已存在
        existing_user = session.query(DBUser).filter(
            DBUser.username == user_data["username"]
        ).first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(
                    code=40002,
                    message="用户名已存在"
                )
            )

        # 创建新用户
        now = datetime.now()
        target_tier = normalize_plan_tier(user_data.get("plan_tier", "free"))
        target_plan = get_plan_definition(target_tier)
        new_user = DBUser(
            id=str(uuid.uuid4()),
            username=user_data["username"],
            phone=user_data.get("phone"),
            password_hash=pwd_context.hash(user_data["password"]),
            email=user_data["email"],
            role=user_data.get("role", "user"),
            permissions=user_data.get("permissions", '["wechat:manage","config:view","message_task:view","message_task:edit","tag:view","tag:edit"]'),
            plan_tier=target_tier,
            monthly_ai_quota=max(0, int(user_data.get("monthly_ai_quota", target_plan["ai_quota"]))),
            monthly_ai_used=max(0, int(user_data.get("monthly_ai_used", 0))),
            monthly_image_quota=max(0, int(user_data.get("monthly_image_quota", target_plan["image_quota"]))),
            monthly_image_used=max(0, int(user_data.get("monthly_image_used", 0))),
            quota_reset_at=now,
            is_active=user_data.get("is_active", True),
            created_at=now,
            updated_at=now
        )
        session.add(new_user)
        session.commit()

        return success_response(message="用户添加成功")
    except HTTPException as e:
        raise e
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_406_NOT_ACCEPTABLE,
            detail=f"用户添加失败: {str(e)}"
        )

@router.put("", summary="修改用户资料")
async def update_user_info(
    update_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """修改用户基本信息(不包括密码)"""
    session = DB.get_session()
    try:
        # 获取目标用户
        target_username = update_data.get("username", current_user["username"])
        user = session.query(DBUser).filter(
            DBUser.username == target_username
        ).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response(
                    code=40401,
                    message="用户不存在"
                )
            )

        # 检查权限：只有管理员或用户自己可以修改信息
        if current_user["role"] != "admin" and current_user["username"] != target_username:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=error_response(
                    code=40301,
                    message="无权限修改其他用户信息"
                )
            )

        # 不允许通过此接口修改密码
        if "password" in update_data:
            raise HTTPException(
                status_code=status.HTTP_200_OK,
                detail=error_response(
                    code=40002,
                    message="请使用专门的密码修改接口"
                )
            )

        # 更新用户信息
        if "is_active" in update_data:
            user.is_active = bool(update_data["is_active"])
        if "email" in update_data:
            user.email = update_data["email"]
        if "nickname" in update_data:
            user.nickname = update_data["nickname"]
        if "avatar" in update_data:
            user.avatar = update_data["avatar"]
        if "wechat_app_id" in update_data:
            user.wechat_app_id = str(update_data.get("wechat_app_id") or "").strip()
        if "wechat_app_secret" in update_data:
            secret_value = str(update_data.get("wechat_app_secret") or "").strip()
            clear_secret = bool(update_data.get("clear_wechat_app_secret"))
            if secret_value:
                user.wechat_app_secret = secret_value
            elif clear_secret:
                user.wechat_app_secret = ""
        if "role" in update_data and current_user["role"] == "admin":
            user.role = update_data["role"]

        if current_user["role"] == "admin" and "plan_tier" in update_data:
            plan_tier = normalize_plan_tier(update_data["plan_tier"])
            defaults = get_plan_definition(plan_tier)
            user.plan_tier = plan_tier
            if "monthly_ai_quota" not in update_data:
                user.monthly_ai_quota = defaults["ai_quota"]
            if "monthly_image_quota" not in update_data:
                user.monthly_image_quota = defaults["image_quota"]

        if current_user["role"] == "admin" and "monthly_ai_quota" in update_data:
            user.monthly_ai_quota = max(0, int(update_data["monthly_ai_quota"] or 0))
        if current_user["role"] == "admin" and "monthly_image_quota" in update_data:
            user.monthly_image_quota = max(0, int(update_data["monthly_image_quota"] or 0))
        if current_user["role"] == "admin" and "monthly_ai_used" in update_data:
            user.monthly_ai_used = max(0, int(update_data["monthly_ai_used"] or 0))
        if current_user["role"] == "admin" and "monthly_image_used" in update_data:
            user.monthly_image_used = max(0, int(update_data["monthly_image_used"] or 0))
        if current_user["role"] == "admin" and "plan_expires_at" in update_data:
            plan_expires_at = update_data["plan_expires_at"]
            if not plan_expires_at:
                user.plan_expires_at = None
            elif isinstance(plan_expires_at, datetime):
                user.plan_expires_at = plan_expires_at
            else:
                user.plan_expires_at = datetime.fromisoformat(str(plan_expires_at))

        user.updated_at = datetime.now()
        session.commit()
        from core.auth import clear_user_cache
        clear_user_cache(target_username)
        return success_response(message="更新成功")
    except HTTPException as e:
        raise e
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_406_NOT_ACCEPTABLE,
            detail=f"更新失败: {str(e)}"
        )


@router.get("/plans", summary="获取套餐目录")
async def get_plans(current_user: dict = Depends(get_current_user)):
    return success_response(get_plan_catalog())


@router.put("/{username}/plan", summary="管理员更新用户套餐")
async def update_user_plan(
    username: str,
    payload: dict,
    current_user: dict = Depends(get_current_user),
):
    _require_admin(current_user)
    session = DB.get_session()
    user = session.query(DBUser).filter(DBUser.username == username).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    try:
        if "plan_tier" in payload:
            tier = normalize_plan_tier(payload.get("plan_tier"))
            defaults = get_plan_definition(tier)
            user.plan_tier = tier
            if "monthly_ai_quota" not in payload:
                user.monthly_ai_quota = defaults["ai_quota"]
            if "monthly_image_quota" not in payload:
                user.monthly_image_quota = defaults["image_quota"]

        if "monthly_ai_quota" in payload:
            user.monthly_ai_quota = max(0, int(payload.get("monthly_ai_quota") or 0))
        if "monthly_image_quota" in payload:
            user.monthly_image_quota = max(0, int(payload.get("monthly_image_quota") or 0))
        if "monthly_ai_used" in payload:
            user.monthly_ai_used = max(0, int(payload.get("monthly_ai_used") or 0))
        if "monthly_image_used" in payload:
            user.monthly_image_used = max(0, int(payload.get("monthly_image_used") or 0))
        if "plan_expires_at" in payload:
            plan_expires_at = payload.get("plan_expires_at")
            if not plan_expires_at:
                user.plan_expires_at = None
            else:
                user.plan_expires_at = datetime.fromisoformat(str(plan_expires_at))

        user.updated_at = datetime.now()
        session.commit()
        plan = get_user_plan_summary(user)
        session.commit()
        return success_response({
            "username": user.username,
            "plan": {
                **plan,
                "quota_reset_at": plan["quota_reset_at"].isoformat() if plan.get("quota_reset_at") else None,
                "plan_expires_at": plan["plan_expires_at"].isoformat() if plan.get("plan_expires_at") else None,
            },
        }, message="套餐更新成功")
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"套餐更新失败: {e}")


@router.post("/{username}/plan/reset-usage", summary="管理员重置用户配额消耗")
async def reset_user_plan_usage(
    username: str,
    current_user: dict = Depends(get_current_user),
):
    _require_admin(current_user)
    session = DB.get_session()
    user = session.query(DBUser).filter(DBUser.username == username).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    user.monthly_ai_used = 0
    user.monthly_image_used = 0
    user.quota_reset_at = datetime.now()
    user.updated_at = datetime.now()
    session.commit()
    plan = get_user_plan_summary(user)
    session.commit()
    return success_response({
        "username": user.username,
        "plan": {
            **plan,
            "quota_reset_at": plan["quota_reset_at"].isoformat() if plan.get("quota_reset_at") else None,
            "plan_expires_at": plan["plan_expires_at"].isoformat() if plan.get("plan_expires_at") else None,
        },
    }, message="已重置用户配额消耗")


@router.get("/{username}/admin-detail", summary="管理员查看用户详情（含授权信息）")
async def get_user_admin_detail(
    username: str,
    mask_sensitive: bool = Query(False, description="是否对 token/cookie 脱敏"),
    current_user: dict = Depends(get_current_user),
):
    _require_admin(current_user)
    session = DB.get_session()
    try:
        user = session.query(DBUser).filter(DBUser.username == username).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

        from core.models.feed import Feed
        from core.models.article import Article
        from core.models.message_task import MessageTask
        from core.models.analytics_event import AnalyticsEvent

        plan = get_user_plan_summary(user)
        auth_item = get_wechat_auth(session, owner_id=username)
        auth_data = serialize_wechat_auth(auth_item, mask=mask_sensitive)
        auth_data["fingerprint"] = str(getattr(auth_item, "fingerprint", "") or "")
        raw_payload = {}
        raw_text = str(getattr(auth_item, "raw_json", "") or "").strip()
        if raw_text:
            try:
                raw_payload = json.loads(raw_text)
            except Exception:
                raw_payload = {"raw": raw_text[:1200]}
        auth_data["raw_payload"] = raw_payload

        feed_rows = (
            session.query(Feed)
            .filter(Feed.owner_id == username)
            .order_by(Feed.created_at.desc())
            .limit(200)
            .all()
        )
        subscriptions = [
            {
                "id": item.id,
                "mp_name": item.mp_name or "",
                "faker_id": item.faker_id or "",
                "status": int(item.status or 0),
                "created_at": item.created_at.isoformat() if item.created_at else None,
                "updated_at": item.updated_at.isoformat() if item.updated_at else None,
            }
            for item in feed_rows
        ]

        article_count = int(
            session.query(func.count(Article.id))
            .filter(Article.owner_id == username)
            .scalar()
            or 0
        )
        mp_count = int(
            session.query(func.count(Feed.id))
            .filter(Feed.owner_id == username)
            .scalar()
            or 0
        )
        task_count = int(
            session.query(func.count(MessageTask.id))
            .filter(MessageTask.owner_id == username)
            .scalar()
            or 0
        )
        event_stats = (
            session.query(
                func.count(AnalyticsEvent.id).label("event_count"),
                func.max(AnalyticsEvent.created_at).label("last_active"),
            )
            .filter(AnalyticsEvent.username == username)
            .first()
        )
        event_count = int(getattr(event_stats, "event_count", 0) or 0)
        last_active = getattr(event_stats, "last_active", None)

        return success_response({
            "user": {
                "username": user.username,
                "phone": user.phone or "",
                "nickname": user.nickname if user.nickname else user.username,
                "email": user.email if user.email else "",
                "avatar": user.avatar if user.avatar else "/static/default-avatar.png",
                "wechat_app_id": str(getattr(user, "wechat_app_id", "") or ""),
                "wechat_app_secret_set": bool(str(getattr(user, "wechat_app_secret", "") or "").strip()),
                "role": user.role,
                "is_active": bool(user.is_active),
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "updated_at": user.updated_at.isoformat() if user.updated_at else None,
            },
            "plan": {
                **plan,
                "quota_reset_at": plan["quota_reset_at"].isoformat() if plan.get("quota_reset_at") else None,
                "plan_expires_at": plan["plan_expires_at"].isoformat() if plan.get("plan_expires_at") else None,
            },
            "usage": {
                "mp_count": mp_count,
                "article_count": article_count,
                "task_count": task_count,
                "event_count": event_count,
                "last_active": last_active.isoformat() if last_active else None,
            },
            "wechat_auth": auth_data,
            "subscriptions": subscriptions,
        })
    finally:
        try:
            session.close()
        except Exception:
            pass


@router.delete("/{username}", summary="管理员删除用户")
async def delete_user(
    username: str,
    current_user: dict = Depends(get_current_user),
):
    _require_admin(current_user)
    if str(current_user.get("username") or "").strip() == str(username or "").strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_response(code=40011, message="不允许删除当前登录管理员账号"),
        )

    session = DB.get_session()
    try:
        target = session.query(DBUser).filter(DBUser.username == username).first()
        if not target:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response(code=40401, message="用户不存在"),
            )

        from core.models.feed import Feed
        from core.models.article import Article
        from core.models.wechat_auth import WechatAuth
        from core.models.message_task import MessageTask
        from core.models.message_task_log import MessageTask as MessageTaskLog
        from core.models.tags import Tags
        from core.models.analytics_event import AnalyticsEvent
        from core.models.ai_profile import AIProfile
        from core.models.ai_publish_task import AIPublishTask
        from core.models.billing_order import BillingOrder

        deleted = {
            "articles": session.query(Article).filter(Article.owner_id == username).delete(synchronize_session=False),
            "feeds": session.query(Feed).filter(Feed.owner_id == username).delete(synchronize_session=False),
            "wechat_auths": session.query(WechatAuth).filter(WechatAuth.owner_id == username).delete(synchronize_session=False),
            "message_tasks": session.query(MessageTask).filter(MessageTask.owner_id == username).delete(synchronize_session=False),
            "message_task_logs": session.query(MessageTaskLog).filter(MessageTaskLog.owner_id == username).delete(synchronize_session=False),
            "tags": session.query(Tags).filter(Tags.owner_id == username).delete(synchronize_session=False),
            "analytics_events": session.query(AnalyticsEvent).filter(AnalyticsEvent.owner_id == username).delete(synchronize_session=False),
            "analytics_events_by_username": session.query(AnalyticsEvent).filter(AnalyticsEvent.username == username).delete(synchronize_session=False),
            "ai_profiles": session.query(AIProfile).filter(AIProfile.owner_id == username).delete(synchronize_session=False),
            "ai_publish_tasks": session.query(AIPublishTask).filter(AIPublishTask.owner_id == username).delete(synchronize_session=False),
            "billing_orders": session.query(BillingOrder).filter(BillingOrder.owner_id == username).delete(synchronize_session=False),
        }
        session.delete(target)
        session.commit()

        try:
            from core.auth import clear_user_cache
            clear_user_cache(username)
        except Exception:
            pass

        return success_response({
            "username": username,
            "deleted": deleted,
        }, message="用户及关联数据已删除")
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_response(code=50003, message=f"删除用户失败: {e}"),
        )
    finally:
        try:
            session.close()
        except Exception:
            pass
   

@router.put("/password", summary="修改密码")
async def change_password(
    password_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """修改用户密码"""
    session = DB.get_session()
    try:
        # 验证请求数据
        if "old_password" not in password_data or "new_password" not in password_data:
            from .base import error_response
            raise HTTPException(
                status_code=status.HTTP_200_OK,
                detail=error_response(
                    code=40001,
                    message="需要提供旧密码和新密码"
                )
            )
            
        # 获取用户
        user = session.query(DBUser).filter(
            DBUser.username == current_user["username"]
        ).first()
        if not user:
            from .base import error_response
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response(
                    code=40401,
                    message="用户不存在"
                )
            )
            
        # 验证旧密码
        if not pwd_context.verify(password_data["old_password"], user.password_hash):
            from .base import error_response
            raise HTTPException(
                status_code=status.HTTP_200_OK,
                detail=error_response(
                    code=40003,
                    message="旧密码不正确"
                )
            )
            
        # 验证新密码复杂度
        new_password = password_data["new_password"]
        if len(new_password) < 8:
            from .base import error_response
            raise HTTPException(
                status_code=status.HTTP_200_OK,
                detail=error_response(
                    code=40004,
                    message="密码长度不能少于8位"
                )
            )
            
        # 更新密码
        user.password_hash = pwd_context.hash(new_password)
        user.updated_at = datetime.now()
        session.commit()
        session.expire(user)
        # 清除用户缓存，确保新密码立即生效
        from core.auth import clear_user_cache
        clear_user_cache(current_user["username"])
        
        from .base import success_response
        return success_response(message="密码修改成功")
        
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_406_NOT_ACCEPTABLE,
            detail=f"密码修改失败: {str(e)}"
        )
@router.post("/avatar", summary="上传用户头像")
async def upload_avatar(
    file: UploadFile = File(...),
    # file: typing.Optional[UploadFile] = None,
    current_user: dict = Depends(get_current_user)
):
    """处理用户头像上传"""
    try:
        avatar_path="files/avatars"
        # 确保头像目录存在
        os.makedirs(avatar_path, exist_ok=True)
        from core.res.avatar import avatar_dir
        # 保存文件
        file_path = f"{avatar_dir}/{current_user['username']}.jpg"
        with open(file_path, "wb") as buffer:
            buffer.write(await file.read())
        
        # 更新用户头像字段
        session = DB.get_session()
        try:
            user = session.query(DBUser).filter(
                DBUser.username == current_user["username"]
            ).first()
            if user:
                user.avatar = f"/{avatar_path}/{current_user['username']}.jpg"
                session.commit()
        except Exception as e:
            session.rollback()
            raise HTTPException(
                status_code=status.HTTP_406_NOT_ACCEPTABLE,
                detail=f"更新用户头像失败: {str(e)}"
            )

        from .base import success_response
        return success_response(data={"avatar": f"/{avatar_path}/{current_user['username']}.jpg"})
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_406_NOT_ACCEPTABLE,
            detail=f"头像上传失败: {str(e)}"
        )
@router.post("/upload", summary="上传文件")
async def upload_file(
    file: UploadFile = File(...),
    type: str = "tags",
    current_user: dict = Depends(get_current_user)
):
    """处理用户文件上传"""
    try:
        # 验证 type 参数的安全性
        if not type.isalnum() or type in ["", ".."]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(
                    code=40003,
                    message="无效的文件类型"
                )
            )
        file_url_path=f"files/{type}/"
        from core.res.avatar import files_dir
        upload_path = f"{files_dir}/{type}/"
        # 确保上传目录存在
        os.makedirs(upload_path, exist_ok=True)

        # 生成唯一的文件名
        file_name = f"{current_user['username']}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}"
        file_path = f"{upload_path}/{file_name}"

        # 保存文件
        with open(file_path, "wb") as buffer:
            buffer.write(await file.read())
        return success_response(data={"url": f"/{file_url_path}/{file_name}"})
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_406_NOT_ACCEPTABLE,
            detail=f"文件上传失败: {str(e)}"
        )
