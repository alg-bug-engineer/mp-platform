from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from core.auth import get_current_user
from core.db import DB
from core.models import User as DBUser
from core.auth import pwd_context
import os
import uuid
from datetime import datetime
from core.plan_service import (
    get_user_plan_summary,
    get_plan_catalog,
    normalize_plan_tier,
    get_plan_definition,
)
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
    page_size: int = 10
):
    """获取所有用户列表（仅管理员可用）"""
    session = DB.get_session()
    try:
        _require_admin(current_user)

        # 查询用户总数
        total = session.query(DBUser).count()

        # 分页查询用户列表
        users = session.query(DBUser).order_by(DBUser.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

        # 格式化返回数据
        user_list = []
        for user in users:
            plan = get_user_plan_summary(user)
            user_list.append({
                "username": user.username,
                "phone": user.phone or "",
                "nickname": user.nickname if user.nickname else user.username,
                "avatar": user.avatar if user.avatar else "/static/default-avatar.png",
                "email": user.email if user.email else "",
                "role": user.role,
                "is_active": user.is_active,
                "plan_tier": plan["tier"],
                "plan_label": plan["label"],
                "ai_quota": plan["ai_quota"],
                "image_quota": plan["image_quota"],
                "created_at": user.created_at.strftime("%Y-%m-%d %H:%M:%S") if user.created_at else "",
                "updated_at": user.updated_at.strftime("%Y-%m-%d %H:%M:%S") if user.updated_at else ""
            })
        session.commit()

        return success_response({
            "total": total,
            "page": page,
            "page_size": page_size,
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
