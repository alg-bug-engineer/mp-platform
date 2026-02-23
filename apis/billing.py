from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from core.auth import get_current_user
from core.db import DB
from core.models.user import User as DBUser
from core.billing_service import (
    create_order,
    create_order_payload,
    list_orders,
    get_order_by_no,
    mark_order_paid,
    cancel_order,
    get_billing_catalog,
    sweep_expired_subscriptions,
    get_user_billing_overview,
)
from .base import success_response


router = APIRouter(prefix="/billing", tags=["支付订阅"])


def _require_admin(current_user: dict):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权限执行此操作")


class CreateOrderRequest(BaseModel):
    plan_tier: str = Field(default="pro", max_length=20)
    months: int = Field(default=1, ge=1, le=24)
    channel: str = Field(default="mock", max_length=32)
    note: str = Field(default="", max_length=500)


class PayOrderRequest(BaseModel):
    provider_txn_id: str = Field(default="", max_length=120)
    provider_payload: str = Field(default="", max_length=2000)


class CancelOrderRequest(BaseModel):
    reason: str = Field(default="", max_length=200)


class WebhookMockRequest(BaseModel):
    order_no: str = Field(default="", max_length=80)
    provider_txn_id: str = Field(default="", max_length=120)
    provider_payload: str = Field(default="", max_length=2000)


@router.get("/catalog", summary="获取付费套餐目录")
async def billing_catalog(current_user: dict = Depends(get_current_user)):
    return success_response(get_billing_catalog())


@router.get("/overview", summary="获取用户订阅概览")
async def billing_overview(current_user: dict = Depends(get_current_user)):
    session = DB.get_session()
    user = session.query(DBUser).filter(DBUser.username == current_user.get("username")).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return success_response(get_user_billing_overview(session, user))


@router.post("/orders", summary="创建订阅订单")
async def create_billing_order(payload: CreateOrderRequest, current_user: dict = Depends(get_current_user)):
    session = DB.get_session()
    user = session.query(DBUser).filter(DBUser.username == current_user.get("username")).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    try:
        order = create_order(
            session=session,
            owner_id=user.username,
            plan_tier=payload.plan_tier,
            months=payload.months,
            channel=payload.channel,
            note=payload.note,
        )
        return success_response(create_order_payload(order), message="订单创建成功")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"创建订单失败: {e}")


@router.get("/orders", summary="获取当前用户订单列表")
async def get_my_orders(
    status: str = Query("", max_length=32),
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
):
    session = DB.get_session()
    return success_response(list_orders(session, owner_id=current_user.get("username"), status=status, limit=limit))


@router.get("/orders/admin", summary="管理员获取全量订单")
async def get_all_orders(
    status: str = Query("", max_length=32),
    limit: int = Query(200, ge=1, le=500),
    current_user: dict = Depends(get_current_user),
):
    _require_admin(current_user)
    session = DB.get_session()
    return success_response(list_orders(session, owner_id="", status=status, limit=limit))


@router.post("/orders/{order_no}/pay", summary="确认订单支付（模拟）")
async def pay_order(order_no: str, payload: PayOrderRequest, current_user: dict = Depends(get_current_user)):
    session = DB.get_session()
    order = get_order_by_no(session, order_no)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    is_admin = current_user.get("role") == "admin"
    if not is_admin and order.owner_id != current_user.get("username"):
        raise HTTPException(status_code=403, detail="无权限支付该订单")
    try:
        updated = mark_order_paid(
            session=session,
            order=order,
            provider_txn_id=payload.provider_txn_id,
            provider_payload=payload.provider_payload,
        )
        return success_response(create_order_payload(updated), message="订单支付成功")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"订单支付失败: {e}")


@router.post("/orders/{order_no}/cancel", summary="取消待支付订单")
async def cancel_billing_order(order_no: str, payload: CancelOrderRequest, current_user: dict = Depends(get_current_user)):
    session = DB.get_session()
    order = get_order_by_no(session, order_no)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    is_admin = current_user.get("role") == "admin"
    if not is_admin and order.owner_id != current_user.get("username"):
        raise HTTPException(status_code=403, detail="无权限取消该订单")
    try:
        updated = cancel_order(session, order, reason=payload.reason)
        return success_response(create_order_payload(updated), message="订单已取消")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"取消失败: {e}")


@router.post("/webhook/mock", summary="模拟支付回调")
async def mock_webhook(payload: WebhookMockRequest, current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    session = DB.get_session()
    order = get_order_by_no(session, payload.order_no)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    try:
        updated = mark_order_paid(
            session=session,
            order=order,
            provider_txn_id=payload.provider_txn_id or f"mock-{order.order_no}",
            provider_payload=payload.provider_payload,
        )
        return success_response(create_order_payload(updated), message="回调处理成功")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"回调处理失败: {e}")


@router.post("/subscriptions/sweep", summary="扫描并降级已过期订阅")
async def sweep_subscriptions(current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    session = DB.get_session()
    result = sweep_expired_subscriptions(session=session, limit=500)
    return success_response(result)
