import unittest
from datetime import datetime, timedelta

from core.ai_service import summarize_activity_metrics


class DummyTask:
    def __init__(self, created_at, status):
        self.created_at = created_at
        self.status = status


class AIActivityMetricsTestCase(unittest.TestCase):
    def test_summarize_activity_metrics(self):
        now = datetime(2026, 2, 18, 12, 0, 0)
        drafts = [
            {"created_at": (now - timedelta(days=1)).isoformat()},
            {"created_at": (now - timedelta(days=1, hours=1)).isoformat()},
            {"created_at": (now - timedelta(days=3)).isoformat()},
            {"created_at": (now - timedelta(days=10)).isoformat()},
        ]
        tasks = [
            DummyTask(now - timedelta(days=1), "success"),
            DummyTask(now - timedelta(days=2), "failed"),
            DummyTask(now - timedelta(days=3), "pending"),
            DummyTask(now - timedelta(days=10), "success"),
        ]

        data = summarize_activity_metrics(drafts=drafts, publish_tasks=tasks, days=7, now=now)
        self.assertEqual(data["draft_count_7d"], 3)
        self.assertAlmostEqual(data["avg_daily_draft"], 0.43, places=2)
        self.assertEqual(data["publish_total_7d"], 3)
        self.assertEqual(data["publish_success_7d"], 1)
        self.assertEqual(data["publish_failed_7d"], 1)
        self.assertEqual(data["publish_pending_7d"], 1)
        self.assertEqual(data["publish_success_rate_7d"], 50.0)
        self.assertEqual(len(data["trend"]), 7)

    def test_empty_activity_metrics(self):
        now = datetime(2026, 2, 18, 12, 0, 0)
        data = summarize_activity_metrics(drafts=[], publish_tasks=[], days=7, now=now)
        self.assertEqual(data["draft_count_7d"], 0)
        self.assertEqual(data["publish_total_7d"], 0)
        self.assertIsNone(data["publish_success_rate_7d"])
        self.assertEqual(len(data["trend"]), 7)

    def test_direct_sync_delivery_should_count(self):
        now = datetime(2026, 2, 18, 12, 0, 0)
        drafts = [
            {
                "created_at": (now - timedelta(days=1)).isoformat(),
                "metadata": {
                    "delivery": {
                        "wechat": {
                            "status": "success",
                            "delivered_at": (now - timedelta(days=1, hours=1)).isoformat(),
                            "source": "draft_sync_action",
                        }
                    }
                },
            }
        ]
        data = summarize_activity_metrics(drafts=drafts, publish_tasks=[], days=7, now=now)
        self.assertEqual(data["draft_count_7d"], 1)
        self.assertEqual(data["publish_total_7d"], 1)
        self.assertEqual(data["publish_success_7d"], 1)
        self.assertEqual(data["publish_failed_7d"], 0)
        self.assertEqual(data["publish_success_rate_7d"], 100.0)


if __name__ == "__main__":
    unittest.main()
