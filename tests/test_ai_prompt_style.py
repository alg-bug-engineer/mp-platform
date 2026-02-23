import unittest

from core.ai_service import build_prompt


class AIPromptStyleTestCase(unittest.TestCase):
    def test_create_prompt_should_enforce_paragraph_first_rules(self):
        system, user = build_prompt(
            mode="create",
            title="测试标题",
            content="测试内容",
            instruction="",
            create_options={
                "platform": "wechat",
                "style": "专业深度",
                "length": "medium",
                "image_count": 1,
            },
        )
        self.assertTrue(system)
        self.assertIn("正文以自然段叙述为主", user)
        self.assertIn("最多使用 2 个二级标题", user)
        self.assertIn("仅允许 1 处且最多 3 条", user)

    def test_rewrite_prompt_should_request_full_paragraph_draft(self):
        _, user = build_prompt(
            mode="rewrite",
            title="测试标题",
            content="测试内容",
            instruction="",
            create_options={
                "platform": "wechat",
                "style": "专业深度",
                "length": "medium",
            },
        )
        self.assertIn("完整改写成稿", user)
        self.assertIn("正文以段落推进", user)


if __name__ == "__main__":
    unittest.main()
