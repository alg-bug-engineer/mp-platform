# coding: utf-8
"""
即梦 API 示例脚本（安全版）

用途：
1. 平台联调：验证即梦文本生图能力是否可用
2. 场景模板：封面、Logo、素材配图等
3. 无硬编码 AK/SK：统一使用环境变量

环境变量：
- JIMENG_AK
- JIMENG_SK
- JIMENG_REQ_KEY（可选，默认 jimeng_t2i_v40）
"""

import argparse
import json
import os
import time
from typing import Dict

from volcengine.visual.VisualService import VisualService


SCENE_TEMPLATES: Dict[str, str] = {
    "article_cover": (
        "为《{topic}》生成公众号头图，风格 {style}，"
        "主体明确，留出中文标题区域，构图稳定，高清商业视觉。"
    ),
    "logo": (
        "为品牌《{topic}》生成简洁易识别的 logo，风格 {style}，"
        "线条清晰，适配深浅背景，纯净背景，矢量质感。"
    ),
    "material": (
        "生成内容素材图：主题《{topic}》，风格 {style}，"
        "画面干净，信息聚焦，可用于图文排版配图。"
    ),
    "article_illustration": (
        "生成文章插画：主题《{topic}》，风格 {style}，"
        "具备故事感和细节层次，适合公众号正文段落配图。"
    ),
}


def build_prompt(scene: str, topic: str, style: str) -> str:
    template = SCENE_TEMPLATES.get(scene, SCENE_TEMPLATES["material"])
    return template.format(topic=topic, style=style)


class JimengClient:
    def __init__(self, ak: str, sk: str):
        self.visual = VisualService()
        self.visual.set_ak(ak)
        self.visual.set_sk(sk)

    def submit_task(self, prompt: str, req_key: str, scale: float = 0.5, force_single: bool = True) -> str:
        body = {
            "req_key": req_key,
            "prompt": prompt,
            "scale": scale,
            "force_single": force_single,
        }
        resp = self.visual.cv_sync2async_submit_task(body)
        if resp.get("code") != 10000:
            raise RuntimeError(f"提交任务失败: {resp}")
        return resp["data"]["task_id"]

    def poll_result(self, task_id: str, req_key: str, max_retries: int = 20, sleep_seconds: float = 1.8):
        query_body = {
            "req_key": req_key,
            "task_id": task_id,
            "req_json": json.dumps({
                "return_url": True,
                "logo_info": {"add_logo": False},
            }),
        }

        for i in range(max_retries):
            resp = self.visual.cv_sync2async_get_result(query_body)
            if resp.get("code") != 10000:
                print(f"第{i + 1}次查询异常: {resp}")
                time.sleep(sleep_seconds)
                continue

            status = (resp.get("data") or {}).get("status")
            if status == "done":
                urls = (resp.get("data") or {}).get("image_urls") or []
                return urls
            if status in ["in_queue", "generating"]:
                print(f"任务处理中({status})，第{i + 1}次轮询")
                time.sleep(sleep_seconds)
                continue
            raise RuntimeError(f"任务状态异常: {status}")

        raise TimeoutError("轮询超时，请稍后在平台任务中心查看结果")


def main():
    parser = argparse.ArgumentParser(description="即梦文本生图示例")
    parser.add_argument("--scene", default="article_cover", choices=list(SCENE_TEMPLATES.keys()), help="场景模板")
    parser.add_argument("--topic", default="AI 创作平台", help="主题")
    parser.add_argument("--style", default="简洁科技感", help="视觉风格")
    parser.add_argument("--scale", type=float, default=0.5, help="文本影响程度 0-1")
    parser.add_argument("--max-retries", type=int, default=20, help="轮询次数")
    args = parser.parse_args()

    ak = str(os.getenv("JIMENG_AK", "")).strip()
    sk = str(os.getenv("JIMENG_SK", "")).strip()
    req_key = str(os.getenv("JIMENG_REQ_KEY", "jimeng_t2i_v40")).strip()

    if not ak or not sk:
        raise SystemExit(
            "缺少环境变量 JIMENG_AK/JIMENG_SK。\n"
            "示例：\n"
            "export JIMENG_AK='your-ak'\n"
            "export JIMENG_SK='your-sk'\n"
            "python tests/test_jimeng_api.py --scene article_cover --topic '自媒体增长' --style '极简商业'"
        )

    prompt = build_prompt(args.scene, args.topic, args.style)
    print(f"场景: {args.scene}")
    print(f"Prompt: {prompt}")

    client = JimengClient(ak=ak, sk=sk)
    task_id = client.submit_task(prompt=prompt, req_key=req_key, scale=args.scale, force_single=True)
    print(f"任务已提交，task_id={task_id}")

    urls = client.poll_result(task_id=task_id, req_key=req_key, max_retries=args.max_retries)
    if not urls:
        print("任务完成但未返回图片链接")
        return

    print("生成成功，图片链接：")
    for idx, url in enumerate(urls, start=1):
        print(f"{idx}. {url}")


if __name__ == "__main__":
    main()
