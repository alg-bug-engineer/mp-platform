import unittest

from core.ai_service import build_image_prompts, merge_image_urls_into_markdown


class AIMarkdownImagesTestCase(unittest.TestCase):
    def test_merge_images_should_put_cover_after_first_paragraph(self):
        content = (
            "# 标题\n\n"
            "这是首段导语，说明文章背景与问题。\n\n"
            "这是第二段，展开方法细节。\n\n"
            "这是第三段，给出结果与建议。"
        )
        merged = merge_image_urls_into_markdown(
            content,
            [
                "https://img.test/cover.png",
                "https://img.test/inline-1.png",
                "https://img.test/inline-2.png",
            ],
        )
        self.assertIn("![封面图](https://img.test/cover.png)", merged)
        self.assertIn("![内容配图1](https://img.test/inline-1.png)", merged)
        self.assertIn("![内容配图2](https://img.test/inline-2.png)", merged)
        self.assertLess(
            merged.index("这是首段导语"),
            merged.index("![封面图](https://img.test/cover.png)"),
        )

    def test_merge_single_inline_image_should_land_in_middle_section(self):
        content = (
            "# 标题\n\n"
            "第一段导语，交代背景和核心问题。\n\n"
            "第二段背景，补充上下文与现状。\n\n"
            "第三段展开，进入方案和关键细节。\n\n"
            "第四段总结，收束观点并给出建议。"
        )
        merged = merge_image_urls_into_markdown(
            content,
            [
                "https://img.test/cover.png",
                "https://img.test/inline-middle.png",
            ],
        )
        inline = "![内容配图1](https://img.test/inline-middle.png)"
        self.assertIn(inline, merged)
        self.assertLess(merged.index("第三段展开"), merged.index(inline))
        self.assertLess(merged.index(inline), merged.index("第四段总结"))

    def test_build_image_prompts_should_include_cover_and_section_focus(self):
        prompts = build_image_prompts(
            title="AI 时代的内容增长",
            platform="wechat",
            style="专业深度",
            image_count=3,
            content=(
                "首段：先讲增长困境。\n\n"
                "第二段：再讲解决策略与执行路径。\n\n"
                "第三段：最后给出案例与结论。"
            ),
        )
        self.assertEqual(len(prompts), 3)
        self.assertIn("cover scene for opening section", prompts[0])
        self.assertIn("section illustration focus", prompts[1])


if __name__ == "__main__":
    unittest.main()
