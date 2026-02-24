from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
import os
import re
import json
import uuid
import time
import html
import logging
import hashlib
import io
from urllib.parse import urlparse

import requests
import yaml
from fastapi import HTTPException, status

from core.config import cfg
from core.models.ai_profile import AIProfile
from core.models.ai_publish_task import AIPublishTask
from core.models.ai_compose_result import AIComposeResult
from core.prompt_templates import build_natural_prompt

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.moonshot.cn/v1"
DEFAULT_MODEL = "kimi-k2-0711-preview"

_RULES_CACHE = {
    "path": None,
    "mtime": None,
    "data": None,
}

DEFAULT_LOCAL_RULES = {
    "tag_rules": {
        "AI": ["ai", "aigc", "大模型", "模型", "生成式", "gpt", "agent", "智能体"],
        "自媒体": ["自媒体", "内容", "流量", "爆款", "选题", "涨粉", "转化", "私域"],
        "运营": ["运营", "增长", "留存", "投放", "复盘", "策略"],
        "商业": ["商业", "变现", "收入", "成本", "roi", "盈利"],
        "职场": ["职场", "管理", "协作", "沟通", "效率"],
        "科技": ["科技", "芯片", "算法", "互联网", "产品", "工程"],
    },
    "stopwords": [
        "的", "了", "和", "与", "在", "把", "是", "有", "你", "我", "他", "她", "它", "这", "那", "一个", "如何", "为什么", "怎么", "什么",
    ],
    "platform_templates": {
        "wechat": {
            "label": "公众号",
            "style": "专业可信、逻辑清晰、可直接发布",
            "structure": "标题-导语-问题拆解-方法步骤-案例-总结行动",
            "constraints": [
                "避免空话套话，优先给可执行建议",
                "段落长度错落，避免机械重复句式",
                "正文以段落推进为主，小标题与编号仅在必要时少量使用",
            ],
        },
        "xiaohongshu": {
            "label": "小红书",
            "style": "真实体验感、口语化、种草友好",
            "structure": "抓眼标题-场景痛点-亲测过程-结果感受-互动引导",
            "constraints": [
                "首段在3句内进入核心价值",
                "多用具体细节，少用抽象判断",
                "结尾增加互动问题或行动引导",
            ],
        },
        "zhihu": {
            "label": "知乎",
            "style": "观点鲜明、论证完整、信息密度高",
            "structure": "观点先行-背景信息-论据展开-反例边界-结论",
            "constraints": [
                "避免营销腔和口号式表达",
                "增加对比分析与适用边界",
                "尽量给数据或案例支撑",
            ],
        },
        "twitter": {
            "label": "推特/X",
            "style": "短句强节奏、观点尖锐、线程化表达",
            "structure": "总观点-分点线程-行动结论",
            "constraints": [
                "每段尽量短，句式有节奏",
                "优先高信息密度表达",
                "避免过度修辞和陈词滥调",
            ],
        },
    },
    "style_templates": {
        "专业深度": "强调洞察与方法，适合行业分析和知识型内容。",
        "故事共鸣": "强调故事感和人物场景，适合情绪连接和传播。",
        "实操清单": "强调步骤和清单，适合教程、攻略和工具分享。",
        "犀利观点": "强调立场与反直觉洞察，适合观点表达和讨论。",
    },
    "length_templates": {
        "short": "300-500字",
        "medium": "800-1200字",
        "long": "1500-2200字",
    },
    "ai_style_guard": {
        "banned_phrases": [
            "首先",
            "其次",
            "最后",
            "总之",
            "随着",
            "毋庸置疑",
            "值得注意的是",
            "在当今时代",
        ]
    }
}


def _deep_merge(base: dict, ext: dict) -> dict:
    for k, v in (ext or {}).items():
        if isinstance(base.get(k), dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
    return base


def _rules_file_path() -> str:
    return str(cfg.get("ai.local_rules_file", "./data/ai_local_rules.yaml"))


def load_local_rules() -> dict:
    path = _rules_file_path()
    abs_path = os.path.abspath(path)
    mtime = None
    if os.path.exists(abs_path):
        try:
            mtime = os.path.getmtime(abs_path)
        except OSError:
            mtime = None

    if (
        _RULES_CACHE.get("data") is not None
        and _RULES_CACHE.get("path") == abs_path
        and _RULES_CACHE.get("mtime") == mtime
    ):
        return _RULES_CACHE["data"]

    rules = json.loads(json.dumps(DEFAULT_LOCAL_RULES))
    if os.path.exists(abs_path):
        try:
            with open(abs_path, "r", encoding="utf-8") as f:
                ext = yaml.safe_load(f) or {}
            if isinstance(ext, dict):
                rules = _deep_merge(rules, ext)
        except Exception:
            pass

    _RULES_CACHE["path"] = abs_path
    _RULES_CACHE["mtime"] = mtime
    _RULES_CACHE["data"] = rules
    return rules


def get_compose_options() -> dict:
    rules = load_local_rules()
    platforms = rules.get("platform_templates", {})
    styles = rules.get("style_templates", {})
    lengths = rules.get("length_templates", {})
    channel = str(cfg.get("ai.jimeng.channel", "local") or "local").strip().lower()
    req_key = str(cfg.get("ai.jimeng.req_key", "jimeng_t2i_v40")).strip()
    fallback_req_keys = str(cfg.get("ai.jimeng.fallback_req_keys", "jimeng_t2i_v30") or "")
    local_base_url = str(cfg.get("ai.jimeng.local_base_url", "http://127.0.0.1:5100")).strip()
    local_base_urls = _build_local_base_url_candidates()
    local_model = str(cfg.get("ai.jimeng.local_model", "jimeng-4.5")).strip()
    req_key_candidates = _build_req_keys(req_key, fallback_req_keys)
    return {
        "platforms": [
            {
                "key": key,
                "label": value.get("label", key),
                "style": value.get("style", ""),
                "structure": value.get("structure", ""),
            }
            for key, value in platforms.items()
        ],
        "styles": [{"key": k, "label": k, "desc": v} for k, v in styles.items()],
        "lengths": [{"key": k, "label": v} for k, v in lengths.items()],
        "jimeng": {
            "channel": channel,
            "req_key": req_key,
            "fallback_req_keys": [k for k in str(fallback_req_keys).split(",") if str(k).strip()],
            "req_key_candidates": req_key_candidates,
            "local_base_url": local_base_url,
            "local_base_urls": local_base_urls,
            "local_model": local_model,
        },
        "rules_file": _rules_file_path(),
    }


def recommend_tags_from_title(title: str, limit: int = 6) -> List[str]:
    text = (title or "").strip()
    if not text:
        return []

    rules = load_local_rules()
    stopwords = set(rules.get("stopwords", []))
    tag_rules = rules.get("tag_rules", {})

    lower_text = text.lower()
    score = {}

    for tag, kws in tag_rules.items():
        for kw in kws or []:
            kw_str = str(kw).strip()
            if not kw_str:
                continue
            if kw_str.lower() in lower_text:
                score[tag] = score.get(tag, 0) + max(1, len(kw_str) // 2)

    tokens = re.findall(r"[A-Za-z0-9+#]{2,}|[\u4e00-\u9fff]{2,8}", text)
    for token in tokens:
        tk = token.strip().lower()
        if not tk or tk in stopwords:
            continue
        if tk in score:
            score[tk] += 1
        else:
            score[tk] = 1

    sorted_items = sorted(score.items(), key=lambda x: (-x[1], -len(x[0]), x[0]))
    result = []
    for key, _ in sorted_items:
        if len(result) >= limit:
            break
        token = str(key).strip()
        if not token or token in result:
            continue
        if token.isdigit():
            continue
        if len(token) <= 1:
            continue
        result.append(token)
    return result


def get_or_create_profile(session, owner_id: str) -> AIProfile:
    profile = session.query(AIProfile).filter(AIProfile.owner_id == owner_id).first()
    if profile:
        return profile
    now = datetime.now()
    profile = AIProfile(
        id=str(uuid.uuid4()),
        owner_id=owner_id,
        provider_name="openai-compatible",
        model_name=DEFAULT_MODEL,
        base_url=DEFAULT_BASE_URL,
        api_key="",
        temperature=70,
        created_at=now,
        updated_at=now,
    )
    session.add(profile)
    session.commit()
    session.refresh(profile)
    return profile


def update_profile(session, owner_id: str, base_url: str, api_key: str, model_name: str, temperature: int) -> AIProfile:
    profile = get_or_create_profile(session, owner_id)
    profile.base_url = (base_url or DEFAULT_BASE_URL).strip()
    profile.api_key = (api_key or "").strip()
    profile.model_name = (model_name or DEFAULT_MODEL).strip()
    profile.temperature = max(0, min(100, int(temperature)))
    profile.updated_at = datetime.now()
    session.commit()
    session.refresh(profile)
    return profile


def _mask_key(api_key: str) -> str:
    if not api_key:
        return ""
    if len(api_key) <= 8:
        return "*" * len(api_key)
    return f"{api_key[:4]}{'*' * (len(api_key) - 8)}{api_key[-4:]}"


def profile_to_dict(profile: AIProfile, include_secret: bool = False) -> dict:
    return {
        "provider_name": profile.provider_name,
        "model_name": profile.model_name,
        "base_url": profile.base_url,
        "temperature": profile.temperature,
        "api_key": profile.api_key if include_secret else _mask_key(profile.api_key),
    }


def _platform_provider_config(include_secret: bool = False) -> Dict[str, Any]:
    base_url = str(
        cfg.get("ai.provider.base_url", "")
        or os.getenv("AI_PROVIDER_BASE_URL", "")
        or DEFAULT_BASE_URL
    ).strip() or DEFAULT_BASE_URL
    model_name = str(
        cfg.get("ai.provider.model_name", "")
        or os.getenv("AI_PROVIDER_MODEL_NAME", "")
        or DEFAULT_MODEL
    ).strip() or DEFAULT_MODEL
    api_key = str(
        cfg.get("ai.provider.api_key", "")
        or os.getenv("AI_PROVIDER_API_KEY", "")
        or os.getenv("KIMI_API_KEY", "")
        or ""
    ).strip()
    try:
        temperature = int(
            cfg.get("ai.provider.temperature", None)
            or os.getenv("AI_PROVIDER_TEMPERATURE", 70)
            or 70
        )
    except Exception:
        temperature = 70
    temperature = max(0, min(100, temperature))
    return {
        "provider_name": "openai-compatible",
        "base_url": base_url,
        "model_name": model_name,
        "api_key": api_key if include_secret else _mask_key(api_key),
        "temperature": temperature,
        "platform_managed": True,
    }


def get_platform_profile(mask_secret: bool = True) -> Dict[str, Any]:
    return _platform_provider_config(include_secret=not mask_secret)


def _resolve_runtime_provider(profile: Optional[AIProfile]) -> Dict[str, Any]:
    force_platform = bool(cfg.get("ai.provider.force_platform", True))
    platform_cfg = _platform_provider_config(include_secret=True)

    profile_base = str(getattr(profile, "base_url", "") or "").strip()
    profile_model = str(getattr(profile, "model_name", "") or "").strip()
    profile_key = str(getattr(profile, "api_key", "") or "").strip()
    try:
        profile_temp = int(getattr(profile, "temperature", 70) or 70)
    except Exception:
        profile_temp = 70
    profile_temp = max(0, min(100, profile_temp))

    if force_platform:
        return {
            "base_url": platform_cfg["base_url"],
            "model_name": platform_cfg["model_name"],
            "api_key": platform_cfg["api_key"],
            "temperature": platform_cfg["temperature"],
        }

    return {
        "base_url": platform_cfg["base_url"] or profile_base or DEFAULT_BASE_URL,
        "model_name": platform_cfg["model_name"] or profile_model or DEFAULT_MODEL,
        "api_key": platform_cfg["api_key"] or profile_key,
        "temperature": platform_cfg["temperature"] if platform_cfg["temperature"] is not None else profile_temp,
    }


def _strip_html(text: str) -> str:
    raw = text or ""
    raw = re.sub(r"<script[\s\S]*?</script>", " ", raw, flags=re.IGNORECASE)
    raw = re.sub(r"<style[\s\S]*?</style>", " ", raw, flags=re.IGNORECASE)
    raw = re.sub(r"<[^>]+>", " ", raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw


def _length_instruction(length: str) -> str:
    rules = load_local_rules()
    length_map = rules.get("length_templates", {})
    text = str(length or "medium").strip().lower()
    return length_map.get(text, text)


def build_prompt(
    mode: str,
    title: str,
    content: str,
    instruction: str = "",
    create_options: Dict = None,
) -> Tuple[str, str]:
    rules = load_local_rules()
    platform_map = rules.get("platform_templates", {})
    style_map = rules.get("style_templates", {})

    create_options = create_options or {}
    platform = str(create_options.get("platform", "wechat")).strip().lower()
    style = str(create_options.get("style", "专业深度")).strip()
    length = _length_instruction(str(create_options.get("length", "medium")))
    image_count = max(0, int(create_options.get("image_count", 0) or 0))
    audience = str(create_options.get("audience", "")).strip()
    tone = str(create_options.get("tone", "")).strip()

    platform_cfg = platform_map.get(platform, platform_map.get("wechat", {}))
    style_desc = style_map.get(style, style)

    source_text = _strip_html(content)
    if len(source_text) > 6000:
        source_text = source_text[:6000] + " ..."

    base = (
        f"素材标题：{title}\n"
        f"素材正文（摘要）：\n{source_text}\n\n"
    )
    ext = f"用户补充要求：{instruction}\n" if instruction else ""

    anti_ai_rules = (
        "文风与结构约束：\n"
        "1. 正文以自然段叙述为主，不要堆砌小标题。\n"
        "2. 全文最多使用 2 个二级标题，禁止三级及以下标题。\n"
        "3. 非必要不使用有序列表；若必须列步骤，仅允许 1 处且最多 3 条。\n"
        "4. 避免“首先/其次/最后/总之”等模板词，降低 AI 腔。\n"
        "5. 每段必须有新信息，多写具体场景、动作细节、数字或对比。\n"
        "6. 句式长短交替，避免整篇同一节奏。\n"
    )

    if mode == "analyze":
        system = "你是资深内容策略编辑，擅长从传播、结构、受众、转化角度拆解内容。"
        user = (
            base
            + ext
            + "分析目标：提炼爆款点与关键信息，不做全文重写。\n"
            + "请输出 Markdown，结构如下：\n"
            + "## 1) 核心主题（1-2句）\n"
            + "## 2) 爆款点拆解（列表，至少5条）\n"
            + "- 每条包含：爆点描述、证据句、可复用写法\n"
            + "## 3) 重点信息凝练（表格）\n"
            + "| 信息点 | 原文依据 | 受众价值 | 写作建议 |\n"
            + "| --- | --- | --- | --- |\n"
            + "## 4) 风险与短板（列表，至少3条）\n"
            + "## 5) 可执行写作清单（3-5条）\n"
            + "输出要求：分析结果必须以列表和表格为主，避免空泛评价。\n"
            + anti_ai_rules
        )
        return system, user

    if mode == "rewrite":
        system = "你是中文头部新媒体编辑，擅长高质量仿写与重构表达。"
        user = (
            base
            + ext
            + f"改写目标风格：{style_desc}\n"
            + "仿写目标：高仿原文的信息结构、叙事节奏与表达气质，但必须换用新句子，不得逐句照搬。\n"
            + "请直接输出完整改写成稿（标题+正文+结尾行动建议），正文以段落推进。\n"
            + "要求：保留关键观点与逻辑顺序，保留原文的情绪强度与节奏密度。\n"
            + anti_ai_rules
        )
        return system, user

    # create
    platform_constraints = "\n".join([f"- {x}" for x in platform_cfg.get("constraints", [])])
    system = "你是资深内容主笔，目标是写出真实、有信息密度、可直接发布的中文内容。"
    user = (
        base
        + ext
        + f"发布平台：{platform_cfg.get('label', platform)}\n"
        + f"平台风格：{platform_cfg.get('style', '')}\n"
        + f"推荐结构：{platform_cfg.get('structure', '')}\n"
        + f"写作风格：{style_desc}\n"
        + f"目标长度：{length}\n"
        + (f"目标受众：{audience}\n" if audience else "")
        + (f"语气偏好：{tone}\n" if tone else "")
        + (f"配图数量：{image_count}（文末需提供配图建议）\n" if image_count > 0 else "")
        + "平台约束：\n"
        + (platform_constraints if platform_constraints else "- 无")
        + "\n输出要求：\n"
        + "1. 创作目标是全新成稿，不能只是改写原文句子。\n"
        + "2. 直接给可发布成稿，不要输出解释过程。\n"
        + "3. 标题必须具体克制，不用万能标题。\n"
        + "4. 正文以段落叙述为主，避免大量子标题与列表。\n"
        + "5. 每段尽量包含可执行建议、实例或观察结论。\n"
        + (f"6. 文末新增“配图建议”小节，给出 {image_count} 条具体画面描述与中文绘图提示词。\n" if image_count > 0 else "")
        + anti_ai_rules
    )
    return system, user


def _extract_markdown_text_blocks(content: str) -> List[str]:
    text = str(content or "").strip()
    if not text:
        return []
    text = re.sub(r"```[\s\S]*?```", " ", text)
    blocks: List[str] = []
    for chunk in re.split(r"\n\s*\n", text):
        raw = str(chunk or "").strip()
        if not raw:
            continue
        if re.match(r"^!\[[^\]]*\]\((https?://[^)\s]+)[^)]*\)\s*$", raw, flags=re.IGNORECASE):
            continue
        if re.match(r"^<img\b", raw, flags=re.IGNORECASE):
            continue
        raw = re.sub(r"^#{1,6}\s+", "", raw)
        raw = re.sub(r"\|", " ", raw)
        raw = re.sub(r"\s+", " ", raw).strip()
        if len(raw) < 8:
            continue
        blocks.append(raw[:220])
    return blocks


def build_image_prompts(
    title: str,
    platform: str,
    style: str,
    image_count: int,
    content: str = "",
) -> List[str]:
    count = max(0, min(int(image_count or 0), 9))
    if count <= 0:
        return []

    platform_hint_map = {
        "wechat": "professional editorial visual for a trustworthy long-form article",
        "xiaohongshu": "lifestyle social visual with authentic daily-life atmosphere",
        "zhihu": "knowledge-oriented visual with rational and structured mood",
        "twitter": "fast-scrolling social visual with bold focal point and high contrast",
    }
    style_hint_map = {
        "专业深度": "insightful, clean, expert-level visual language",
        "故事共鸣": "human-centered storytelling mood with emotional details",
        "实操清单": "practical, step-by-step, instructional scene composition",
        "犀利观点": "sharp perspective, strong contrast, decisive composition",
    }
    scene_variants = [
        "hero scene with a single clear subject",
        "close-up detail shot with contextual background",
        "workspace scene with depth and layered foreground",
        "people-in-action scene with natural gesture and interaction",
        "before-and-after comparison mood in one frame",
        "minimal still-life composition with symbolic objects",
        "city or office environment with cinematic depth",
        "productivity desk setup with editorial styling",
        "macro detail combined with soft environmental light",
    ]

    topic = str(title or "").strip()
    ascii_keywords = re.findall(r"[A-Za-z0-9][A-Za-z0-9 +#&/_-]{1,40}", topic)
    if ascii_keywords:
        topic_hint = ", ".join(ascii_keywords[:3]).strip(" ,")
    else:
        topic_hint = "the core article topic"

    text_blocks = _extract_markdown_text_blocks(content)
    cover_scene = _compact_text_for_scene(text_blocks[0], max_len=180) if text_blocks else topic_hint
    section_blocks = text_blocks[1:] if len(text_blocks) > 1 else []

    platform_key = str(platform or "wechat").strip().lower()
    platform_hint = platform_hint_map.get(platform_key, "editorial social content visual")
    style_hint = style_hint_map.get(str(style or "").strip(), "clean modern editorial style")

    prompts: List[str] = []
    for i in range(1, count + 1):
        scene_hint = scene_variants[(i - 1) % len(scene_variants)]
        if i == 1:
            scene_focus = f"cover scene for opening section: {cover_scene}"
        elif section_blocks:
            idx = min(len(section_blocks) - 1, int((i - 2) * len(section_blocks) / max(1, count - 1)))
            scene_focus = f"section illustration focus: {_compact_text_for_scene(section_blocks[idx], max_len=180)}"
        else:
            scene_focus = f"section illustration focus around topic: {topic_hint}"
        prompts.append(
            "Create a high-quality editorial illustration. "
            f"Topic: {topic_hint}. "
            f"Platform intent: {platform_hint}. "
            f"Style intent: {style_hint}. "
            f"Scene variation {i}: {scene_hint}. "
            f"Content focus: {scene_focus}. "
            "Use realistic lighting, clear focal subject, layered composition, natural color harmony, "
            "high detail, 4k quality. "
            "English visual semantics only. "
            "No text, no letters, no Chinese characters, no watermark, no logo, no UI."
        )
    return prompts


def build_inline_image_prompt(
    title: str,
    selected_text: str,
    platform: str,
    style: str,
    context_text: str = "",
) -> str:
    platform_hint_map = {
        "wechat": "professional editorial visual for a trustworthy long-form article",
        "xiaohongshu": "lifestyle social visual with authentic daily-life atmosphere",
        "zhihu": "knowledge-oriented visual with rational and structured mood",
        "twitter": "fast-scrolling social visual with bold focal point and high contrast",
    }
    style_hint_map = {
        "专业深度": "insightful, clean, expert-level visual language",
        "故事共鸣": "human-centered storytelling mood with emotional details",
        "实操清单": "practical, step-by-step, instructional scene composition",
        "犀利观点": "sharp perspective, strong contrast, decisive composition",
    }
    platform_key = str(platform or "wechat").strip().lower()
    platform_hint = platform_hint_map.get(platform_key, "editorial social content visual")
    style_hint = style_hint_map.get(str(style or "").strip(), "clean modern editorial style")
    topic_hint = _compact_text_for_scene(title or "article topic", max_len=100) or "article topic"
    selected_hint = _compact_text_for_scene(selected_text, max_len=180) or "core selected paragraph"
    context_hint = _compact_text_for_scene(context_text, max_len=140) or "article context"
    return (
        "Create a high-quality editorial illustration for one paragraph in a long-form article. "
        f"Topic: {topic_hint}. "
        f"Platform intent: {platform_hint}. "
        f"Style intent: {style_hint}. "
        f"Paragraph focus: {selected_hint}. "
        f"Context: {context_hint}. "
        "Use realistic lighting, clear focal subject, layered composition, natural color harmony, high detail, 4k quality. "
        "English visual semantics only. "
        "No text, no letters, no Chinese characters, no watermark, no logo, no UI."
    )


def _is_markdown_image_block(text: str) -> bool:
    block = str(text or "").strip()
    if not block:
        return False
    if re.match(r"^!\[[^\]]*\]\((https?://[^)\s]+)[^)]*\)\s*$", block, flags=re.IGNORECASE):
        return True
    if re.match(r"^<img\b[^>]*>\s*$", block, flags=re.IGNORECASE):
        return True
    return False


def _is_plain_text_block(text: str) -> bool:
    block = str(text or "").strip()
    if not block:
        return False
    if _is_markdown_image_block(block):
        return False
    if re.match(r"^#{1,6}\s+", block):
        return False
    cleaned = re.sub(r"[\[\]()`*_>#|!-]", " ", block)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return len(cleaned) >= 8


def merge_image_urls_into_markdown(content: str, image_urls: List[str]) -> str:
    """
    将图片 URL 以 Markdown 图片语法合并进正文（去重）。
    规则：
    - 第一张图片作为封面图，插入首个正文段落后
    - 其余图片按正文段落均匀分布为内容插图
    """
    base = str(content or "").strip()
    urls = []
    for raw in image_urls or []:
        text = str(raw or "").strip()
        if not text or not re.match(r"^https?://", text, flags=re.IGNORECASE):
            continue
        if text not in urls:
            urls.append(text)
    if not urls:
        return base

    existing_urls = set()
    for m in re.findall(r"!\[[^\]]*\]\((https?://[^)\s]+)[^)]*\)", base, flags=re.IGNORECASE):
        existing_urls.add(str(m).strip())
    for m in re.findall(r"<img[^>]+src=[\"'](https?://[^\"']+)[\"']", base, flags=re.IGNORECASE):
        existing_urls.add(str(m).strip())

    pending = [url for url in urls if url not in existing_urls]
    if not pending:
        return base

    if not base:
        return "\n\n".join([f"![配图{i + 1}]({url})" for i, url in enumerate(pending)])

    blocks = [str(x or "").strip() for x in re.split(r"\n\s*\n", base) if str(x or "").strip()]
    if not blocks:
        return "\n\n".join([f"![配图{i + 1}]({url})" for i, url in enumerate(pending)])

    text_indexes = [i for i, blk in enumerate(blocks) if _is_plain_text_block(blk)]
    cover_url = pending[0]
    content_urls = pending[1:]

    cover_anchor = text_indexes[0] if text_indexes else -1
    insertion_map: Dict[int, List[str]] = {}
    if cover_anchor >= 0:
        insertion_map.setdefault(cover_anchor, []).append(f"![封面图]({cover_url})")
    else:
        insertion_map.setdefault(-1, []).append(f"![封面图]({cover_url})")

    if content_urls:
        candidate_anchors = [idx for idx in text_indexes if idx > cover_anchor]
        if not candidate_anchors:
            candidate_anchors = [len(blocks) - 1]
        for idx, url in enumerate(content_urls, start=1):
            pos = min(
                len(candidate_anchors) - 1,
                int((idx - 1) * len(candidate_anchors) / max(1, len(content_urls))),
            )
            anchor = candidate_anchors[pos]
            insertion_map.setdefault(anchor, []).append(f"![内容配图{idx}]({url})")

    merged_blocks: List[str] = []
    if insertion_map.get(-1):
        merged_blocks.extend(insertion_map[-1])
    for i, blk in enumerate(blocks):
        merged_blocks.append(blk)
        if insertion_map.get(i):
            merged_blocks.extend(insertion_map[i])
    return "\n\n".join([x for x in merged_blocks if str(x or "").strip()])


def call_openai_compatible(profile: AIProfile, system_prompt: str, user_prompt: str) -> str:
    runtime = _resolve_runtime_provider(profile)
    base_url = str(runtime.get("base_url") or "").strip()
    api_key = str(runtime.get("api_key") or "").strip()
    model_name = str(runtime.get("model_name") or "").strip()
    try:
        temperature = int(runtime.get("temperature") or 70)
    except Exception:
        temperature = 70
    temperature = max(0, min(100, temperature))

    if base_url.lower().startswith("mock://") or api_key.lower() in ["mock", "mock-key", "test-mock"]:
        title = "未命名主题"
        m = re.search(r"素材标题：([^\n]+)", user_prompt or "")
        if m:
            title = m.group(1).strip()[:80]
        return (
            f"# {title}\n\n"
            "这是一份模拟生成内容，用于联调与自动化测试。\n\n"
            "## 核心观点\n"
            "1. 明确目标受众与场景。\n"
            "2. 给出可执行步骤与边界。\n"
            "3. 结尾加入行动建议与复盘方式。\n\n"
            "## 执行清单\n"
            "- 提炼要点\n"
            "- 组织结构\n"
            "- 输出发布稿\n"
        )
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="平台 AI 服务未配置，请联系管理员"
        )

    endpoint = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model_name,
        "temperature": float(temperature) / 100.0,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    try:
        # 显式序列化 JSON，确保中文不被转义
        payload_json = json.dumps(payload, ensure_ascii=False)
        resp = requests.post(endpoint, data=payload_json.encode('utf-8'), headers={**headers, 'Content-Type': 'application/json; charset=utf-8'}, timeout=180)
        if resp.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"模型调用失败: {resp.text[:300]}"
            )
        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="模型返回为空"
            )
        return choices[0].get("message", {}).get("content", "").strip()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"模型调用异常: {e}"
        )


def refine_draft(
    profile: AIProfile,
    mode: str,
    draft: str,
    title: str,
    create_options: Dict = None,
    instruction: str = "",
) -> str:
    text = (draft or "").strip()
    if not text:
        return text
    if not cfg.get("ai.refine_enabled", True):
        return text

    create_options = create_options or {}
    rules = load_local_rules()
    banned = rules.get("ai_style_guard", {}).get("banned_phrases", [])
    banned_text = "、".join([str(x) for x in banned if str(x).strip()]) or "无"
    platform = str(create_options.get("platform", "wechat"))
    style = str(create_options.get("style", "专业深度"))
    length = str(create_options.get("length", "medium"))
    extra = (instruction or "").strip()

    system_prompt = "你是中文内容总编，负责把草稿打磨成自然、可信、可发布版本。"
    user_prompt = (
        f"任务类型：{mode}\n"
        f"素材标题：{title}\n"
        f"平台：{platform}\n"
        f"风格：{style}\n"
        f"篇幅：{length}\n"
        + (f"补充要求：{extra}\n" if extra else "")
        + "请在不改事实、不改核心观点的前提下润色下面草稿：\n\n"
        + text
        + "\n\n润色要求：\n"
        + "1. 删除模板腔和官话，保留真实表达。\n"
        + "2. 每段必须有有效信息，不要重复同义句。\n"
        + "3. 优先具体动作、细节、案例和数字。\n"
        + "4. 正文以段落为主，最多 2 个二级标题，不得出现三级标题。\n"
        + "5. 非必要不使用有序列表；若必须使用，仅允许 1 处且最多 3 条。\n"
        + "6. 禁用词：" + banned_text + "\n"
        + "7. 直接输出润色后的最终稿，不解释。\n"
    )

    try:
        refined = call_openai_compatible(profile, system_prompt, user_prompt)
        refined = (refined or "").strip()
        return refined if len(refined) >= max(80, int(len(text) * 0.6)) else text
    except Exception:
        return text


def _looks_like_markdown(text: str) -> bool:
    source = str(text or "")
    if not source.strip():
        return False
    patterns = [
        r"(?m)^\s*#{1,6}\s+\S+",
        r"(?m)^\s*[-*+]\s+\S+",
        r"(?m)^\s*\d+\.\s+\S+",
        r"(?m)\*\*[^*]+\*\*",
        r"(?m)^\s*\|.+\|\s*$",
        r"(?m)!\[[^\]]*\]\([^)]+\)",
        r"(?m)\[[^\]]+\]\([^)]+\)",
    ]
    return any(re.search(p, source) for p in patterns)


def _to_markdown_heading_title(title: str, fallback: str = "AI 草稿") -> str:
    value = str(title or "").strip()
    if not value:
        return fallback
    value = re.sub(r"^#{1,6}\s+", "", value).strip()
    return value or fallback


def _split_plain_paragraphs(text: str) -> List[str]:
    source = str(text or "").replace("\r\n", "\n")
    rows = [str(x or "").strip() for x in re.split(r"\n\s*\n", source)]
    paragraphs = [x for x in rows if x]
    if paragraphs:
        return paragraphs
    rows = [str(x or "").strip() for x in source.split("\n")]
    rows = [x for x in rows if x]
    return rows


def ensure_markdown_content(mode: str, title: str, text: str) -> str:
    source = str(text or "").strip()
    if not source:
        return source
    if _looks_like_markdown(source):
        return source

    heading = _to_markdown_heading_title(title)
    paragraphs = _split_plain_paragraphs(source)
    if not paragraphs:
        return f"# {heading}\n\n{source}"

    bullet_candidates = []
    for para in paragraphs[:3]:
        sentence = re.split(r"[。！？.!?]", para)[0].strip()
        sentence = sentence or para[:42].strip()
        if sentence:
            bullet_candidates.append(sentence[:60])
    bullet_candidates = [x for i, x in enumerate(bullet_candidates) if x and x not in bullet_candidates[:i]]

    if mode == "analyze":
        lines = [
            f"# {heading}｜分析结果",
            "",
            "## 核心结论",
            paragraphs[0],
            "",
            "## 重点信息",
        ]
        if bullet_candidates:
            for idx, item in enumerate(bullet_candidates, start=1):
                lines.append(f"- **要点{idx}**：{item}")
        else:
            lines.append("- **要点1**：请结合原文补充关键信息。")
        if len(paragraphs) > 1:
            lines.extend(["", "## 写作建议", "\n\n".join(paragraphs[1:])])
        return "\n".join(lines).strip()

    lines = [
        f"# {heading}",
        "",
        "## 导语",
        paragraphs[0],
        "",
        "## 正文",
        "\n\n".join(paragraphs[1:]) if len(paragraphs) > 1 else paragraphs[0],
        "",
        "## 关键要点",
    ]
    if bullet_candidates:
        for idx, item in enumerate(bullet_candidates, start=1):
            lines.append(f"- **要点{idx}**：{item}")
    else:
        lines.append("- **要点1**：请根据正文补充。")
    return "\n".join(lines).strip()


def _parse_jimeng_error(raw_error: str) -> Dict[str, str]:
    """从 SDK 抛错文本中尽量提取 code/message/request_id。"""
    text = str(raw_error or "").strip()
    if not text:
        return {"code": "", "message": "未知错误", "request_id": ""}

    # SDK 常见格式：b'{"code":50400,...}'
    if (text.startswith("b'") and text.endswith("'")) or (text.startswith('b"') and text.endswith('"')):
        text = text[2:-1]
        try:
            text = bytes(text, "utf-8").decode("unicode_escape")
        except Exception:
            pass

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        maybe_json = text[start : end + 1]
        try:
            payload = json.loads(maybe_json)
            return {
                "code": str(payload.get("code") or payload.get("status") or ""),
                "message": str(payload.get("message") or text),
                "request_id": str(payload.get("request_id") or ""),
            }
        except Exception:
            pass

    return {"code": "", "message": text, "request_id": ""}


def _is_access_denied(err: Dict[str, str]) -> bool:
    code = str(err.get("code") or "")
    message = str(err.get("message") or "").lower()
    return code == "50400" or "access denied" in message


def _build_req_keys(primary_key: str, fallback_keys_raw: str) -> List[str]:
    keys: List[str] = []
    for item in [primary_key] + str(fallback_keys_raw or "").split(","):
        k = str(item or "").strip()
        if k and k not in keys:
            keys.append(k)
    return keys or ["jimeng_t2i_v40", "jimeng_t2i_v30"]


def _normalize_jimeng_channel(channel: str) -> str:
    value = str(channel or "").strip().lower()
    return value if value in {"local", "api"} else "local"


def _build_local_base_url_candidates() -> List[str]:
    raw_multi = str(
        cfg.get("ai.jimeng.local_base_urls", "")
        or os.getenv("JIMENG_LOCAL_BASE_URLS", "")
        or ""
    ).strip()
    configured_single = str(
        cfg.get("ai.jimeng.local_base_url", "")
        or os.getenv("JIMENG_LOCAL_BASE_URL", "")
        or "http://127.0.0.1:5100"
    ).strip()

    candidates: List[str] = []

    def _append(raw: str) -> None:
        text = str(raw or "").strip().rstrip("/")
        if not text:
            return
        if not re.match(r"^https?://", text, flags=re.IGNORECASE):
            return
        try:
            parsed = urlparse(text)
        except Exception:
            return
        host = str(parsed.hostname or "").strip()
        if not host:
            return
        # 仅允许 5100 端口，屏蔽旧端口配置。
        if parsed.port not in [None, 5100]:
            return
        norm = f"{parsed.scheme}://{host}:5100"
        if norm not in candidates:
            candidates.append(norm)

    if raw_multi:
        for item in re.split(r"[,\s;]+", raw_multi):
            _append(item)

    _append(configured_single)

    for host in ["127.0.0.1", "localhost"]:
        _append(f"http://{host}:5100")

    # 容器内访问宿主机时，127.0.0.1 指向容器本身，补充 host.docker.internal。
    if os.path.exists("/.dockerenv"):
        _append("http://host.docker.internal:5100")

    return candidates


def _extract_local_image_urls(payload: Any) -> List[str]:
    urls: List[str] = []
    data = payload
    if isinstance(payload, dict):
        data = payload.get("data", payload)
    if not isinstance(data, list):
        return urls
    for item in data:
        if not isinstance(item, dict):
            continue
        for key in ("url", "image_url", "img_url"):
            value = str(item.get(key) or "").strip()
            if value.startswith("http://") or value.startswith("https://"):
                urls.append(value)
                break
    return urls


def _generate_images_with_jimeng_local(prompts: List[str]) -> Tuple[List[str], str, bool]:
    if not prompts:
        return [], "", True

    base_urls = _build_local_base_url_candidates()
    if not base_urls:
        return [], "local 模式未配置接口地址", False
    endpoint = str(cfg.get("ai.jimeng.local_endpoint", "/v1/images/generations") or "/v1/images/generations").strip()
    if not endpoint.startswith("/"):
        endpoint = f"/{endpoint}"
    model = str(cfg.get("ai.jimeng.local_model", "") or os.getenv("JIMENG_LOCAL_MODEL", "jimeng-4.5")).strip()
    ratio = str(cfg.get("ai.jimeng.local_ratio", "") or os.getenv("JIMENG_LOCAL_RATIO", "1:1")).strip()
    resolution = str(cfg.get("ai.jimeng.local_resolution", "") or os.getenv("JIMENG_LOCAL_RESOLUTION", "2k")).strip()
    timeout = int(cfg.get("ai.jimeng.local_timeout_seconds", 120) or 120)
    send_extra_params = bool(cfg.get("ai.jimeng.local_send_extra_params", False))
    local_token = str(cfg.get("ai.jimeng.local_token", "") or os.getenv("JIMENG_LOCAL_TOKEN", "")).strip()

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if local_token:
        headers["Authorization"] = f"Bearer {local_token}"

    image_urls: List[str] = []
    errors: List[str] = []
    unreachable = False
    active_base_urls = list(base_urls)
    selected_base_url = ""
    for prompt in prompts:
        payload = {
            "model": model,
            "prompt": prompt,
        }
        # 默认与用户 curl 请求保持一致，必要时再开启扩展参数。
        if send_extra_params:
            if ratio:
                payload["ratio"] = ratio
            if resolution:
                payload["resolution"] = resolution
            payload["response_format"] = "url"
        prompt_done = False
        conn_errors = 0
        for idx, base_url in enumerate(active_base_urls):
            url = f"{base_url}{endpoint}"
            try:
                resp = requests.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=(5, max(20, timeout)),
                )
            except requests.Timeout as e:
                try:
                    # 超时后再给一次更长读超时，避免误判 local 不可用。
                    resp = requests.post(
                        url,
                        json=payload,
                        headers=headers,
                        timeout=(5, max(60, timeout * 2)),
                    )
                except Exception as e2:
                    conn_errors += 1
                    logger.warning(
                        "Jimeng local channel timeout. url=%s read_timeout=%s retry_timeout=%s err=%s",
                        url,
                        max(20, timeout),
                        max(60, timeout * 2),
                        e2,
                    )
                    continue
            except requests.RequestException as e:
                conn_errors += 1
                logger.warning("Jimeng local channel unavailable. url=%s err=%s", url, e)
                continue

            if int(resp.status_code or 0) >= 400:
                text = str(resp.text or "")[:400]
                errors.append(f"local[{base_url}] HTTP {resp.status_code}: {text}")
                continue

            try:
                data = resp.json()
            except Exception:
                errors.append(f"local[{base_url}] 接口返回非 JSON 数据")
                continue

            urls = _extract_local_image_urls(data)
            if urls:
                image_urls.append(urls[0])
                selected_base_url = base_url
                if idx > 0:
                    active_base_urls = [base_url] + [x for x in active_base_urls if x != base_url]
                prompt_done = True
                break

            error_message = ""
            if isinstance(data, dict):
                error_message = str(data.get("message") or data.get("error") or "").strip()
            errors.append(error_message or f"local[{base_url}] 接口未返回图片地址")

        if not prompt_done and conn_errors >= len(active_base_urls):
            unreachable = True

    if image_urls and len(image_urls) == len(prompts):
        suffix = f"，地址 {selected_base_url}" if selected_base_url else ""
        return image_urls, f"即梦 local 生图成功（{len(image_urls)} 张{suffix}）", True

    if image_urls:
        detail = errors[0] if errors else "部分任务未返回图片"
        return image_urls, f"即梦 local 生图部分成功（{len(image_urls)}/{len(prompts)}）：{detail}", True

    if unreachable:
        return [], "即梦 local 接口不可达", False
    detail = errors[0] if errors else "即梦 local 生图失败"
    return [], detail, False


def _generate_images_with_jimeng_api(prompts: List[str]) -> Tuple[List[str], str]:
    ak = str(cfg.get("ai.jimeng.ak", "") or os.getenv("JIMENG_AK", "")).strip()
    sk = str(cfg.get("ai.jimeng.sk", "") or os.getenv("JIMENG_SK", "")).strip()
    req_key = str(cfg.get("ai.jimeng.req_key", "jimeng_t2i_v40")).strip()
    fallback_req_keys = str(cfg.get("ai.jimeng.fallback_req_keys", "jimeng_t2i_v30") or "")
    scale = float(cfg.get("ai.jimeng.scale", 0.5) or 0.5)
    max_retries = int(cfg.get("ai.jimeng.max_retries", 20) or 20)
    candidate_req_keys = _build_req_keys(req_key, fallback_req_keys)

    if not ak or not sk:
        logger.warning("Jimeng disabled due to missing AK/SK. prompts=%s", len(prompts))
        return [], "平台生图服务未就绪，已返回配图提示词（未实际生图）"

    try:
        from volcengine.visual.VisualService import VisualService
    except Exception as e:
        logger.exception("Jimeng dependency import failed: %s", e)
        return [], "平台生图依赖未就绪，已返回配图提示词（未实际生图）"

    visual_service = VisualService()
    visual_service.set_ak(ak)
    visual_service.set_sk(sk)

    image_urls: List[str] = []
    errors: List[str] = []
    effective_req_key = candidate_req_keys[0]
    fallback_used = False

    for prompt in prompts:
        prompt_success = False
        key_candidates = [effective_req_key] + [k for k in candidate_req_keys if k != effective_req_key]

        for idx, current_req_key in enumerate(key_candidates):
            try:
                submit_body = {
                    "req_key": current_req_key,
                    "prompt": prompt,
                    "scale": scale,
                    "force_single": True,
                }
                submit_resp = visual_service.cv_sync2async_submit_task(submit_body)
                if submit_resp.get("code") != 10000:
                    err = {
                        "code": str(submit_resp.get("code") or ""),
                        "message": str(submit_resp.get("message") or submit_resp),
                        "request_id": str(submit_resp.get("request_id") or ""),
                    }
                    if _is_access_denied(err) and idx < len(key_candidates) - 1:
                        continue
                    req_suffix = f"（request_id={err['request_id']}）" if err.get("request_id") else ""
                    errors.append(f"即梦提交失败[{current_req_key}]：{err['message']}{req_suffix}")
                    break

                task_id = submit_resp["data"]["task_id"]
                query_body = {
                    "req_key": current_req_key,
                    "task_id": task_id,
                    "req_json": json.dumps({
                        "return_url": True,
                        "logo_info": {"add_logo": False},
                    }),
                }

                url = ""
                for _ in range(max_retries):
                    query_resp = visual_service.cv_sync2async_get_result(query_body)
                    if query_resp.get("code") != 10000:
                        time.sleep(1.5)
                        continue
                    status_text = (query_resp.get("data") or {}).get("status")
                    if status_text == "done":
                        urls = (query_resp.get("data") or {}).get("image_urls") or []
                        if urls:
                            url = urls[0]
                        break
                    if status_text in ["in_queue", "generating"]:
                        time.sleep(1.5)
                    else:
                        break

                if url:
                    if current_req_key != candidate_req_keys[0]:
                        fallback_used = True
                    effective_req_key = current_req_key
                    image_urls.append(url)
                    prompt_success = True
                else:
                    errors.append(f"即梦任务未返回图片链接[{current_req_key}]")
                break
            except Exception as e:
                err = _parse_jimeng_error(str(e))
                logger.warning(
                    "Jimeng call failed. req_key=%s code=%s request_id=%s msg=%s",
                    current_req_key,
                    err.get("code", ""),
                    err.get("request_id", ""),
                    err.get("message", ""),
                )
                if _is_access_denied(err) and idx < len(key_candidates) - 1:
                    continue
                req_suffix = f"（request_id={err['request_id']}）" if err.get("request_id") else ""
                errors.append(f"即梦调用失败[{current_req_key}]：{err['message']}{req_suffix}")
                break

        if not prompt_success and len(key_candidates) > 1 and not errors:
            errors.append("即梦生图失败：平台已自动尝试可用模型")

    notices: List[str] = []
    if image_urls:
        notices.append(f"即梦生图成功，使用模型 {effective_req_key}")
    if fallback_used:
        notices.append(f"检测到默认模型不可用，已自动回退到 {effective_req_key}")
    if errors:
        notices.append("；".join(errors[:2]))
    return image_urls, "；".join([n for n in notices if n])


def generate_images_with_jimeng(prompts: List[str]) -> Tuple[List[str], str]:
    """
    即梦双通道：
    - local：优先调用本地 jimeng-api 容器
    - api：走 AK/SK 直连
    默认 local，local 不可用时自动回退 api。
    """
    if not prompts:
        return [], ""

    channel = _normalize_jimeng_channel(cfg.get("ai.jimeng.channel", "local"))
    if channel == "api":
        return _generate_images_with_jimeng_api(prompts)

    local_urls, local_notice, local_ok = _generate_images_with_jimeng_local(prompts)
    if local_ok and local_urls:
        return local_urls, local_notice

    api_urls, api_notice = _generate_images_with_jimeng_api(prompts)
    if api_urls:
        fallback_notice = "local 通道不可用，已自动回退 AK/SK 通道"
        if local_notice:
            fallback_notice = f"{fallback_notice}（{local_notice}）"
        merged = "；".join([x for x in [fallback_notice, api_notice] if x])
        return api_urls, merged

    merged = "；".join([x for x in [local_notice, api_notice] if x])
    if not merged:
        merged = "即梦生图不可用，已返回配图提示词"
    return [], merged


def _compact_text_for_scene(text: str, max_len: int = 120) -> str:
    source = str(text or "").strip()
    if not source:
        return ""
    source = re.sub(r"\s+", " ", source)
    if len(source) <= max_len:
        return source
    return source[:max_len].rstrip() + "..."


def build_compose_request_signature(
    mode: str,
    instruction: str = "",
    create_options: Dict = None,
) -> str:
    options = create_options or {}
    payload = {
        "mode": str(mode or "").strip().lower(),
        "instruction": str(instruction or "").strip(),
        "platform": str(options.get("platform", "wechat")).strip().lower(),
        "style": str(options.get("style", "专业深度")).strip(),
        "length": str(options.get("length", "medium")).strip().lower(),
        "image_count": max(0, int(options.get("image_count", 0) or 0)),
        "audience": str(options.get("audience", "")).strip(),
        "tone": str(options.get("tone", "")).strip(),
        "generate_images": bool(options.get("generate_images", True)),
    }
    digest = hashlib.sha1(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    return digest


def _parse_compose_result_json(row: AIComposeResult) -> Dict[str, Any]:
    try:
        payload = json.loads(str(row.result_json or "{}"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _parse_compose_request_payload_json(row: AIComposeResult) -> Dict[str, Any]:
    try:
        payload = json.loads(str(row.request_payload or "{}"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def serialize_compose_result_row(row: AIComposeResult) -> Dict[str, Any]:
    if not row:
        return {}
    payload = _parse_compose_result_json(row)
    request_payload = _parse_compose_request_payload_json(row)
    result = {
        "id": row.id,
        "owner_id": row.owner_id,
        "article_id": row.article_id,
        "mode": row.mode,
        "title": row.title or "",
        "source_title": row.source_title or "",
        "request_signature": row.request_signature or "",
        "request_payload": request_payload,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }
    result.update(payload)
    return result


def get_cached_compose_result(
    session,
    owner_id: str,
    article_id: str,
    mode: str,
    request_signature: str = "",
) -> Optional[Dict[str, Any]]:
    owner = str(owner_id or "").strip()
    article = str(article_id or "").strip()
    mode_key = str(mode or "").strip().lower()
    if not owner or not article or not mode_key:
        return None
    query = session.query(AIComposeResult).filter(
        AIComposeResult.owner_id == owner,
        AIComposeResult.article_id == article,
        AIComposeResult.mode == mode_key,
    )
    if request_signature:
        query = query.filter(AIComposeResult.request_signature == str(request_signature).strip())
    row = query.order_by(AIComposeResult.updated_at.desc()).first()
    if not row:
        return None
    data = serialize_compose_result_row(row)
    data["from_cache"] = True
    data["cached_at"] = data.get("updated_at")
    return data


def upsert_compose_result(
    session,
    owner_id: str,
    article_id: str,
    mode: str,
    title: str,
    source_title: str,
    request_signature: str,
    request_payload: Dict[str, Any],
    result_payload: Dict[str, Any],
) -> Dict[str, Any]:
    owner = str(owner_id or "").strip()
    article = str(article_id or "").strip()
    mode_key = str(mode or "").strip().lower()
    now = datetime.now()
    if not owner or not article or not mode_key:
        return {}
    query = session.query(AIComposeResult).filter(
        AIComposeResult.owner_id == owner,
        AIComposeResult.article_id == article,
        AIComposeResult.mode == mode_key,
    )
    if request_signature:
        query = query.filter(AIComposeResult.request_signature == str(request_signature).strip())
    row = query.first()
    if not row:
        row = AIComposeResult(
            id=str(uuid.uuid4()),
            owner_id=owner,
            article_id=article,
            mode=mode_key,
            created_at=now,
        )
        session.add(row)
    row.title = str(title or "").strip()
    row.source_title = str(source_title or "").strip()
    row.request_signature = str(request_signature or "").strip()
    row.request_payload = json.dumps(request_payload or {}, ensure_ascii=False)
    row.result_json = json.dumps(result_payload or {}, ensure_ascii=False)
    row.updated_at = now
    return serialize_compose_result_row(row)


def _draft_dir() -> str:
    path = str(cfg.get("ai.draft_dir", "./data/ai_drafts"))
    return os.path.abspath(path)


def _draft_file(owner_id: str) -> str:
    safe_owner = re.sub(r"[^a-zA-Z0-9_\-.]", "_", str(owner_id or "anonymous"))
    return os.path.join(_draft_dir(), f"{safe_owner}.jsonl")


def save_local_draft(
    owner_id: str,
    article_id: str,
    title: str,
    content: str,
    platform: str = "wechat",
    mode: str = "create",
    metadata: Dict = None,
) -> Dict:
    os.makedirs(_draft_dir(), exist_ok=True)
    record = {
        "id": str(uuid.uuid4()),
        "owner_id": owner_id,
        "article_id": article_id,
        "title": (title or "").strip(),
        "content": (content or "").strip(),
        "platform": (platform or "wechat").strip().lower(),
        "mode": (mode or "create").strip().lower(),
        "created_at": datetime.now().isoformat(),
        "metadata": metadata or {},
    }
    with open(_draft_file(owner_id), "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def list_local_drafts(owner_id: str, limit: int = 20) -> List[Dict]:
    path = _draft_file(owner_id)
    if not os.path.exists(path):
        return []
    rows: List[Dict] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                text = (line or "").strip()
                if not text:
                    continue
                try:
                    rows.append(json.loads(text))
                except Exception:
                    continue
    except Exception:
        return []
    rows = rows[-max(1, int(limit or 20)):]
    rows.reverse()
    return rows


def _read_draft_rows(owner_id: str) -> List[Dict]:
    path = _draft_file(owner_id)
    if not os.path.exists(path):
        return []
    rows: List[Dict] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                text = (line or "").strip()
                if not text:
                    continue
                try:
                    rows.append(json.loads(text))
                except Exception:
                    continue
    except Exception:
        return []
    return rows


def _write_draft_rows(owner_id: str, rows: List[Dict]) -> None:
    path = _draft_file(owner_id)
    os.makedirs(_draft_dir(), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def get_local_draft(owner_id: str, draft_id: str) -> Optional[Dict]:
    target = str(draft_id or "").strip()
    if not target:
        return None
    rows = _read_draft_rows(owner_id)
    for row in reversed(rows):
        if str(row.get("id") or "").strip() == target:
            return row
    return None


def update_local_draft(
    owner_id: str,
    draft_id: str,
    title: str,
    content: str,
    platform: str = "wechat",
    mode: str = "create",
    metadata: Dict = None,
) -> Optional[Dict]:
    target = str(draft_id or "").strip()
    if not target:
        return None
    rows = _read_draft_rows(owner_id)
    found = None
    next_rows: List[Dict] = []
    for row in rows:
        if str(row.get("id") or "").strip() != target:
            next_rows.append(row)
            continue
        updated = dict(row)
        updated["title"] = str(title or "").strip()
        updated["content"] = str(content or "").strip()
        updated["platform"] = (platform or "wechat").strip().lower()
        updated["mode"] = (mode or "create").strip().lower()
        if metadata is not None:
            updated["metadata"] = metadata
        updated["updated_at"] = datetime.now().isoformat()
        found = updated
        next_rows.append(updated)
    if not found:
        return None
    _write_draft_rows(owner_id, next_rows)
    return found


def delete_local_draft(owner_id: str, draft_id: str) -> bool:
    target = str(draft_id or "").strip()
    if not target:
        return False
    rows = _read_draft_rows(owner_id)
    next_rows = [row for row in rows if str(row.get("id") or "").strip() != target]
    if len(next_rows) == len(rows):
        return False
    _write_draft_rows(owner_id, next_rows)
    return True


def _parse_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except Exception:
            return None
    if dt.tzinfo is not None:
        dt = dt.astimezone().replace(tzinfo=None)
    return dt


def _pick_value(item: Any, field: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(field, default)
    return getattr(item, field, default)


def summarize_activity_metrics(
    drafts: List[Dict],
    publish_tasks: List[Any],
    days: int = 7,
    now: Optional[datetime] = None,
) -> Dict:
    days = max(1, int(days or 7))
    now = now or datetime.now()
    start = (now - timedelta(days=days - 1)).date()
    day_keys = [(start + timedelta(days=i)).isoformat() for i in range(days)]
    buckets = {
        key: {
            "date": key,
            "drafts": 0,
            "publish_success": 0,
            "publish_failed": 0,
        }
        for key in day_keys
    }

    draft_count = 0
    for row in drafts or []:
        dt = _parse_datetime(_pick_value(row, "created_at"))
        if not dt:
            continue
        key = dt.date().isoformat()
        if key not in buckets:
            continue
        buckets[key]["drafts"] += 1
        draft_count += 1

    publish_total = 0
    publish_success = 0
    publish_failed = 0
    publish_pending = 0
    for task in publish_tasks or []:
        dt = _parse_datetime(_pick_value(task, "created_at"))
        if not dt:
            continue
        key = dt.date().isoformat()
        if key not in buckets:
            continue

        publish_total += 1
        status = str(_pick_value(task, "status", "") or "").strip().lower()
        if status == "success":
            publish_success += 1
            buckets[key]["publish_success"] += 1
        elif status == "failed":
            publish_failed += 1
            buckets[key]["publish_failed"] += 1
        elif status in ["pending", "processing"]:
            publish_pending += 1

    finished = publish_success + publish_failed
    success_rate = round((publish_success / finished) * 100, 2) if finished > 0 else None
    return {
        "days": days,
        "draft_count_7d": draft_count,
        "avg_daily_draft": round(draft_count / float(days), 2),
        "publish_total_7d": publish_total,
        "publish_success_7d": publish_success,
        "publish_failed_7d": publish_failed,
        "publish_pending_7d": publish_pending,
        "publish_success_rate_7d": success_rate,
        "trend": [buckets[k] for k in day_keys],
    }


def _markdown_to_wechat_html(content: str) -> str:
    text = (content or "").strip()
    if not text:
        return ""
    try:
        from markdown import markdown

        return markdown(text, extensions=["extra", "nl2br", "sane_lists"])
    except Exception:
        escaped = html.escape(text).replace("\n", "<br />")
        return f"<p>{escaped}</p>"


def _contains_html_image(html_content: str) -> bool:
    return bool(re.search(r"<img\b", str(html_content or ""), flags=re.IGNORECASE))


def _extract_img_attr(img_tag: str, attr_name: str) -> str:
    tag = str(img_tag or "")
    attr = re.escape(str(attr_name or "").strip())
    if not attr:
        return ""
    quoted = re.search(rf'\b{attr}\s*=\s*["\']([^"\']+)["\']', tag, flags=re.IGNORECASE)
    if quoted:
        return str(quoted.group(1) or "").strip()
    unquoted = re.search(rf"\b{attr}\s*=\s*([^\s>]+)", tag, flags=re.IGNORECASE)
    if unquoted:
        return str(unquoted.group(1) or "").strip().strip('"').strip("'")
    return ""


def _normalize_wechat_img_tags(html_content: str) -> str:
    """
    将 data-src/data-original 归一到 src，避免微信侧识别不到正文图片。
    """
    text = str(html_content or "")
    if not text:
        return ""

    def _repl(match: re.Match) -> str:
        tag = str(match.group(0) or "")
        if re.search(r"\bsrc\s*=", tag, flags=re.IGNORECASE):
            return tag
        fallback_src = (
            _extract_img_attr(tag, "data-src")
            or _extract_img_attr(tag, "data-original")
            or _extract_img_attr(tag, "data-url")
        )
        if not fallback_src:
            return tag
        safe_src = html.escape(fallback_src, quote=True)
        if tag.endswith("/>"):
            return tag[:-2] + f' src="{safe_src}" />'
        if tag.endswith(">"):
            return tag[:-1] + f' src="{safe_src}">'
        return tag + f' src="{safe_src}"'

    return re.sub(r"<img\b[^>]*>", _repl, text, flags=re.IGNORECASE)


def _extract_image_urls_from_html(html_content: str) -> List[str]:
    text = str(html_content or "")
    if not text:
        return []
    urls: List[str] = []
    for tag in re.findall(r"<img\b[^>]*>", text, flags=re.IGNORECASE):
        src = _extract_img_attr(tag, "src")
        if src:
            urls.append(src)
            continue
        fallback = (
            _extract_img_attr(tag, "data-src")
            or _extract_img_attr(tag, "data-original")
            or _extract_img_attr(tag, "data-url")
        )
        if fallback:
            urls.append(fallback)
    deduped: List[str] = []
    for url in urls:
        clean = str(url or "").strip()
        if not clean:
            continue
        if clean not in deduped:
            deduped.append(clean)
    return deduped


def _pick_first_http_image_url(urls: List[str]) -> str:
    for url in urls or []:
        text = str(url or "").strip()
        if re.match(r"^https?://", text, flags=re.IGNORECASE):
            return text
    return ""


def _trim_utf8_bytes(text: str, max_bytes: int) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    limit = max(1, int(max_bytes or 1))
    if len(raw.encode("utf-8")) <= limit:
        return raw
    parts: List[str] = []
    used = 0
    for ch in raw:
        chunk = ch.encode("utf-8")
        if used + len(chunk) > limit:
            break
        parts.append(ch)
        used += len(chunk)
    return "".join(parts).strip()


def _safe_wechat_title(raw_title: str) -> str:
    """
    清理并截断标题以符合微信公众号要求

    微信公众号标题限制：
    - 官方文档：不超过 64 个字符
    - 实际测试：不同公众号对长度和特殊字符校验更严格
    - 本函数：保守截断到 50 bytes，避免 errcode=45003
    """
    # 1. 清理控制字符和特殊符号
    title = str(raw_title or "").strip()
    # 移除换行符、制表符、回车等控制字符
    title = re.sub(r'[\r\n\t\v\f]', ' ', title)
    # 移除其他控制字符（Unicode 控制字符范围）
    title = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', title)
    # 压缩多个空格为单个空格
    title = re.sub(r'\s+', ' ', title).strip()

    # 2. 截断字节长度（50 bytes 是保守值，避免不同公众号的严格限制）
    title = _trim_utf8_bytes(title, max_bytes=50)

    # 3. 确保有有效标题
    return title or "未命名草稿"


def _is_wechat_cdn_url(url: str) -> bool:
    text = str(url or "").strip().lower()
    return "mmbiz.qpic.cn" in text or "mmbiz.qlogo.cn" in text


def _extract_url_from_payload(payload: Any) -> str:
    """
    从微信返回 payload 中尽可能提取图床 URL。
    """
    candidates: List[str] = []

    def _walk(node: Any) -> None:
        if isinstance(node, dict):
            for v in node.values():
                _walk(v)
            return
        if isinstance(node, list):
            for v in node:
                _walk(v)
            return
        if isinstance(node, str):
            text = node.strip()
            if re.match(r"^https?://", text, flags=re.IGNORECASE):
                candidates.append(text)
                return
            for m in re.findall(r"https?://[^\s\"'<>]+", text, flags=re.IGNORECASE):
                candidates.append(str(m).strip())

    _walk(payload)
    for url in candidates:
        if _is_wechat_cdn_url(url):
            return url
    for url in candidates:
        if re.match(r"^https?://", str(url), flags=re.IGNORECASE):
            return str(url)
    return ""


def _set_img_attr(tag: str, attr: str, value: str) -> str:
    text = str(tag or "")
    name = str(attr or "").strip()
    if not name:
        return text
    safe_value = html.escape(str(value or "").strip(), quote=True)
    quoted_pattern = rf'(\b{name}\s*=\s*)(["\']).*?\2'
    if re.search(quoted_pattern, text, flags=re.IGNORECASE | re.DOTALL):
        return re.sub(quoted_pattern, rf'\1"{safe_value}"', text, count=1, flags=re.IGNORECASE | re.DOTALL)
    unquoted_pattern = rf"(\b{name}\s*=\s*)([^\s>]+)"
    if re.search(unquoted_pattern, text, flags=re.IGNORECASE):
        return re.sub(unquoted_pattern, rf'\1"{safe_value}"', text, count=1, flags=re.IGNORECASE)
    if text.endswith("/>"):
        return text[:-2] + f' {name}="{safe_value}" />'
    if text.endswith(">"):
        return text[:-1] + f' {name}="{safe_value}">'
    return text + f' {name}="{safe_value}"'


def _try_upload_article_img_to_wechat(token: str, cookie: str, image_url: str) -> Tuple[str, str]:
    """
    通过公众号后台编辑器接口 uploadimg2cdn 上传正文插图，返回微信图床 URL。
    """
    src = str(image_url or "").strip()
    if not src:
        return "", "正文图片 URL 为空"
    if not re.match(r"^https?://", src, flags=re.IGNORECASE):
        return "", "正文图片 URL 非 http(s)"
    if _is_wechat_cdn_url(src):
        return src, ""
    def _parse_upload_resp(resp: requests.Response) -> Tuple[str, str]:
        if resp.status_code >= 400:
            return "", f"正文图片上传 HTTP {resp.status_code}"
        payload: Dict[str, Any] = {}
        try:
            payload = resp.json()
        except Exception:
            return "", "正文图片上传返回非 JSON"

        base_resp = payload.get("base_resp") if isinstance(payload.get("base_resp"), dict) else {}
        ret_raw = payload.get("ret", None)
        if ret_raw is None:
            ret_raw = base_resp.get("ret", -1)
        try:
            ret = int(ret_raw)
        except Exception:
            ret = -1
        if ret != 0:
            err = (
                payload.get("errmsg")
                or payload.get("msg")
                or payload.get("error_msg")
                or base_resp.get("err_msg")
                or base_resp.get("errmsg")
                or "unknown"
            )
            return "", f"正文图片上传失败(ret={ret}): {err}"
        wx_url = str(payload.get("url") or payload.get("cdn_url") or "").strip()
        if not wx_url:
            wx_url = _extract_url_from_payload(payload)
        if not wx_url:
            return "", "正文图片上传成功但未返回 URL"
        return wx_url, ""

    def _upload_image_bytes_via_filetransfer() -> Tuple[str, str]:
        try:
            download_candidates = [
                {
                    "User-Agent": str(cfg.get("user_agent", "Mozilla/5.0")),
                    "Referer": "https://mp.weixin.qq.com/",
                    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
                },
                {
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
                    "Referer": "https://dreamina.capcut.com/",
                    "Origin": "https://dreamina.capcut.com",
                    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
                },
                {
                    "User-Agent": "curl/8.7.1",
                    "Accept": "*/*",
                },
            ]
            image_resp = None
            download_errors: List[str] = []
            for header_idx, img_headers in enumerate(download_candidates, start=1):
                try:
                    trial_resp = requests.get(src, headers=img_headers, timeout=25)
                except Exception as e:
                    download_errors.append(f"h{header_idx} 请求异常: {e}")
                    continue
                if trial_resp.status_code >= 400 or not trial_resp.content:
                    download_errors.append(f"h{header_idx} HTTP {trial_resp.status_code}")
                    continue
                image_resp = trial_resp
                break
            if image_resp is None:
                detail = "；".join(download_errors[:3]) if download_errors else "unknown"
                return "", f"图片下载失败 {detail}"

            upload_api = "https://mp.weixin.qq.com/cgi-bin/filetransfer"
            headers = {
                "Cookie": cookie,
                "User-Agent": str(cfg.get("user_agent", "Mozilla/5.0")),
                "Referer": f"https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit&action=edit&type=10&token={token}&lang=zh_CN",
            }
            mime = image_resp.headers.get("Content-Type", "image/jpeg")
            filename = f"body_{int(time.time() * 1000)}.jpg"
            files = {
                "file": (filename, image_resp.content, mime),
            }

            errors: List[str] = []
            for scene in ["2", "1", "8"]:
                params = {
                    "action": "upload_material",
                    "f": "json",
                    "scene": scene,
                    "writetype": "doublewrite",
                    "token": token,
                    "lang": "zh_CN",
                }
                resp = requests.post(upload_api, params=params, headers=headers, files=files, timeout=40)
                if resp.status_code >= 400:
                    errors.append(f"scene={scene} HTTP {resp.status_code}")
                    continue
                try:
                    payload = resp.json()
                except Exception:
                    errors.append(f"scene={scene} 非 JSON")
                    continue

                base_resp = payload.get("base_resp") if isinstance(payload.get("base_resp"), dict) else {}
                ret_raw = payload.get("ret", None)
                if ret_raw is None:
                    ret_raw = base_resp.get("ret", 0)
                try:
                    ret = int(ret_raw)
                except Exception:
                    ret = 0
                if ret not in [0]:
                    err = (
                        payload.get("errmsg")
                        or payload.get("msg")
                        or payload.get("error_msg")
                        or base_resp.get("err_msg")
                        or base_resp.get("errmsg")
                        or "unknown"
                    )
                    errors.append(f"scene={scene} ret={ret} err={err}")
                    continue

                wx_url = str(payload.get("url") or payload.get("cdn_url") or payload.get("content") or "").strip()
                if not wx_url:
                    wx_url = _extract_url_from_payload(payload)
                if wx_url and re.match(r"^https?://", wx_url, flags=re.IGNORECASE):
                    return wx_url, ""
                errors.append(f"scene={scene} 未返回 URL")
            return "", "；".join(errors[:3]) if errors else "filetransfer 未返回 URL"
        except Exception as e:
            return "", f"filetransfer 回退异常: {e}"

    try:
        endpoint = "https://mp.weixin.qq.com/cgi-bin/uploadimg2cdn"
        params = {
            "token": token,
            "lang": "zh_CN",
            "f": "json",
            "ajax": "1",
        }
        data = {
            "imgurl": src,
            "t": "ajax-editor-upload-img",
        }
        headers = {
            "Cookie": cookie,
            "User-Agent": str(cfg.get("user_agent", "Mozilla/5.0")),
            "Referer": f"https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit&action=edit&type=10&token={token}&lang=zh_CN",
            "X-Requested-With": "XMLHttpRequest",
        }

        # 策略1：POST（编辑器常用）
        post_resp = requests.post(endpoint, params=params, data=data, headers=headers, timeout=40)
        wx_url, err = _parse_upload_resp(post_resp)
        if wx_url:
            return wx_url, ""

        # 策略2：GET（部分账号/版本兼容）
        get_params = dict(params)
        get_params.update(data)
        get_resp = requests.get(endpoint, params=get_params, headers=headers, timeout=40)
        wx_url2, err2 = _parse_upload_resp(get_resp)
        if wx_url2:
            return wx_url2, ""
        wx_url3, err3 = _upload_image_bytes_via_filetransfer()
        if wx_url3:
            return wx_url3, ""
        return "", f"{err}; fallback_get={err2}; fallback_file={err3}"
    except Exception as e:
        return "", f"正文图片上传异常: {e}"


def _rewrite_html_images_to_wechat_cdn(content_html: str, token: str, cookie: str) -> Tuple[str, Dict[str, str], List[str]]:
    text = str(content_html or "")
    if not text:
        return "", {}, []
    mapping: Dict[str, str] = {}
    warnings: List[str] = []

    def _repl(match: re.Match) -> str:
        tag = str(match.group(0) or "")
        src = (
            _extract_img_attr(tag, "src")
            or _extract_img_attr(tag, "data-src")
            or _extract_img_attr(tag, "data-original")
            or _extract_img_attr(tag, "data-url")
        )
        if not src:
            return tag
        src = str(src).strip()
        if not src or not re.match(r"^https?://", src, flags=re.IGNORECASE):
            return tag
        if _is_wechat_cdn_url(src):
            return tag
        if src in mapping:
            target = mapping[src]
        else:
            target, err = _try_upload_article_img_to_wechat(token, cookie, src)
            if not target:
                warnings.append(f"{src[:80]} -> {err}")
                return tag
            mapping[src] = target
        updated = _set_img_attr(tag, "src", target)
        updated = _set_img_attr(updated, "data-src", target)
        updated = _set_img_attr(updated, "data-original", target)
        return updated

    rewritten = re.sub(r"<img\b[^>]*>", _repl, text, flags=re.IGNORECASE)
    return rewritten, mapping, warnings


def _ensure_wechat_body_has_image(html_content: str, cover_url: str) -> Tuple[str, bool]:
    """
    微信草稿要求正文中包含图片。
    当正文无图且提供了封面图 URL 时，自动把封面图插入正文首段。
    """
    body = str(html_content or "").strip()
    if _contains_html_image(body):
        return body, False

    url = str(cover_url or "").strip()
    if not re.match(r"^https?://", url, flags=re.IGNORECASE):
        return body, False

    safe_url = html.escape(url, quote=True)
    injected = f'<p><img src="{safe_url}" alt="cover" /></p>'
    return (injected + body), True


PUBLISH_STATUS_PENDING = "pending"
PUBLISH_STATUS_PROCESSING = "processing"
PUBLISH_STATUS_SUCCESS = "success"
PUBLISH_STATUS_FAILED = "failed"
_WECHAT_OPENAPI_TOKEN_CACHE: Dict[str, Dict[str, Any]] = {}


def _wechat_auth(owner_id: str = "", session=None) -> Tuple[str, str]:
    # 优先使用用户维度授权，保留全局配置作为兼容回退
    try:
        from core.wechat_auth_service import get_token_cookie
        from core.db import DB

        local_session = session
        should_close = False
        if local_session is None:
            local_session = DB.get_session()
            should_close = True
        token, cookie = get_token_cookie(local_session, owner_id=owner_id, allow_global_fallback=True)
        if should_close and hasattr(local_session, "close"):
            local_session.close()
        return token, cookie
    except Exception:
        try:
            from driver.token import wx_cfg

            token = str(wx_cfg.get("token", "")).strip()
            cookie = str(wx_cfg.get("cookie", "")).strip()
            return token, cookie
        except Exception:
            return "", ""


def _try_upload_cover_media_id(token: str, cookie: str, cover_url: str) -> Tuple[str, str]:
    url = str(cover_url or "").strip()
    if not url:
        return "", ""
    try:
        image_resp = requests.get(url, timeout=20)
        if image_resp.status_code >= 400 or not image_resp.content:
            return "", "封面下载失败"
        upload_api = "https://mp.weixin.qq.com/cgi-bin/filetransfer"
        params = {
            "action": "upload_material",
            "f": "json",
            "scene": "8",
            "writetype": "doublewrite",
            "token": token,
            "lang": "zh_CN",
        }
        headers = {
            "Cookie": cookie,
            "User-Agent": str(cfg.get("user_agent", "Mozilla/5.0")),
            "Referer": f"https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit&action=edit&type=10&token={token}&lang=zh_CN",
        }
        files = {
            "file": ("cover.jpg", image_resp.content, image_resp.headers.get("Content-Type", "image/jpeg")),
        }
        resp = requests.post(upload_api, params=params, headers=headers, files=files, timeout=30)
        payload = {}
        try:
            payload = resp.json()
        except Exception:
            return "", "封面上传返回非 JSON"
        media_id = str(payload.get("media_id") or payload.get("content") or "").strip()
        if media_id:
            return media_id, ""
        return "", f'封面上传失败: {payload.get("errmsg") or payload.get("msg") or "unknown"}'
    except Exception as e:
        return "", f"封面上传异常: {e}"


def _get_wechat_openapi_access_token(app_id: str, app_secret: str) -> Tuple[str, str]:
    appid = str(app_id or "").strip()
    secret = str(app_secret or "").strip()
    if not appid or not secret:
        return "", "缺少 appid/appsecret"
    cache_key = f"{appid}:{hashlib.sha1(secret.encode('utf-8')).hexdigest()[:12]}"
    now_ts = int(time.time())
    cached = _WECHAT_OPENAPI_TOKEN_CACHE.get(cache_key) or {}
    cached_token = str(cached.get("token") or "").strip()
    expire_at = int(cached.get("expire_at") or 0)
    if cached_token and expire_at > now_ts + 30:
        return cached_token, ""

    token_url = "https://api.weixin.qq.com/cgi-bin/token"
    params = {
        "grant_type": "client_credential",
        "appid": appid,
        "secret": secret,
    }
    try:
        resp = requests.get(token_url, params=params, timeout=(5, 25))
    except Exception as e:
        return "", f"获取 access_token 异常: {e}"
    if int(resp.status_code or 0) >= 400:
        return "", f"获取 access_token HTTP {resp.status_code}"
    try:
        payload = resp.json()
    except Exception:
        return "", "获取 access_token 返回非 JSON"
    token = str(payload.get("access_token") or "").strip()
    if not token:
        err = str(payload.get("errmsg") or payload.get("errcode") or payload)[:260]
        return "", f"获取 access_token 失败: {err}"
    expires_in = int(payload.get("expires_in") or 7200)
    _WECHAT_OPENAPI_TOKEN_CACHE[cache_key] = {
        "token": token,
        "expire_at": now_ts + max(60, expires_in - 120),
    }
    return token, ""


def _download_image_bytes(image_url: str) -> Tuple[bytes, str, str]:
    src = str(image_url or "").strip()
    if not src:
        return b"", "", "图片 URL 为空"
    if not re.match(r"^https?://", src, flags=re.IGNORECASE):
        return b"", "", "图片 URL 非 http(s)"
    download_candidates = [
        {
            "User-Agent": str(cfg.get("user_agent", "Mozilla/5.0")),
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        },
        {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            "Referer": "https://dreamina.capcut.com/",
            "Origin": "https://dreamina.capcut.com",
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        },
        {
            "User-Agent": "curl/8.7.1",
            "Accept": "*/*",
        },
    ]
    errors: List[str] = []
    for idx, headers in enumerate(download_candidates, start=1):
        try:
            resp = requests.get(src, headers=headers, timeout=(5, 30))
        except Exception as e:
            errors.append(f"h{idx} 请求异常: {e}")
            continue
        if int(resp.status_code or 0) >= 400 or not resp.content:
            errors.append(f"h{idx} HTTP {resp.status_code}")
            continue
        mime = str(resp.headers.get("Content-Type") or "image/jpeg").split(";")[0].strip() or "image/jpeg"
        return bytes(resp.content), mime, ""
    return b"", "", "；".join(errors[:3]) if errors else "下载失败"


def _compress_image_bytes(raw: bytes, max_size: int) -> bytes:
    data = bytes(raw or b"")
    if not data or len(data) <= max_size:
        return data
    try:
        from PIL import Image
    except Exception:
        return data
    try:
        image = Image.open(io.BytesIO(data))
        if image.mode != "RGB":
            image = image.convert("RGB")
        quality = 88
        width, height = image.size
        scale = 1.0
        while True:
            buf = io.BytesIO()
            resized = image
            if scale < 0.999:
                resized = image.resize((max(32, int(width * scale)), max(32, int(height * scale))), Image.LANCZOS)
            resized.save(buf, format="JPEG", quality=max(30, quality))
            out = buf.getvalue()
            if len(out) <= max_size:
                return out
            if quality > 38:
                quality -= 8
            else:
                scale *= 0.86
                if scale < 0.35:
                    return out
    except Exception:
        return data


def _upload_article_image_openapi(access_token: str, image_url: str) -> Tuple[str, str]:
    src = str(image_url or "").strip()
    if not src:
        return "", "正文图片 URL 为空"
    if _is_wechat_cdn_url(src):
        return src, ""
    image_bytes, mime, dl_err = _download_image_bytes(src)
    if not image_bytes:
        return "", f"图片下载失败 {dl_err}"
    image_bytes = _compress_image_bytes(image_bytes, max_size=1 * 1024 * 1024)
    endpoint = f"https://api.weixin.qq.com/cgi-bin/media/uploadimg?access_token={access_token}"
    files = {
        "media": (f"body_{int(time.time() * 1000)}.jpg", image_bytes, mime or "image/jpeg"),
    }
    try:
        resp = requests.post(endpoint, files=files, timeout=(5, 40))
    except Exception as e:
        return "", f"正文图片上传异常: {e}"
    if int(resp.status_code or 0) >= 400:
        return "", f"正文图片上传 HTTP {resp.status_code}"
    try:
        payload = resp.json()
    except Exception:
        return "", "正文图片上传返回非 JSON"
    url = str(payload.get("url") or "").strip()
    if url:
        return url, ""
    err = str(payload.get("errmsg") or payload.get("errcode") or payload)[:240]
    return "", f"正文图片上传失败: {err}"


def _upload_cover_media_openapi(access_token: str, cover_url: str) -> Tuple[str, str]:
    def _post_cover(image_bytes: bytes, mime: str, filename: str) -> Tuple[str, str]:
        endpoint = f"https://api.weixin.qq.com/cgi-bin/material/add_material?access_token={access_token}&type=image"
        files = {
            "media": (filename, image_bytes, mime or "image/jpeg"),
        }
        try:
            resp = requests.post(endpoint, files=files, timeout=(5, 40))
        except Exception as e:
            return "", f"封面上传异常: {e}"
        if int(resp.status_code or 0) >= 400:
            return "", f"封面上传 HTTP {resp.status_code}"
        try:
            payload = resp.json()
        except Exception:
            return "", "封面上传返回非 JSON"
        media_id = str(payload.get("media_id") or "").strip()
        if media_id:
            return media_id, ""
        err = str(payload.get("errmsg") or payload.get("errcode") or payload)[:240]
        return "", f"封面上传失败: {err}"

    src = str(cover_url or "").strip()
    if not src:
        return "", "封面 URL 为空"
    image_bytes, mime, dl_err = _download_image_bytes(src)
    if not image_bytes:
        return "", f"封面下载失败 {dl_err}"
    image_bytes = _compress_image_bytes(image_bytes, max_size=9 * 1024 * 1024)
    return _post_cover(
        image_bytes=image_bytes,
        mime=mime or "image/jpeg",
        filename=f"cover_{int(time.time() * 1000)}.jpg",
    )


def _upload_cover_media_openapi_from_local_file(access_token: str, file_path: str) -> Tuple[str, str]:
    path = str(file_path or "").strip()
    if not path:
        return "", "默认封面路径为空"
    if not os.path.isfile(path):
        return "", f"默认封面文件不存在: {path}"
    try:
        with open(path, "rb") as f:
            image_bytes = f.read()
    except Exception as e:
        return "", f"读取默认封面失败: {e}"
    if not image_bytes:
        return "", "默认封面内容为空"
    mime = "image/png"
    lower = path.lower()
    if lower.endswith(".jpg") or lower.endswith(".jpeg"):
        mime = "image/jpeg"
    elif lower.endswith(".gif"):
        mime = "image/gif"
    elif lower.endswith(".webp"):
        mime = "image/webp"
    image_bytes = _compress_image_bytes(image_bytes, max_size=9 * 1024 * 1024)
    endpoint = f"https://api.weixin.qq.com/cgi-bin/material/add_material?access_token={access_token}&type=image"
    files = {
        "media": (f"cover_fallback_{int(time.time() * 1000)}.jpg", image_bytes, mime),
    }
    try:
        resp = requests.post(endpoint, files=files, timeout=(5, 40))
    except Exception as e:
        return "", f"默认封面上传异常: {e}"
    if int(resp.status_code or 0) >= 400:
        return "", f"默认封面上传 HTTP {resp.status_code}"
    try:
        payload = resp.json()
    except Exception:
        return "", "默认封面上传返回非 JSON"
    media_id = str(payload.get("media_id") or "").strip()
    if media_id:
        return media_id, ""
    err = str(payload.get("errmsg") or payload.get("errcode") or payload)[:240]
    return "", f"默认封面上传失败: {err}"


def _rewrite_html_images_to_wechat_openapi(content_html: str, access_token: str) -> Tuple[str, Dict[str, str], List[str]]:
    text = str(content_html or "")
    if not text:
        return "", {}, []
    mapping: Dict[str, str] = {}
    warnings: List[str] = []

    def _repl(match: re.Match) -> str:
        tag = str(match.group(0) or "")
        src = (
            _extract_img_attr(tag, "src")
            or _extract_img_attr(tag, "data-src")
            or _extract_img_attr(tag, "data-original")
            or _extract_img_attr(tag, "data-url")
        )
        src = str(src or "").strip()
        if not src or not re.match(r"^https?://", src, flags=re.IGNORECASE):
            return tag
        if _is_wechat_cdn_url(src):
            return tag
        if src in mapping:
            target = mapping[src]
        else:
            target, err = _upload_article_image_openapi(access_token, src)
            if not target:
                warnings.append(f"{src[:80]} -> {err}")
                return tag
            mapping[src] = target
        updated = _set_img_attr(tag, "src", target)
        updated = _set_img_attr(updated, "data-src", target)
        updated = _set_img_attr(updated, "data-original", target)
        return updated

    rewritten = re.sub(r"<img\b[^>]*>", _repl, text, flags=re.IGNORECASE)
    return rewritten, mapping, warnings


def _publish_batch_to_wechat_draft_openapi(
    items: List[Dict],
    wechat_app_id: str,
    wechat_app_secret: str,
) -> Tuple[bool, str, Dict]:
    token, token_err = _get_wechat_openapi_access_token(wechat_app_id, wechat_app_secret)
    if not token:
        return False, f"微信公众号接口不可用：{token_err}", {}

    articles: List[Dict[str, Any]] = []
    body_image_warnings: List[str] = []
    missing_image_titles: List[str] = []
    cover_warnings: List[str] = []
    for item in items or []:
        title = str(item.get("title") or "未命名草稿").strip()
        safe_title = _safe_wechat_title(title)
        markdown = str(item.get("content") or "").strip()
        if not markdown:
            continue
        cover_url = str(item.get("cover_url") or "").strip()
        content_html = _normalize_wechat_img_tags(_markdown_to_wechat_html(markdown))
        content_html, _, upload_warnings = _rewrite_html_images_to_wechat_openapi(content_html, token)
        if upload_warnings:
            body_image_warnings.extend([f"{title}: {x}" for x in upload_warnings[:3]])

        body_image_urls = _extract_image_urls_from_html(content_html)
        first_body_image = _pick_first_http_image_url(body_image_urls)
        content_html, injected = _ensure_wechat_body_has_image(content_html, first_body_image or cover_url)
        if injected:
            content_html, _, inject_warnings = _rewrite_html_images_to_wechat_openapi(content_html, token)
            if inject_warnings:
                body_image_warnings.extend([f"{title}: {x}" for x in inject_warnings[:3]])
            body_image_urls = _extract_image_urls_from_html(content_html)

        if not _contains_html_image(content_html):
            missing_image_titles.append(title)
            continue

        cover_candidates: List[str] = []
        for url in body_image_urls:
            text = str(url or "").strip()
            if not re.match(r"^https?://", text, flags=re.IGNORECASE):
                continue
            if text not in cover_candidates:
                cover_candidates.append(text)
        if re.match(r"^https?://", cover_url, flags=re.IGNORECASE) and cover_url not in cover_candidates:
            cover_candidates.append(cover_url)

        thumb_media_id = ""
        cover_attempt_errors: List[str] = []
        for candidate in cover_candidates[:6]:
            thumb_media_id, cover_err = _upload_cover_media_openapi(token, candidate)
            if thumb_media_id:
                break
            if cover_err:
                cover_attempt_errors.append(f"{candidate[:80]} -> {cover_err}")

        if not thumb_media_id:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            fallback_path = str(
                cfg.get("ai.wechat_default_cover_path", os.path.join(base_dir, "static", "default-avatar.png"))
                or ""
            ).strip()
            if fallback_path and not os.path.isabs(fallback_path):
                fallback_path = os.path.abspath(os.path.join(base_dir, fallback_path))
            thumb_media_id, fallback_err = _upload_cover_media_openapi_from_local_file(token, fallback_path)
            if thumb_media_id:
                cover_warnings.append(f"{title}: 封面链接不可用，已自动回退默认封面")
            else:
                if not cover_attempt_errors:
                    if cover_candidates:
                        cover_attempt_errors.append("封面处理失败（无可用封面候选）")
                    else:
                        cover_attempt_errors.append("缺少可用封面图链接")
                if fallback_err:
                    cover_attempt_errors.append(f"默认封面回退失败: {fallback_err}")
                cover_warnings.append(f"{title}: {'；'.join(cover_attempt_errors[:3])}")
                continue

        articles.append(
            {
                "title": safe_title,
                "author": str(item.get("author") or "").strip(),
                "digest": str(item.get("digest") or "").strip()[:120],
                "content": content_html,
                "content_source_url": "",
                "thumb_media_id": thumb_media_id,
                "need_open_comment": 1,
                "only_fans_can_comment": 0,
            }
        )

    if missing_image_titles:
        return False, "微信草稿箱投递失败: 以下草稿正文缺少插图: " + "；".join(missing_image_titles[:5]), {
            "missing_body_image_titles": missing_image_titles,
            "body_image_upload_warnings": body_image_warnings[:20],
            "cover_warnings": cover_warnings[:20],
        }
    if cover_warnings and not articles:
        sample = str(cover_warnings[0] or "").strip()
        sample_text = f"（示例：{sample[:160]}）" if sample else ""
        return False, f"微信草稿箱投递失败: 封面处理失败，请检查封面图链接与公众号权限{sample_text}", {
            "cover_warnings": cover_warnings[:20],
            "body_image_upload_warnings": body_image_warnings[:20],
        }
    if not articles:
        return False, "没有有效内容可推送", {}

    endpoint = f"https://api.weixin.qq.com/cgi-bin/draft/add?access_token={token}"
    try:
        # 显式序列化 JSON，确保中文不被转义为 \uXXXX（修复草稿箱乱码问题）
        payload_json = json.dumps({"articles": articles}, ensure_ascii=False)
        resp = requests.post(
            endpoint,
            data=payload_json.encode('utf-8'),
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=(5, 40),
        )
    except Exception as e:
        return False, f"微信草稿箱请求异常: {e}", {}
    if int(resp.status_code or 0) >= 400:
        return False, f"微信草稿箱接口返回 HTTP {resp.status_code}", {"status_code": resp.status_code}
    try:
        payload = resp.json()
    except Exception:
        return False, "微信草稿箱接口返回非 JSON", {"raw": str(resp.text or "")[:260]}
    media_id = str(payload.get("media_id") or "").strip()
    if media_id:
        msg = "已按官方接口投递到公众号草稿箱"
        if body_image_warnings:
            msg += f"（正文图片降级 {len(body_image_warnings)} 项）"
        if cover_warnings:
            msg += f"（封面降级 {len(cover_warnings)} 项）"
        payload["body_image_upload_warnings"] = body_image_warnings[:20]
        payload["cover_warnings"] = cover_warnings[:20]
        return True, msg, payload
    errcode = payload.get("errcode")
    errmsg = payload.get("errmsg")
    return False, f"微信草稿箱投递失败: errcode={errcode}, errmsg={errmsg}", payload


def publish_batch_to_wechat_draft(
    items: List[Dict],
    owner_id: str = "",
    session=None,
    wechat_app_id: str = "",
    wechat_app_secret: str = "",
) -> Tuple[bool, str, Dict]:
    """
    批量推送到公众号草稿箱（单次请求支持多图文）。
    当封面 media_id 上传失败时，会降级为无封面继续投递。
    """
    if not items:
        return False, "没有可投递内容", {}
    app_id = str(wechat_app_id or "").strip()
    app_secret = str(wechat_app_secret or "").strip()
    if app_id and app_secret:
        return _publish_batch_to_wechat_draft_openapi(items=items, wechat_app_id=app_id, wechat_app_secret=app_secret)
    if app_id or app_secret:
        return False, "同步到草稿箱需要同时提供 wechat_app_id 与 wechat_app_secret", {}
    try:
        token, cookie = _wechat_auth(owner_id=owner_id, session=session)
    except Exception:
        return False, "未找到微信授权配置，请先扫码授权", {}
    if not token or not cookie:
        return False, "公众号尚未扫码授权，已保存到本地草稿箱", {}

    appmsg = []
    cover_warnings: List[str] = []
    body_image_upload_warnings: List[str] = []
    missing_image_titles: List[str] = []
    auto_image_injected_titles: List[str] = []
    cover_from_first_body_image_titles: List[str] = []
    for item in items:
        title = str(item.get("title", "未命名草稿")).strip()
        safe_title = _safe_wechat_title(title)
        content = str(item.get("content", "")).strip()
        if not content:
            continue
        cover_url = str(item.get("cover_url", "")).strip()
        content_html = _normalize_wechat_img_tags(_markdown_to_wechat_html(content))
        body_image_urls = _extract_image_urls_from_html(content_html)
        first_body_image_url = _pick_first_http_image_url(body_image_urls)

        content_html, _, upload_warnings = _rewrite_html_images_to_wechat_cdn(content_html, token, cookie)
        if upload_warnings:
            body_image_upload_warnings.extend([f"{title}: {x}" for x in upload_warnings[:3]])
        body_image_urls = _extract_image_urls_from_html(content_html)
        first_body_image_url_after = _pick_first_http_image_url(body_image_urls)

        # 微信草稿场景优先使用正文第一张图片作为封面，保证封面与正文一致。
        effective_cover_url = first_body_image_url_after or first_body_image_url or cover_url
        if first_body_image_url:
            cover_from_first_body_image_titles.append(title)

        content_html, injected = _ensure_wechat_body_has_image(content_html, effective_cover_url)
        if injected:
            auto_image_injected_titles.append(title)
            # 兜底插入的图片也要上传到微信图床，否则仍可能触发 64513。
            content_html, _, inject_upload_warnings = _rewrite_html_images_to_wechat_cdn(content_html, token, cookie)
            if inject_upload_warnings:
                body_image_upload_warnings.extend([f"{title}: {x}" for x in inject_upload_warnings[:3]])
            body_image_urls = _extract_image_urls_from_html(content_html)
            first_body_image_url = _pick_first_http_image_url(body_image_urls)
            if first_body_image_url:
                effective_cover_url = first_body_image_url
        if not _contains_html_image(content_html):
            missing_image_titles.append(title)
            continue

        thumb_media_id, cover_err = _try_upload_cover_media_id(token, cookie, effective_cover_url)
        if cover_err:
            cover_warnings.append(f"{title}: {cover_err}")
        appmsg.append(
            {
                "title": safe_title,
                "author": str(item.get("author", "")).strip(),
                "digest": str(item.get("digest", "")).strip()[:120],
                "content": content_html,
                "content_source_url": "",
                "source_url": "",
                "need_open_comment": 1,
                "only_fans_can_comment": 0,
                "show_cover_pic": 1 if thumb_media_id else 0,
                # 直链封面在部分帐号会触发 64513（封面必须存在正文中），
                # 这里默认关闭直链封面回退，仅在上传成功时使用 thumb_media_id。
                "cdn_url": "",
                "thumb_media_id": thumb_media_id,
            }
        )

    if missing_image_titles:
        return (
            False,
            "微信草稿箱投递失败: 以下草稿正文缺少插图，请在正文插入图片或提供封面图后重试: "
            + "；".join(missing_image_titles[:5]),
            {
                "missing_body_image_titles": missing_image_titles,
                "auto_image_injected_titles": auto_image_injected_titles,
                "cover_from_first_body_image_titles": cover_from_first_body_image_titles,
                "body_image_upload_warnings": body_image_upload_warnings[:20],
            },
        )

    if not appmsg:
        return False, "没有有效内容可推送", {}

    endpoint = "https://mp.weixin.qq.com/cgi-bin/operate_appmsg"
    params = {
        "sub": "create",
        "t": "ajax-response",
        "type": "10",
        "token": token,
        "lang": "zh_CN",
        "f": "json",
        "ajax": "1",
    }
    headers = {
        "Cookie": cookie,
        "User-Agent": str(cfg.get("user_agent", "Mozilla/5.0")),
        "Referer": f"https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit&action=edit&type=10&token={token}&lang=zh_CN",
    }

    def _post_appmsg(payload_appmsg: List[Dict]) -> Tuple[int, str, Dict]:
        data = {
            "AppMsg": json.dumps(payload_appmsg, ensure_ascii=False),
            "count": str(len(payload_appmsg)),
            "isnew": "1",
            "token": token,
            "lang": "zh_CN",
            "f": "json",
            "ajax": "1",
            "random": str(time.time()),
        }
        resp = requests.post(endpoint, params=params, data=data, headers=headers, timeout=40)
        if resp.status_code >= 400:
            return -1, f"微信草稿箱接口返回 HTTP {resp.status_code}", {"status_code": resp.status_code}
        payload: Dict = {}
        try:
            payload = resp.json()
        except Exception:
            return -1, "微信草稿箱接口返回非 JSON，已保存本地草稿", {"raw": resp.text[:300]}
        base_resp = payload.get("base_resp") if isinstance(payload.get("base_resp"), dict) else {}
        ret_raw = payload.get("ret", None)
        if ret_raw is None:
            ret_raw = base_resp.get("ret", -1)
        try:
            ret = int(ret_raw)
        except Exception:
            ret = -1
        err = (
            payload.get("errmsg")
            or payload.get("msg")
            or payload.get("error_msg")
            or base_resp.get("err_msg")
            or base_resp.get("errmsg")
            or ""
        )
        err_text = str(err or "").strip()
        if not err_text and ret != 0:
            err_text = f"unknown error, ret={ret}"
            try:
                raw_brief = json.dumps(payload, ensure_ascii=False)[:240]
                if raw_brief:
                    err_text = f"{err_text}, payload={raw_brief}"
            except Exception:
                pass
        return ret, err_text, payload

    try:
        ret, err_text, payload = _post_appmsg(appmsg)
        if ret == 0:
            msg = "已投递到公众号草稿箱"
            if cover_warnings:
                msg = msg + f"（封面降级 {len(cover_warnings)} 项）"
            if body_image_upload_warnings:
                msg = msg + f"（正文图片上传降级 {len(body_image_upload_warnings)} 项）"
            payload["cover_warnings"] = cover_warnings
            payload["auto_image_injected_titles"] = auto_image_injected_titles
            payload["cover_from_first_body_image_titles"] = cover_from_first_body_image_titles
            payload["body_image_upload_warnings"] = body_image_upload_warnings[:20]
            return True, msg, payload

        if ret == 64513:
            logger.warning("WeChat draft rejected with ret=64513, retry without cover.")
            appmsg_no_cover: List[Dict] = []
            for row in appmsg:
                clean_row = dict(row)
                clean_row["show_cover_pic"] = 0
                clean_row["thumb_media_id"] = ""
                clean_row["cdn_url"] = ""
                appmsg_no_cover.append(clean_row)
            retry_ret, retry_err_text, retry_payload = _post_appmsg(appmsg_no_cover)
            payload["retry_no_cover"] = retry_payload
            if retry_ret == 0:
                msg = "已投递到公众号草稿箱（封面与正文校验失败，已自动移除封面重试成功）"
                if cover_warnings:
                    msg = msg + f"（封面降级 {len(cover_warnings)} 项）"
                if body_image_upload_warnings:
                    msg = msg + f"（正文图片上传降级 {len(body_image_upload_warnings)} 项）"
                retry_payload["cover_warnings"] = cover_warnings
                retry_payload["auto_image_injected_titles"] = auto_image_injected_titles
                retry_payload["cover_from_first_body_image_titles"] = cover_from_first_body_image_titles
                retry_payload["body_image_upload_warnings"] = body_image_upload_warnings[:20]
                return True, msg, retry_payload
            ret = retry_ret
            err_text = retry_err_text or err_text

        if ret in [200003, 200013] or "invalid session" in err_text.lower():
            return False, f"微信授权已失效，请重新扫码授权（ret={ret}, err={err_text}）", payload
        detail_suffix = ""
        if body_image_upload_warnings:
            detail_suffix = f"，正文图片上传异常示例：{body_image_upload_warnings[0]}"
        return False, f"微信草稿箱投递失败: ret={ret}, err={err_text}{detail_suffix}", payload
    except Exception as e:
        return False, f"微信草稿箱请求异常: {e}", {}


def publish_to_wechat_draft(
    title: str,
    content: str,
    digest: str = "",
    author: str = "",
    cover_url: str = "",
    owner_id: str = "",
    session=None,
) -> Tuple[bool, str, Dict]:
    return publish_batch_to_wechat_draft(
        [
            {
                "title": title,
                "content": content,
                "digest": digest,
                "author": author,
                "cover_url": cover_url,
            }
        ],
        owner_id=owner_id,
        session=session,
    )


def serialize_publish_task(task: AIPublishTask) -> Dict:
    return {
        "id": task.id,
        "owner_id": task.owner_id,
        "article_id": task.article_id,
        "title": task.title,
        "platform": task.platform,
        "status": task.status,
        "retries": int(task.retries or 0),
        "max_retries": int(task.max_retries or 0),
        "next_retry_at": task.next_retry_at.isoformat() if task.next_retry_at else None,
        "last_error": task.last_error or "",
        "last_response": task.last_response or "",
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
    }


def enqueue_publish_task(
    session,
    owner_id: str,
    article_id: str,
    title: str,
    content: str,
    digest: str = "",
    author: str = "",
    cover_url: str = "",
    platform: str = "wechat",
    max_retries: int = 3,
) -> AIPublishTask:
    now = datetime.now()
    task = AIPublishTask(
        id=str(uuid.uuid4()),
        owner_id=owner_id,
        article_id=article_id,
        title=(title or "未命名草稿").strip(),
        content=(content or "").strip(),
        digest=(digest or "").strip(),
        author=(author or "").strip(),
        cover_url=(cover_url or "").strip(),
        platform=(platform or "wechat").strip().lower(),
        status=PUBLISH_STATUS_PENDING,
        retries=0,
        max_retries=max(1, min(int(max_retries or 3), 8)),
        next_retry_at=now,
        last_error="",
        last_response="",
        created_at=now,
        updated_at=now,
    )
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


def _mark_task_processing(session, task: AIPublishTask, now: datetime) -> bool:
    """
    尝试将任务从 pending 原子切换到 processing。
    在并发 worker 场景下，只有一个执行器能成功切换状态。
    """
    if not hasattr(session, "query"):
        task.status = PUBLISH_STATUS_PROCESSING
        task.updated_at = now
        session.commit()
        return True
    try:
        affected = session.query(AIPublishTask).filter(
            AIPublishTask.id == task.id,
            AIPublishTask.status == PUBLISH_STATUS_PENDING,
        ).update(
            {
                AIPublishTask.status: PUBLISH_STATUS_PROCESSING,
                AIPublishTask.updated_at: now,
            },
            synchronize_session=False,
        )
        session.commit()
        if affected <= 0:
            return False
        try:
            session.refresh(task)
        except Exception:
            pass
        return True
    except Exception:
        if hasattr(session, "rollback"):
            session.rollback()
        return False


def process_publish_task(session, task: AIPublishTask) -> Tuple[bool, str]:
    now = datetime.now()
    if task.status == PUBLISH_STATUS_SUCCESS:
        return True, "任务已成功，无需重试"
    if task.next_retry_at and task.next_retry_at > now:
        return False, "未到重试时间"

    if not _mark_task_processing(session, task, now):
        return False, "任务已被其他进程处理"

    ok, message, raw = publish_to_wechat_draft(
        title=task.title,
        content=task.content,
        digest=task.digest,
        author=task.author,
        cover_url=task.cover_url,
        owner_id=task.owner_id,
        session=session,
    )

    task.updated_at = datetime.now()
    task.last_response = json.dumps(raw or {}, ensure_ascii=False)[:3000]

    if ok:
        task.status = PUBLISH_STATUS_SUCCESS
        task.last_error = ""
        task.next_retry_at = None
        session.commit()
        return True, message

    retries = int(task.retries or 0) + 1
    task.retries = retries
    task.last_error = message[:1000]
    if retries >= int(task.max_retries or 3):
        task.status = PUBLISH_STATUS_FAILED
        task.next_retry_at = None
    else:
        task.status = PUBLISH_STATUS_PENDING
        backoff_minutes = min(30, 2 ** retries)
        task.next_retry_at = datetime.now() + timedelta(minutes=backoff_minutes)
    session.commit()
    return False, message


def process_pending_publish_tasks(session, owner_id: str = "", limit: int = 10) -> Dict:
    now = datetime.now()
    query = session.query(AIPublishTask).filter(
        AIPublishTask.status == PUBLISH_STATUS_PENDING,
        AIPublishTask.next_retry_at <= now,
    )
    if owner_id:
        query = query.filter(AIPublishTask.owner_id == owner_id)
    tasks = query.order_by(AIPublishTask.created_at.asc()).limit(max(1, int(limit or 10))).all()

    success_count = 0
    failed_count = 0
    details = []
    for task in tasks:
        ok, msg = process_publish_task(session, task)
        if ok:
            success_count += 1
        else:
            failed_count += 1
        details.append(
            {
                "id": task.id,
                "status": task.status,
                "message": msg,
            }
        )
    return {
        "total": len(tasks),
        "success": success_count,
        "failed": failed_count,
        "details": details,
    }
