import uuid
from datetime import datetime
from typing import Dict, List, Tuple

from core.models.billing_order import BillingOrder
from core.models.user import User as DBUser
from core.plan_service import (
    get_plan_definition,
    normalize_plan_tier,
    ensure_user_plan_defaults,
    get_user_plan_summary,
)


ORDER_STATUS_PENDING = "pending"
ORDER_STATUS_PAID = "paid"
ORDER_STATUS_CANCELED = "canceled"


PLAN_MONTHLY_PRICE_CENTS = {
    "free": 0,
    "pro": 9900,
    "premium": 39900,
}


def _add_months(dt: datetime, months: int) -> datetime:
    month = int(dt.month - 1 + months)
    year = int(dt.year + month // 12)
    month = int(month % 12 + 1)
    day = min(
        dt.day,
        [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1],
    )
    return dt.replace(year=year, month=month, day=day)


def _new_order_no() -> str:
    return f"ORD{datetime.now().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:6].upper()}"


def _order_to_dict(order: BillingOrder) -> Dict:
    return {
        "id": order.id,
        "order_no": order.order_no,
        "owner_id": order.owner_id,
        "plan_tier": order.plan_tier,
        "months": int(order.months or 0),
        "amount_cents": int(order.amount_cents or 0),
        "currency": order.currency,
        "channel": order.channel,
        "status": order.status,
        "paid_at": order.paid_at.isoformat() if order.paid_at else None,
        "effective_from": order.effective_from.isoformat() if order.effective_from else None,
        "effective_to": order.effective_to.isoformat() if order.effective_to else None,
        "provider_txn_id": order.provider_txn_id or "",
        "note": order.note or "",
        "created_at": order.created_at.isoformat() if order.created_at else None,
    }


def _channel_pay_hint(order: BillingOrder) -> Dict:
    if (order.channel or "").lower() == "mock":
        return {
            "type": "mock",
            "message": "测试支付通道，请调用确认支付接口完成支付。",
            "mock_token": f"mockpay://{order.order_no}",
        }
    return {"type": "manual", "message": "当前通道仅支持线下确认。"}


def create_order(
    session,
    owner_id: str,
    plan_tier: str,
    months: int = 1,
    channel: str = "mock",
    note: str = "",
) -> BillingOrder:
    tier = normalize_plan_tier(plan_tier)
    if tier == "free":
        raise ValueError("免费套餐不支持创建付费订单")
    m = max(1, min(int(months or 1), 24))
    now = datetime.now()
    amount_cents = int(PLAN_MONTHLY_PRICE_CENTS.get(tier, 0) * m)
    order = BillingOrder(
        id=str(uuid.uuid4()),
        order_no=_new_order_no(),
        owner_id=str(owner_id or "").strip(),
        plan_tier=tier,
        months=m,
        amount_cents=amount_cents,
        currency="CNY",
        channel=(channel or "mock").strip().lower(),
        status=ORDER_STATUS_PENDING,
        note=(note or "").strip()[:500],
        created_at=now,
        updated_at=now,
    )
    session.add(order)
    session.commit()
    session.refresh(order)
    return order


def apply_subscription(user: DBUser, tier: str, months: int) -> Tuple[datetime, datetime]:
    now = datetime.now()
    normalized = normalize_plan_tier(tier)
    if normalized == "free":
        normalized = "free"
    start = now
    current_expire = getattr(user, "plan_expires_at", None)
    if current_expire and current_expire > now:
        start = current_expire
    end = _add_months(start, max(1, int(months or 1)))

    user.plan_tier = normalized
    defaults = get_plan_definition(normalized)
    user.monthly_ai_quota = int(defaults["ai_quota"])
    user.monthly_image_quota = int(defaults["image_quota"])
    ensure_user_plan_defaults(user, preferred_tier=normalized)
    user.plan_expires_at = end
    user.updated_at = now
    return start, end


def mark_order_paid(
    session,
    order: BillingOrder,
    provider_txn_id: str = "",
    provider_payload: str = "",
) -> BillingOrder:
    if not order:
        raise ValueError("order 不存在")
    if order.status == ORDER_STATUS_PAID:
        return order
    if order.status != ORDER_STATUS_PENDING:
        raise ValueError("订单状态不可支付")
    user = session.query(DBUser).filter(DBUser.username == order.owner_id).first()
    if not user:
        raise ValueError("用户不存在")
    start, end = apply_subscription(user, order.plan_tier, int(order.months or 1))
    now = datetime.now()
    order.status = ORDER_STATUS_PAID
    order.paid_at = now
    order.effective_from = start
    order.effective_to = end
    order.provider_txn_id = (provider_txn_id or "").strip()[:120]
    order.provider_payload = (provider_payload or "")[:2000]
    order.updated_at = now
    session.commit()
    session.refresh(order)
    return order


def cancel_order(session, order: BillingOrder, reason: str = "") -> BillingOrder:
    if not order:
        raise ValueError("order 不存在")
    if order.status == ORDER_STATUS_PAID:
        raise ValueError("已支付订单不可取消")
    order.status = ORDER_STATUS_CANCELED
    order.note = ((order.note or "") + f"\n取消原因: {reason}".strip())[:800]
    order.updated_at = datetime.now()
    session.commit()
    session.refresh(order)
    return order


def list_orders(session, owner_id: str = "", status: str = "", limit: int = 50) -> List[Dict]:
    query = session.query(BillingOrder)
    if owner_id:
        query = query.filter(BillingOrder.owner_id == owner_id)
    status_text = str(status or "").strip().lower()
    if status_text:
        query = query.filter(BillingOrder.status == status_text)
    rows = query.order_by(BillingOrder.created_at.desc()).limit(max(1, min(int(limit or 50), 200))).all()
    return [_order_to_dict(x) for x in rows]


def get_order_by_no(session, order_no: str) -> BillingOrder:
    no = str(order_no or "").strip()
    if not no:
        return None
    return session.query(BillingOrder).filter(BillingOrder.order_no == no).first()


def get_billing_catalog() -> List[Dict]:
    data = []
    for tier in ["pro", "premium"]:
        plan = get_plan_definition(tier)
        monthly_price_cents = int(PLAN_MONTHLY_PRICE_CENTS.get(tier, 0))
        data.append(
            {
                "tier": tier,
                "label": plan["label"],
                "description": plan["description"],
                "monthly_price_cents": monthly_price_cents,
                "monthly_price_text": f"¥{monthly_price_cents / 100:.2f}/月",
                "ai_quota": plan["ai_quota"],
                "image_quota": plan["image_quota"],
                "highlights": plan["highlights"],
            }
        )
    return data


def create_order_payload(order: BillingOrder) -> Dict:
    return {
        **_order_to_dict(order),
        "payment": _channel_pay_hint(order),
    }


def sweep_expired_subscriptions(session, limit: int = 200) -> Dict:
    now = datetime.now()
    users = session.query(DBUser).filter(
        DBUser.plan_tier != "free",
        DBUser.plan_expires_at != None,  # noqa: E711
        DBUser.plan_expires_at < now,
    ).limit(max(1, min(int(limit or 200), 1000))).all()
    changed = []
    free_defaults = get_plan_definition("free")
    for user in users:
        user.plan_tier = "free"
        user.plan_expires_at = None
        user.monthly_ai_quota = int(free_defaults["ai_quota"])
        user.monthly_image_quota = int(free_defaults["image_quota"])
        user.monthly_ai_used = min(int(user.monthly_ai_used or 0), int(user.monthly_ai_quota))
        user.monthly_image_used = min(int(user.monthly_image_used or 0), int(user.monthly_image_quota))
        user.updated_at = now
        changed.append(user.username)
    if changed:
        session.commit()
    return {"total": len(changed), "users": changed}


def get_user_billing_overview(session, user: DBUser) -> Dict:
    summary = get_user_plan_summary(user)
    recent_orders = list_orders(session, owner_id=user.username, limit=10)
    return {
        "plan": summary,
        "catalog": get_billing_catalog(),
        "recent_orders": recent_orders,
    }
