import unittest
import uuid
from datetime import datetime, timedelta

from core.db import DB
from core.auth import pwd_context
from core.models.user import User
from core.billing_service import (
    create_order,
    mark_order_paid,
    sweep_expired_subscriptions,
    ORDER_STATUS_PENDING,
    ORDER_STATUS_PAID,
)


class BillingFlowTestCase(unittest.TestCase):
    def setUp(self):
        DB.create_tables()
        self.session = DB.get_session()
        self.username = f"u_{uuid.uuid4().hex[:10]}"
        now = datetime.now()
        user = User(
            id=str(uuid.uuid4()),
            username=self.username,
            phone=f"18{uuid.uuid4().int % 1000000000:09d}",
            password_hash=pwd_context.hash("demo123456"),
            role="user",
            permissions="[]",
            plan_tier="free",
            monthly_ai_quota=30,
            monthly_ai_used=0,
            monthly_image_quota=5,
            monthly_image_used=0,
            quota_reset_at=now,
            created_at=now,
            updated_at=now,
            is_active=True,
        )
        self.session.add(user)
        self.session.commit()

    def tearDown(self):
        try:
            self.session.query(User).filter(User.username == self.username).delete()
            self.session.commit()
        except Exception:
            pass
        self.session.close()

    def test_create_and_pay_order(self):
        order = create_order(self.session, owner_id=self.username, plan_tier="pro", months=1, channel="mock")
        self.assertEqual(order.status, ORDER_STATUS_PENDING)
        paid = mark_order_paid(self.session, order, provider_txn_id="mock-1")
        self.assertEqual(paid.status, ORDER_STATUS_PAID)
        user = self.session.query(User).filter(User.username == self.username).first()
        self.assertEqual(user.plan_tier, "pro")
        self.assertIsNotNone(user.plan_expires_at)

    def test_renew_should_extend(self):
        first = create_order(self.session, owner_id=self.username, plan_tier="pro", months=1, channel="mock")
        first = mark_order_paid(self.session, first, provider_txn_id="mock-2")
        old_expire = first.effective_to

        second = create_order(self.session, owner_id=self.username, plan_tier="pro", months=2, channel="mock")
        second = mark_order_paid(self.session, second, provider_txn_id="mock-3")
        self.assertIsNotNone(second.effective_to)
        self.assertGreaterEqual(second.effective_to, old_expire)

    def test_sweep_expired(self):
        user = self.session.query(User).filter(User.username == self.username).first()
        user.plan_tier = "pro"
        user.plan_expires_at = datetime.now() - timedelta(days=1)
        self.session.commit()
        result = sweep_expired_subscriptions(self.session, limit=100)
        self.assertGreaterEqual(result.get("total", 0), 1)
        user2 = self.session.query(User).filter(User.username == self.username).first()
        self.assertEqual(user2.plan_tier, "free")
        self.assertIsNone(user2.plan_expires_at)


if __name__ == "__main__":
    unittest.main()
