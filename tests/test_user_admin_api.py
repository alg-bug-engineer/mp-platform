import unittest
import uuid

from core.db import DB
from core.models.user import User
from apis.user import add_user


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


if __name__ == "__main__":
    unittest.main()
