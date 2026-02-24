from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.security import OAuth2PasswordRequestForm
from datetime import timedelta
from pydantic import BaseModel, Field
from datetime import datetime
import re
import uuid
from core.auth import (
    authenticate_user,
    create_access_token,
    get_current_user,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    pwd_context
)
from .ver import API_VERSION
from .base import success_response, error_response
from driver.base import WX_API
from core.config import set_config, cfg
from core.db import DB
from core.models.user import User as DBUser
from core.plan_service import get_plan_definition
from core.wechat_auth_service import (
    upsert_wechat_auth,
    has_wechat_auth,
    serialize_wechat_auth,
    get_wechat_auth,
    validate_and_maybe_clear_wechat_auth,
    migrate_global_auth_to_owner,
)
router = APIRouter(prefix=f"/auth", tags=["认证"])
from driver.success import Success
from driver.wx_api import get_qr_code #通过API登录
def ApiSuccess(data):
    if data != None:
            print("\n登录结果:")
            print(f"Token: {data['token']}")
            set_config("token",data['token'])
            cfg.reload()
    else:
            print("\n登录失败，请检查上述错误信息")
@router.get("/qr/code", summary="获取登录二维码")
async def get_qrcode(current_user=Depends(get_current_user)):
    owner_id = current_user.get("username")

    def _on_auth_success(data: dict, ext_data: dict = None):
        session = DB.get_session()
        ext = ext_data or {}
        expiry = (data or {}).get("expiry", {}) or {}
        try:
            upsert_wechat_auth(
                session=session,
                owner_id=owner_id,
                token=(data or {}).get("token", ""),
                cookie=(data or {}).get("cookies_str", ""),
                fingerprint=(data or {}).get("fingerprint", ""),
                wx_app_name=ext.get("wx_app_name", ""),
                wx_user_name=ext.get("wx_user_name", ""),
                expiry_time=expiry.get("expiry_time", ""),
                raw_payload={"data": data, "ext_data": ext},
            )
        finally:
            try:
                session.close()
            except Exception:
                pass

    code_url = WX_API.GetCode(_on_auth_success) or {}
    if not code_url.get("code"):
        message = str(code_url.get("msg") or "二维码获取失败，请稍后重试")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=error_response(code=50301, message=message),
        )
    return success_response(code_url)
@router.get("/qr/image", summary="获取登录二维码图片")
async def qr_image(current_user=Depends(get_current_user)):
    return success_response(WX_API.GetHasCode())

@router.get("/qr/status",summary="获取扫描状态")
async def qr_status(current_user=Depends(get_current_user)):
     session = DB.get_session()
     try:
         owner_id = current_user.get("username")
         login_status = has_wechat_auth(session, owner_id)
         qr_exists = bool(WX_API.GetHasCode()) if hasattr(WX_API, "GetHasCode") else False
         error_message = str(getattr(WX_API, "last_login_error", "") or "")
         if login_status:
             error_message = ""
         return success_response({
              "login_status": bool(login_status),
              "qr_exists": qr_exists,
              "error_message": error_message,
         })
     finally:
         try:
             session.close()
         except Exception:
             pass
@router.get("/qr/over",summary="扫码完成")
async def qr_success(current_user=Depends(get_current_user)):
     return success_response(WX_API.Close())    


@router.get("/wechat/auth", summary="获取当前用户公众号授权状态")
async def get_wechat_auth_status(
    strict: bool = Query(False, description="是否执行严格会话校验"),
    current_user=Depends(get_current_user),
):
    session = DB.get_session()
    owner_id = current_user.get("username")
    if strict:
        validate_and_maybe_clear_wechat_auth(session, owner_id)
    auth = get_wechat_auth(session, owner_id)
    return success_response(serialize_wechat_auth(auth, mask=True))


@router.post("/wechat/mock-bind", summary="手工绑定公众号授权（仅管理员）")
async def mock_bind_wechat_auth(payload: dict, current_user=Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权限执行")
    owner_id = str(payload.get("owner_id") or current_user.get("username")).strip()
    token = str(payload.get("token") or "").strip()
    cookie = str(payload.get("cookie") or "").strip()
    if not token or not cookie:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="token/cookie 不能为空")
    session = DB.get_session()
    auth = upsert_wechat_auth(
        session=session,
        owner_id=owner_id,
        token=token,
        cookie=cookie,
        fingerprint=str(payload.get("fingerprint") or ""),
        wx_app_name=str(payload.get("wx_app_name") or ""),
        wx_user_name=str(payload.get("wx_user_name") or ""),
        expiry_time=str(payload.get("expiry_time") or ""),
        raw_payload={"source": "mock_bind"},
    )
    return success_response(serialize_wechat_auth(auth, mask=True), message="绑定成功")


@router.post("/wechat/migrate-global", summary="迁移全局微信授权到用户维度（仅管理员）")
async def migrate_global_wechat_auth(payload: dict = None, current_user=Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权限执行")
    body = payload or {}
    owner_id = str(body.get("owner_id") or "admin").strip() or "admin"
    overwrite = bool(body.get("overwrite", False))
    session = DB.get_session()
    result = migrate_global_auth_to_owner(session, owner_id=owner_id, overwrite=overwrite)
    return success_response(result)
@router.post("/login", summary="用户登录")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_response(
                code=40101,
                message="用户名或密码错误"
            )
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return success_response({
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60
    })


class RegisterRequest(BaseModel):
    phone: str = Field(..., min_length=11, max_length=20)
    password: str = Field(..., min_length=6, max_length=64)
    nickname: str = Field(default="")


@router.post("/register", summary="手机号注册")
async def register(payload: RegisterRequest):
    phone = payload.phone.strip()
    if not re.match(r"^1[3-9]\d{9}$", phone):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_response(code=40001, message="手机号格式不正确")
        )

    session = DB.get_session()
    try:
        exists = session.query(DBUser).filter(
            (DBUser.phone == phone) | (DBUser.username == phone)
        ).first()
        if exists:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(code=40002, message="手机号已注册")
            )

        now = datetime.now()
        free_plan = get_plan_definition("free")
        new_user = DBUser(
            id=str(uuid.uuid4()),
            username=phone,
            phone=phone,
            password_hash=pwd_context.hash(payload.password),
            nickname=payload.nickname or phone[-4:],
            role="user",
            permissions='["wechat:manage","config:view","message_task:view","message_task:edit","tag:view","tag:edit"]',
            plan_tier="free",
            monthly_ai_quota=free_plan["ai_quota"],
            monthly_ai_used=0,
            monthly_image_quota=free_plan["image_quota"],
            monthly_image_used=0,
            quota_reset_at=now,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        session.add(new_user)
        session.commit()
        return success_response({
            "phone": phone,
            "username": phone
        }, message="注册成功")
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(code=50001, message=f"注册失败: {e}")
        )


@router.post("/token",summary="获取Token")
async def getToken(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_202_ACCEPTED,
            detail=error_response(
                code=40101,
                message="用户名或密码错误"
            )
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60
    }


@router.post("/logout", summary="用户注销")
async def logout(current_user: dict = Depends(get_current_user)):
    return {"code": 0, "message": "注销成功"}

@router.post("/refresh", summary="刷新Token")
async def refresh_token(current_user: dict = Depends(get_current_user)):
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": current_user["username"]}, expires_delta=access_token_expires
    )
    return success_response({
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60
    })

@router.get("/verify", summary="验证Token有效性")
async def verify_token(current_user: dict = Depends(get_current_user)):
    """验证当前token是否有效"""
    return success_response({
        "is_valid": True,
        "username": current_user["username"],
        "expires_at": current_user.get("exp")
    })
