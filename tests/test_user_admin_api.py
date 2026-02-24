import unittest
import uuid

from core.db import DB
from core.models.user import User
from apis.user import add_user, update_user_info
from apis.ai import _resolve_wechat_openapi_credentials


class UserAdminApiTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_add_user_should_assign_id_and_plan_defaults(self):
        DB.create_tables()
        username = f"admin_add_{uuid.uuid4().hex[:8]}"
        payload = {
            "username": username,
            "password": "demo123456",
            "email": f"{username}@example.com",
        }
        result = await add_user(payload, current_user={"username": "admin", "role": "admin"})
        self.assertEqual(result.get("code"), 0)

        session = DB.get_session()
        try:
            user = session.query(User).filter(User.username == username).first()
            self.assertIsNotNone(user)
            self.assertTrue(bool(user.id))
            self.assertEqual(user.plan_tier, "free")
            self.assertGreaterEqual(user.monthly_ai_quota, 1)
            self.assertGreaterEqual(user.monthly_image_quota, 0)
            session.query(User).filter(User.username == username).delete()
            session.commit()
        finally:
            session.close()

    async def test_update_user_wechat_secret_should_keep_when_blank(self):
        DB.create_tables()
        username = f"wechat_user_{uuid.uuid4().hex[:8]}"
        session = DB.get_session()
        try:
            user = User(
                id=str(uuid.uuid4()),
                username=username,
                password_hash="hashed",
                email=f"{username}@example.com",
                role="user",
                is_active=True,
                wechat_app_id="wx_old",
                wechat_app_secret="sec_old",
            )
            session.add(user)
            session.commit()
        finally:
            session.close()

        await update_user_info(
            {
                "username": username,
                "wechat_app_id": "wx_new",
                "wechat_app_secret": "",
            },
            current_user={"username": username, "role": "user"},
        )

        session = DB.get_session()
        try:
            user = session.query(User).filter(User.username == username).first()
            self.assertIsNotNone(user)
            self.assertEqual(user.wechat_app_id, "wx_new")
            self.assertEqual(user.wechat_app_secret, "sec_old")
            session.query(User).filter(User.username == username).delete()
            session.commit()
        finally:
            session.close()

    def test_resolve_wechat_credentials_should_fallback_to_profile(self):
        class _User:
            wechat_app_id = "wx_profile"
            wechat_app_secret = "sec_profile"

        app_id, app_secret, source = _resolve_wechat_openapi_credentials(
            user=_User(),
            app_id="",
            app_secret="",
        )
        self.assertEqual(source, "profile")
        self.assertEqual(app_id, "wx_profile")
        self.assertEqual(app_secret, "sec_profile")

        app_id, app_secret, source = _resolve_wechat_openapi_credentials(
            user=_User(),
            app_id="wx_req",
            app_secret="",
        )
        self.assertEqual(source, "partial_request")
        self.assertEqual(app_id, "")
        self.assertEqual(app_secret, "")


if __name__ == "__main__":
    unittest.main()
