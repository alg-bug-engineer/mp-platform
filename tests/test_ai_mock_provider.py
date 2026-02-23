import unittest

from core.ai_service import call_openai_compatible


class _DummyProfile:
    def __init__(self):
        self.base_url = "mock://local"
        self.api_key = "mock"
        self.model_name = "mock-model"
        self.temperature = 70


class AIMockProviderTestCase(unittest.TestCase):
    def test_mock_provider_output(self):
        profile = _DummyProfile()
        text = call_openai_compatible(profile, "sys", "素材标题：测试标题\n正文：hello")
        self.assertIn("测试标题", text)
        self.assertIn("模拟生成内容", text)


if __name__ == "__main__":
    unittest.main()
