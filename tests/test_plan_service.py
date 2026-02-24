import unittest
from datetime import datetime

from core.plan_service import (
    ensure_user_plan_defaults,
    get_user_plan_summary,
    validate_ai_action,
    consume_ai_usage,
)
from core.product_mode import get_product_mode, set_product_mode


class DummyUser:
    def __init__(self, tier="free", role="user"):
        self.role = role
        self.plan_tier = tier
        self.plan_expires_at = None
        self.monthly_ai_quota = None
        self.monthly_ai_used = None
        self.monthly_image_quota = None
        self.monthly_image_used = None
        self.quota_reset_at = None
        self.updated_at = None


class PlanServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.origin_mode = get_product_mode()
        set_product_mode("commercial")

    def tearDown(self):
        set_product_mode(self.origin_mode)

    def test_default_plan_is_initialized(self):
        user = DummyUser()
        ensure_user_plan_defaults(user, preferred_tier="free")
        summary = get_user_plan_summary(user)
        self.assertEqual(summary["tier"], "free")
        self.assertGreater(summary["ai_quota"], 0)
        self.assertGreaterEqual(summary["ai_remaining"], 0)

    def test_usage_consume_works(self):
        user = DummyUser("pro")
        ensure_user_plan_defaults(user, preferred_tier="pro")
        before = get_user_plan_summary(user)
        consume_ai_usage(user, image_count=2)
        after = get_user_plan_summary(user)
        self.assertEqual(after["ai_used"], before["ai_used"] + 1)
        self.assertEqual(after["image_used"], before["image_used"] + 2)

    def test_validate_action_respects_quota(self):
        user = DummyUser("free")
        ensure_user_plan_defaults(user, preferred_tier="free")
        user.monthly_ai_used = user.monthly_ai_quota
        ok, _, _ = validate_ai_action(user, mode="create")
        self.assertFalse(ok)

    def test_monthly_reset(self):
        user = DummyUser("pro")
        ensure_user_plan_defaults(user, preferred_tier="pro")
        user.monthly_ai_used = 10
        user.monthly_image_used = 10
        user.quota_reset_at = datetime(2020, 1, 1)
        summary = get_user_plan_summary(user)
        self.assertEqual(summary["ai_used"], 0)
        self.assertEqual(summary["image_used"], 0)


if __name__ == "__main__":
    unittest.main()
