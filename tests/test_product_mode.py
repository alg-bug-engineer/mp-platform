import unittest

from core.product_mode import get_product_mode, set_product_mode
from core.plan_service import validate_ai_action


class DummyUser:
    def __init__(self):
        self.role = 'user'
        self.plan_tier = 'free'
        self.monthly_ai_quota = 30
        self.monthly_ai_used = 0
        self.monthly_image_quota = 5
        self.monthly_image_used = 0
        self.quota_reset_at = None
        self.plan_expires_at = None


class ProductModeTestCase(unittest.TestCase):
    def setUp(self):
        self.origin_mode = get_product_mode()

    def tearDown(self):
        set_product_mode(self.origin_mode)

    def test_all_free_mode_should_open_plan_limits(self):
        user = DummyUser()

        set_product_mode('commercial')
        ok_commercial, _, _ = validate_ai_action(
            user=user,
            mode='create',
            image_count=1,
            publish_to_wechat=True,
        )
        self.assertFalse(ok_commercial)

        set_product_mode('all_free')
        ok_all_free, _, summary = validate_ai_action(
            user=user,
            mode='create',
            image_count=1,
            publish_to_wechat=True,
        )
        self.assertTrue(ok_all_free)
        self.assertTrue(summary.get('can_generate_images'))
        self.assertTrue(summary.get('can_publish_wechat_draft'))


if __name__ == '__main__':
    unittest.main()
