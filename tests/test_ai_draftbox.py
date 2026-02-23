import os
import shutil
import tempfile
import unittest

from core.ai_service import save_local_draft, list_local_drafts


class AIDraftboxTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="ai-drafts-")
        os.environ["AI_DRAFT_DIR"] = self.temp_dir

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        os.environ.pop("AI_DRAFT_DIR", None)

    def test_save_and_list_local_drafts(self):
        owner = "tester_user"
        saved = save_local_draft(
            owner_id=owner,
            article_id="a-1",
            title="测试草稿",
            content="这是一段测试内容",
            platform="wechat",
            mode="create",
            metadata={"scene": "unit-test"},
        )
        self.assertTrue(saved.get("id"))
        self.assertEqual(saved.get("owner_id"), owner)

        drafts = list_local_drafts(owner, limit=10)
        self.assertTrue(len(drafts) >= 1)
        self.assertEqual(drafts[0].get("title"), "测试草稿")


if __name__ == "__main__":
    unittest.main()
