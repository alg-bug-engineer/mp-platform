#!/usr/bin/env python3
"""
测试微信草稿标题清理功能
"""

import sys
import re


def _clean_title(raw_title: str, max_bytes: int = 50) -> str:
    """
    清理并截断标题以符合微信公众号要求

    Args:
        raw_title: 原始标题
        max_bytes: 最大字节数（默认50，保守值避免 errcode=45003）

    Returns:
        清理后的标题
    """
    # 1. 清理控制字符和特殊符号
    title = str(raw_title or "").strip()
    # 移除换行符、制表符、回车等控制字符
    title = re.sub(r'[\r\n\t\v\f]', ' ', title)
    # 移除其他控制字符（Unicode 控制字符范围）
    title = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', title)
    # 压缩多个空格为单个空格
    title = re.sub(r'\s+', ' ', title).strip()

    # 2. 截断字节长度
    if not title:
        return "未命名草稿"

    if len(title.encode('utf-8')) <= max_bytes:
        return title

    # 逐字符截断，确保不超过字节限制
    parts = []
    used_bytes = 0
    for ch in title:
        ch_bytes = len(ch.encode('utf-8'))
        if used_bytes + ch_bytes > max_bytes:
            break
        parts.append(ch)
        used_bytes += ch_bytes

    result = ''.join(parts).strip()
    return result or "未命名草稿"


def test_title_cleanup():
    """测试标题清理功能"""

    test_cases = [
        # (输入标题, 期望结果描述)
        ("正常标题", "应该保持不变"),
        ("这是一个很长的标题" * 10, "应该被截断到50字节"),
        ("标题\n包含\n换行符", "换行符应该被替换为空格"),
        ("标题\t包含\t制表符", "制表符应该被替换为空格"),
        ("标题   包含   多个空格", "多个空格应该压缩为单个空格"),
        ("", "空标题应该返回'未命名草稿'"),
        ("   ", "纯空格应该返回'未命名草稿'"),
        ("标题\x00包含\x01控制字符", "控制字符应该被移除"),
        ("AI 创作｜深度分析｜技术解读", "特殊符号应该保留"),
        ("【重要】这是一个带emoji的标题😀", "emoji应该保留但可能被截断"),
    ]

    print("=" * 80)
    print("测试微信草稿标题清理功能")
    print("=" * 80)
    print()

    all_passed = True
    for i, (input_title, description) in enumerate(test_cases, 1):
        cleaned = _clean_title(input_title, max_bytes=50)
        byte_len = len(cleaned.encode('utf-8'))

        print(f"测试 {i}: {description}")
        print(f"  输入: {repr(input_title)}")
        print(f"  输出: {repr(cleaned)}")
        print(f"  字节长度: {byte_len} bytes")

        # 验证
        issues = []
        if byte_len > 50:
            issues.append(f"❌ 超过50字节限制（实际 {byte_len} bytes）")
            all_passed = False
        if '\n' in cleaned or '\t' in cleaned or '\r' in cleaned:
            issues.append("❌ 仍包含换行符或制表符")
            all_passed = False
        if re.search(r'\s{2,}', cleaned):
            issues.append("❌ 仍包含多个连续空格")
            all_passed = False
        if not cleaned.strip():
            if input_title.strip():
                issues.append("❌ 清理后变为空（但输入非空）")
                all_passed = False

        if issues:
            for issue in issues:
                print(f"  {issue}")
        else:
            print(f"  ✅ 通过")
        print()

    print("=" * 80)
    if all_passed:
        print("🎉 所有测试通过！")
        return 0
    else:
        print("⚠️ 部分测试失败，请检查上面的错误")
        return 1


def test_real_world_titles():
    """测试真实场景中的标题"""

    print("\n" + "=" * 80)
    print("真实场景测试")
    print("=" * 80)
    print()

    real_titles = [
        "AI 创作工具使用指南：如何利用 GPT-4 提升内容质量",
        "深度解析：微信公众号草稿箱 API 的 5 个常见问题及解决方案",
        "2024 年最值得关注的 10 个开源 AI 项目（附详细评测）",
        "从零开始学习 Python：一份适合初学者的完整教程",
    ]

    for title in real_titles:
        cleaned = _clean_title(title, max_bytes=50)
        byte_len = len(cleaned.encode('utf-8'))

        print(f"原始标题: {title}")
        print(f"清理后: {cleaned}")
        print(f"字节长度: {byte_len} / 50 bytes")
        print(f"状态: {'✅ 通过' if byte_len <= 50 else '❌ 超长'}")
        print()


if __name__ == "__main__":
    exit_code = test_title_cleanup()
    test_real_world_titles()
    sys.exit(exit_code)
