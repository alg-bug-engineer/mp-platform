#!/usr/bin/env python3
"""
优化验证脚本

验证本次优化的三个核心功能是否正常工作：
1. 提示词模块
2. 图片服务
3. 微信草稿服务
"""

import sys
from pathlib import Path

def verify_prompt_templates():
    """验证提示词模块"""
    print("=" * 60)
    print("1. 验证提示词模块（prompt_templates.py）")
    print("=" * 60)

    try:
        from core.prompt_templates import (
            build_natural_prompt,
            get_frontend_options,
            PLATFORM_CHARACTERISTICS,
            WRITING_STYLES,
            CONTENT_LENGTHS,
        )

        # 测试获取前端选项
        options = get_frontend_options()
        platforms = options.get("platforms", [])
        styles = options.get("styles", [])
        lengths = options.get("lengths", [])

        print(f"✅ 平台数量: {len(platforms)}")
        print(f"✅ 风格数量: {len(styles)}")
        print(f"✅ 篇幅数量: {len(lengths)}")

        # 测试构建提示词
        system_prompt, user_prompt = build_natural_prompt(
            mode="create",
            platform="wechat",
            style="专业深度",
            length="medium",
            instruction="测试用例",
            audience="技术从业者",
            tone="专业但不端着",
            source_title="测试文章",
            source_content="这是一篇测试文章的内容...",
        )

        print(f"✅ 系统提示词长度: {len(system_prompt)} 字符")
        print(f"✅ 用户提示词长度: {len(user_prompt)} 字符")

        # 显示示例
        print("\n【示例】平台特性（wechat）:")
        wechat = PLATFORM_CHARACTERISTICS.get("wechat", {})
        print(f"  - 语气: {wechat.get('tone_desc', '')[:50]}...")

        print("\n【示例】写作风格（专业深度）:")
        style_info = WRITING_STYLES.get("专业深度", {})
        print(f"  - 描述: {style_info.get('description', '')}")

        print("\n✅ 提示词模块验证通过！")
        return True

    except Exception as e:
        print(f"\n❌ 提示词模块验证失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def verify_image_service():
    """验证图片服务"""
    print("\n" + "=" * 60)
    print("2. 验证图片服务（image_service.py）")
    print("=" * 60)

    try:
        from core.image_service import ImageService

        # 创建测试服务实例
        service = ImageService(owner_id="test_user")

        print(f"✅ 用户目录: {service.owner_dir}")
        print(f"✅ 用户ID: {service.owner_id}")

        # 检查目录是否创建
        if service.owner_dir.exists():
            print(f"✅ 目录已创建: {service.owner_dir}")
        else:
            print(f"❌ 目录未创建: {service.owner_dir}")
            return False

        # 验证方法存在
        methods = [
            "download_jimeng_image",
            "compress_image_stream",
            "download_and_compress",
            "compress_local_file",
        ]

        for method in methods:
            if hasattr(service, method):
                print(f"✅ 方法存在: {method}()")
            else:
                print(f"❌ 方法缺失: {method}()")
                return False

        print("\n✅ 图片服务验证通过！")
        return True

    except Exception as e:
        print(f"\n❌ 图片服务验证失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def verify_wechat_draft_service():
    """验证微信草稿服务"""
    print("\n" + "=" * 60)
    print("3. 验证微信草稿服务（wechat_draft_service.py）")
    print("=" * 60)

    try:
        from core.wechat_draft_service import WeChatDraftService

        # 创建测试服务实例（不需要真实凭证）
        service = WeChatDraftService(
            app_id="test_app_id",
            app_secret="test_app_secret",
            owner_id="test_user",
        )

        print(f"✅ App ID: {service.app_id}")
        print(f"✅ 用户ID: {service.owner_id}")
        print(f"✅ 封面图限制: {service.MAX_COVER_IMG_SIZE / 1024 / 1024:.0f}MB")
        print(f"✅ 正文图限制: {service.MAX_ARTICLE_IMG_SIZE / 1024 / 1024:.0f}MB")

        # 验证方法存在
        methods = [
            "get_access_token",
            "upload_cover_image",
            "upload_article_image",
            "process_html_images",
            "submit_draft",
        ]

        for method in methods:
            if hasattr(service, method):
                print(f"✅ 方法存在: {method}()")
            else:
                print(f"❌ 方法缺失: {method}()")
                return False

        # 验证图片服务已集成
        if hasattr(service, 'image_service'):
            print(f"✅ 图片服务已集成")
        else:
            print(f"❌ 图片服务未集成")
            return False

        print("\n✅ 微信草稿服务验证通过！")
        return True

    except Exception as e:
        print(f"\n❌ 微信草稿服务验证失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主函数"""
    print("\n" + "🚀" * 30)
    print("开始验证优化模块...")
    print("🚀" * 30 + "\n")

    results = []

    # 1. 验证提示词模块
    results.append(("提示词模块", verify_prompt_templates()))

    # 2. 验证图片服务
    results.append(("图片服务", verify_image_service()))

    # 3. 验证微信草稿服务
    results.append(("微信草稿服务", verify_wechat_draft_service()))

    # 总结
    print("\n" + "=" * 60)
    print("验证结果总结")
    print("=" * 60)

    all_passed = True
    for name, passed in results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"{status} - {name}")
        if not passed:
            all_passed = False

    print("=" * 60)

    if all_passed:
        print("\n🎉 所有模块验证通过！优化已成功完成。")
        print("\n下一步：")
        print("  开发环境启动：")
        print("    1. 后端: python main.py -job True -init True")
        print("    2. 前端: cd web_ui && npm run dev")
        print("    3. 访问 http://localhost:5173")
        print("\n  生产环境启动：")
        print("    script/deploy.sh start")
        print("\n详细说明请查看 docs/records/2026-02-24-OPTIMIZATION_SUMMARY.md")
        return 0
    else:
        print("\n⚠️ 部分模块验证失败，请检查错误信息。")
        return 1


if __name__ == "__main__":
    sys.exit(main())
