import unittest
import uuid
from unittest.mock import patch

from core.db import DB
from core.wechat_auth_service import (
    upsert_wechat_auth,
    get_token_cookie,
    migrate_global_auth_to_owner,
    get_wechat_auth,
)
from core.models.wechat_auth import WechatAuth


class _DummyCfg:
    def __init__(self, data):
        self.data = data

    def get(self, key, default=""):
        if key == "expiry.expiry_time":
            return self.data.get("expiry", {}).get("expiry_time", default)
        return self.data.get(key, default)


class WechatAuthServiceTestCase(unittest.TestCase):
    def setUp(self):
        DB.create_tables()
        self.session = DB.get_session()
        self.owner_id = f"u_{uuid.uuid4().hex[:8]}"

    def tearDown(self):
        try:
            self.session.query(WechatAuth).filter(WechatAuth.owner_id == self.owner_id).delete()
            self.session.commit()
        except Exception:
            pass
        self.session.close()

    def test_upsert_and_get_token_cookie(self):
        upsert_wechat_auth(
            session=self.session,
            owner_id=self.owner_id,
            token="token-demo",
            cookie="cookie-demo",
            wx_app_name="demo-app",
        )
        token, cookie = get_token_cookie(self.session, self.owner_id, allow_global_fallback=False)
        self.assertEqual(token, "token-demo")
        self.assertEqual(cookie, "cookie-demo")

    def test_migrate_global_auth(self):
        fake_data = {
            "token": "global-token",
            "cookie": "global-cookie",
            "fingerprint": "fp-1",
            "expiry": {"expiry_time": "2099-01-01 00:00:00"},
            "ext_data": {"wx_app_name": "global-app", "wx_user_name": "global-user"},
        }
        with patch("driver.token.wx_cfg", _DummyCfg(fake_data)):
            result = migrate_global_auth_to_owner(self.session, owner_id=self.owner_id, overwrite=True)
        self.assertTrue(result.get("migrated"))
        item = get_wechat_auth(self.session, self.owner_id)
        self.assertEqual(item.token, "global-token")


if __name__ == "__main__":
    unittest.main()
