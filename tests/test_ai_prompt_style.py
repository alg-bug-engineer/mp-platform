import unittest

from core.ai_service import build_prompt, ensure_markdown_content


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

    def test_ensure_markdown_should_wrap_plain_text(self):
        out = ensure_markdown_content(
            mode="create",
            title="测试标题",
            text="这是一段纯文本内容，没有标题也没有列表。",
        )
        self.assertIn("# 测试标题", out)
        self.assertRegex(out, r"(?m)^## ")
        self.assertRegex(out, r"(?m)^- \*\*要点")


if __name__ == "__main__":
    unittest.main()
