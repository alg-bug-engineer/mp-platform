import unittest
import uuid
from datetime import datetime

from core.db import DB
from core.analytics_service import save_event, build_analytics_summary, list_registered_user_usage
from core.auth import pwd_context
from core.models.analytics_event import AnalyticsEvent
from core.models.user import User


class AnalyticsServiceTestCase(unittest.TestCase):
    def setUp(self):
        DB.create_tables()
        self.session = DB.get_session()
        self.username = f"u_{uuid.uuid4().hex[:8]}"
        now = datetime.now()
        user = User(
            id=str(uuid.uuid4()),
            username=self.username,
            phone=f"13{uuid.uuid4().int % 1000000000:09d}",
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
            self.session.query(AnalyticsEvent).delete()
            self.session.query(User).filter(User.username == self.username).delete()
            self.session.commit()
        except Exception:
            pass
        self.session.close()

    def test_build_analytics_summary(self):
        save_event(
            self.session,
            {
                'event_type': 'page_view',
                'page': '/workspace/content',
                'username': 'u1',
                'session_id': 's1',
            },
        )
        save_event(
            self.session,
            {
                'event_type': 'input',
                'feature': 'form',
                'action': 'typing',
                'input_name': 'title',
                'input_length': 8,
                'username': 'u1',
                'session_id': 's1',
            },
        )
        save_event(
            self.session,
            {
                'event_type': 'api_request',
                'path': '/api/v1/wx/article',
                'feature': 'article',
                'action': 'list',
                'status_code': 200,
                'duration_ms': 86,
                'username': 'u1',
                'session_id': 's1',
            },
        )
        self.session.commit()

        summary = build_analytics_summary(self.session, days=7, limit=10)
        overview = summary['overview']

        self.assertGreaterEqual(overview['total_events'], 3)
        self.assertGreaterEqual(overview['page_views'], 1)
        self.assertGreaterEqual(overview['api_requests'], 1)
        self.assertGreaterEqual(overview['input_events'], 1)
        self.assertGreaterEqual(len(summary['top_pages']), 1)
        self.assertGreaterEqual(len(summary['top_features']), 1)

    def test_list_registered_user_usage_should_return_all_registered_users(self):
        result = list_registered_user_usage(self.session, page=1, page_size=20, keyword="")
        self.assertGreaterEqual(result["total"], 1)
        usernames = [item.get("username") for item in result.get("list", [])]
        self.assertIn(self.username, usernames)


if __name__ == '__main__':
    unittest.main()
