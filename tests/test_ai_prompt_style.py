import unittest

from core.ai_service import build_prompt


class AIPromptStyleTestCase(unittest.TestCase):
    def test_create_prompt_should_use_new_story_architect_template(self):
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
        self.assertIn("科技叙事架构师与热点解读者", user)
        self.assertIn("Initialization Workflow", user)
        self.assertIn("Adaptive Structure Templates", user)

    def test_rewrite_prompt_should_use_style_reconstruction_template(self):
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
        self.assertIn("Phase 3: 内容重构", user)
        self.assertIn("Output Format (输出格式)", user)
        self.assertIn("目标媒体/参考文章", user)


if __name__ == "__main__":
    unittest.main()
