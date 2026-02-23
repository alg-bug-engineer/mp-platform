import unittest
from datetime import datetime
from unittest.mock import patch

from core.ai_service import (
    process_publish_task,
    PUBLISH_STATUS_PENDING,
    PUBLISH_STATUS_SUCCESS,
    PUBLISH_STATUS_FAILED,
)


class DummySession:
    def commit(self):
        return None


class DummyTask:
    def __init__(self):
        self.owner_id = "tester"
        self.title = "demo"
        self.content = "content"
        self.digest = ""
        self.author = ""
        self.cover_url = ""
        self.status = PUBLISH_STATUS_PENDING
        self.retries = 0
        self.max_retries = 2
        self.last_error = ""
        self.last_response = ""
        self.next_retry_at = datetime.now()
        self.updated_at = datetime.now()


class AIPublishQueueTestCase(unittest.TestCase):
    def test_process_task_success(self):
        session = DummySession()
        task = DummyTask()
        with patch("core.ai_service.publish_to_wechat_draft", return_value=(True, "ok", {"ret": 0})):
            ok, _ = process_publish_task(session, task)
        self.assertTrue(ok)
        self.assertEqual(task.status, PUBLISH_STATUS_SUCCESS)
        self.assertEqual(task.retries, 0)

    def test_process_task_fail_to_failed(self):
        session = DummySession()
        task = DummyTask()
        task.retries = 1
        with patch("core.ai_service.publish_to_wechat_draft", return_value=(False, "network error", {"ret": -1})):
            ok, _ = process_publish_task(session, task)
        self.assertFalse(ok)
        self.assertEqual(task.status, PUBLISH_STATUS_FAILED)
        self.assertEqual(task.retries, 2)


if __name__ == "__main__":
    unittest.main()
