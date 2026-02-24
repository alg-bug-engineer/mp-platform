#!/usr/bin/env python3
"""
测试 Unicode JSON 响应编码
"""

import json
from fastapi.responses import JSONResponse
from typing import Any


class UnicodeJSONResponse(JSONResponse):
    """自定义 JSON 响应类，确保中文不被转义"""
    def render(self, content: Any) -> bytes:
        return json.dumps(
            content,
            ensure_ascii=False,  # 关键：不转义非ASCII字符
            allow_nan=False,
            indent=None,
            separators=(",", ":"),
        ).encode("utf-8")


def test_json_encoding():
    """测试 JSON 编码"""

    test_data = {
        "title": "揭秘GLM-5\u6280\u672f",  # Unicode 转义格式
        "content": "这是一篇关于 AI 技术的文章",
        "tags": ["人工智能", "深度学习", "GPT"],
        "metadata": {
            "author": "作者姓名",
            "date": "2024-01-01",
        }
    }

    print("=" * 80)
    print("测试 JSON 编码（中文字符处理）")
    print("=" * 80)
    print()

    # 测试 1: 默认 JSONResponse (ensure_ascii=True，会转义中文)
    print("1. 默认 JSONResponse (FastAPI 默认行为):")
    default_response = JSONResponse(content=test_data)
    default_body = default_response.render(test_data)
    default_text = default_body.decode('utf-8')
    print(f"   输出: {default_text[:200]}...")
    has_escape = '\\u' in default_text
    print(f"   包含 \\u 转义: {has_escape}")
    print()

    # 测试 2: UnicodeJSONResponse (ensure_ascii=False，不转义中文)
    print("2. UnicodeJSONResponse (修复后):")
    unicode_response = UnicodeJSONResponse(content=test_data)
    unicode_body = unicode_response.render(test_data)
    unicode_text = unicode_body.decode('utf-8')
    print(f"   输出: {unicode_text[:200]}...")
    has_escape = '\\u' in unicode_text
    print(f"   包含 \\u 转义: {has_escape}")
    print()

    # 验证
    print("=" * 80)
    print("验证结果:")
    print("=" * 80)

    # 解析 JSON
    default_parsed = json.loads(default_body)
    unicode_parsed = json.loads(unicode_body)

    print(f"✅ 默认响应解析成功: title = {default_parsed['title']}")
    print(f"✅ Unicode 响应解析成功: title = {unicode_parsed['title']}")
    print()

    # 检查字节大小
    print(f"默认响应字节数: {len(default_body)} bytes")
    print(f"Unicode 响应字节数: {len(unicode_body)} bytes")
    print(f"节省空间: {len(default_body) - len(unicode_body)} bytes ({100 - len(unicode_body)*100/len(default_body):.1f}% 更小)")
    print()

    # 可读性对比
    print("=" * 80)
    print("可读性对比:")
    print("=" * 80)
    print()
    print("默认响应（难以阅读）:")
    print(default_body.decode('utf-8'))
    print()
    print("Unicode 响应（易于阅读）:")
    print(unicode_body.decode('utf-8'))
    print()


def test_draft_example():
    """测试实际草稿数据"""

    draft_data = {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "article_id": "article_123",
        "title": "揭秘GLM-5\u6280\u672f",  # 用户报告的问题
        "content": "# AI 创作工具使用指南\n\n这是一篇关于人工智能的深度文章...",
        "platform": "wechat",
        "mode": "create",
        "created_at": "2024-01-01T10:00:00",
        "metadata": {
            "author": "AI 助手",
            "digest": "深度解析 AI 技术",
            "cover_url": "https://example.com/cover.jpg"
        }
    }

    print("=" * 80)
    print("实际草稿数据测试:")
    print("=" * 80)
    print()

    # 使用 UnicodeJSONResponse
    response = UnicodeJSONResponse(content=draft_data)
    body = response.render(draft_data)

    print("草稿 JSON 响应:")
    print(body.decode('utf-8'))
    print()

    # 验证可以正确解析
    parsed = json.loads(body)
    print(f"✅ 解析成功!")
    print(f"   标题: {parsed['title']}")
    print(f"   作者: {parsed['metadata']['author']}")
    print(f"   摘要: {parsed['metadata']['digest']}")
    print()


if __name__ == "__main__":
    test_json_encoding()
    print("\n" + "=" * 80 + "\n")
    test_draft_example()
