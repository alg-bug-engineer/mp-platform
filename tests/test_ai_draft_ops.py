import os
import shutil
import tempfile
import unittest

from core.ai_service import (
    save_local_draft,
    get_local_draft,
    update_local_draft,
    delete_local_draft,
)


class AIDraftOpsTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="ai-draft-ops-")
        os.environ["AI_DRAFT_DIR"] = self.temp_dir

    def tearDown(self):
        os.environ.pop("AI_DRAFT_DIR", None)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_update_and_delete_local_draft(self):
        owner = "ops-user"
        saved = save_local_draft(
            owner_id=owner,
            article_id="a-1",
            title="old title",
            content="old content",
            platform="wechat",
            mode="create",
            metadata={"author": "old"},
        )
        draft_id = saved.get("id")
        self.assertTrue(draft_id)

        updated = update_local_draft(
            owner_id=owner,
            draft_id=draft_id,
            title="new title",
            content="new content",
            platform="wechat",
            mode="rewrite",
            metadata={"author": "new"},
        )
        self.assertIsNotNone(updated)
        self.assertEqual(updated.get("title"), "new title")
        self.assertEqual(updated.get("content"), "new content")
        self.assertEqual(updated.get("mode"), "rewrite")
        self.assertEqual(updated.get("metadata", {}).get("author"), "new")
        self.assertTrue(updated.get("updated_at"))

        fetched = get_local_draft(owner, draft_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.get("title"), "new title")

        deleted = delete_local_draft(owner, draft_id)
        self.assertTrue(deleted)
        self.assertIsNone(get_local_draft(owner, draft_id))


if __name__ == "__main__":
    unittest.main()
