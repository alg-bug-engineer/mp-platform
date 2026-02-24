"""
AI 提示词模板 - 去 AI 味，自然化表达

这个模块提供了优化后的提示词模板，避免列表化和机器感，
采用案例驱动、场景化的方式生成更自然的内容。
"""

from enum import Enum
from typing import Dict, Optional


class PromptStyle(Enum):
    """提示词风格枚举"""
    NARRATIVE = "叙事型"     # 用故事和案例
    TECHNICAL = "技术型"     # 深入浅出
    CASUAL = "对话型"        # 口语化表达


# ============================================================================
# 平台特性定义（去列表化，增加场景描述）
# ============================================================================

PLATFORM_CHARACTERISTICS = {
    "wechat": {
        "name": "微信公众号",
        "tone_desc": "像是在给朋友发一篇有深度的长文，既专业又不端着",
        "structure_hint": "开头可以用一个小故事或者提问来吸引注意，中间展开观点时用小标题分段，结尾最好有个升华或者行动号召",
        "example": "比如科技类文章可以这样开头：'上周跟一个创业的朋友聊天，他说现在AI工具多得让人眼花，但真正用好的人不多...'",
        "avoid": "不要写成论文格式，不要用'首先、其次、最后'这种生硬的过渡词",
    },
    "xiaohongshu": {
        "name": "小红书",
        "tone_desc": "像是在跟闺蜜分享一个超实用的发现，真诚、接地气、有画面感",
        "structure_hint": "第一段就要抛出最核心的干货或者痛点，用表情符号增加亲和力，最后可以加个互动问题",
        "example": "比如职场技巧可以这样写：'姐妹们！我发现了一个让老板对你刮目相看的方法✨ 之前我也是...'",
        "avoid": "不要写得太正式，不要长篇大论，段落要短，每段不超过3行",
    },
    "zhihu": {
        "name": "知乎",
        "tone_desc": "像是一个行业资深人士在分享经验，既有理有据，又不会让人觉得在炫技",
        "structure_hint": "先给出核心观点，然后用数据、案例、逻辑推演来支撑，适当加一些个人经历增加可信度",
        "example": "比如技术分析可以这样：'做了5年后端开发，我发现90%的性能问题都出在这3个地方...'",
        "avoid": "不要只堆概念不讲人话，不要为了显得专业而用太多术语，深入浅出才是王道",
    },
    "twitter": {
        "name": "推特/X",
        "tone_desc": "像是在给关注你的人发一条有价值的推文，简洁、有洞察、值得转发",
        "structure_hint": "第一句话就要抛出核心观点，后面用2-3个短句来支撑或延展，可以用emoji但不要过度",
        "example": "比如观点分享：'AI工具最大的陷阱不是技术门槛，而是让人觉得有了工具就不用思考了。真正的高手是...'",
        "avoid": "不要写成长文章的摘要，不要堆砌热门话题标签，真诚比流量更重要",
    },
}


# ============================================================================
# 写作风格定义（场景化描述）
# ============================================================================

WRITING_STYLES = {
    "专业深度": {
        "description": "像行业白皮书那样，用数据和逻辑说服人",
        "guidance": "想象你在给同行写一篇深度分析。用真实数据佐证观点，用案例拆解原理，让读者看完觉得'原来是这么回事'。",
        "example_opening": "过去一年，我们分析了500+个失败案例，发现有个规律特别明显...",
        "key_elements": "数据支撑、逻辑推导、行业洞察、专业术语适度使用",
    },
    "故事共鸣": {
        "description": "像讲朋友故事一样，让读者感同身受",
        "guidance": "不要干巴巴讲道理，而是通过一个具体的人、具体的场景来展开。可以是你的经历，可以是身边人的故事，关键是要有画面感和情绪。",
        "example_opening": "三年前，我遇到一个客户，他的问题看起来很常见，但背后的原因让我至今记忆犹新...",
        "key_elements": "具体场景、人物细节、情绪波动、冲突与转折",
    },
    "实操清单": {
        "description": "像操作手册那样,每一步都能照着做",
        "guidance": "把复杂的任务拆解成可执行的步骤。每一步都要具体、明确，最好能说清楚'做什么'和'为什么这么做'。",
        "example_opening": "如果你想在30天内搭建一个内容运营体系，这5个步骤可以直接上手...",
        "key_elements": "清晰步骤、具体工具、常见坑点、效果预期",
    },
    "犀利观点": {
        "description": "像时评专栏那样，旗帜鲜明地表达立场",
        "guidance": "不要和稀泥，直接抛出你的观点。可以反常识，可以反主流，但一定要言之有据。敢说'不'比唱赞歌更有价值。",
        "example_opening": "大家都在追捧的增长黑客，我认为90%的公司根本不需要，原因很简单...",
        "key_elements": "鲜明立场、反常识角度、有力论据、挑战权威",
    },
}


# ============================================================================
# 篇幅说明（场景化描述）
# ============================================================================

CONTENT_LENGTHS = {
    "short": {
        "label": "短篇 (300-500字)",
        "description": "像朋友圈长文那样，一口气能读完",
        "best_for": "适合单一观点、快速教程、碎片化阅读",
        "structure": "开门见山→核心要点→简短总结",
    },
    "medium": {
        "label": "中篇 (800-1200字)",
        "description": "像一篇公众号推文那样，有深度但不累",
        "best_for": "适合深度分析、经验分享、案例拆解",
        "structure": "引入话题→展开2-3个要点→呼应开头",
    },
    "long": {
        "label": "长篇 (1500-2200字)",
        "description": "像一篇研究报告那样，值得收藏反复看",
        "best_for": "适合系统方法论、多案例对比、行业洞察",
        "structure": "问题背景→分层论述→实践建议→升华总结",
    },
}


# ============================================================================
# 核心提示词构建函数
# ============================================================================

def build_natural_prompt(
    mode: str,
    platform: str,
    style: str,
    length: str,
    instruction: str = "",
    audience: str = "",
    tone: str = "",
    source_title: str = "",
    source_content: str = "",
) -> tuple[str, str]:
    """
    构建自然化的系统提示词和用户提示词

    Args:
        mode: 创作模式 (analyze/create/rewrite)
        platform: 发布平台
        style: 写作风格
        length: 篇幅
        instruction: 用户补充要求
        audience: 目标受众
        tone: 语气
        source_title: 源文章标题
        source_content: 源文章内容

    Returns:
        (system_prompt, user_prompt) 元组
    """
    platform_info = PLATFORM_CHARACTERISTICS.get(platform, PLATFORM_CHARACTERISTICS["wechat"])
    style_info = WRITING_STYLES.get(style, WRITING_STYLES["专业深度"])
    length_info = CONTENT_LENGTHS.get(length, CONTENT_LENGTHS["medium"])

    # ========== 系统提示词 ==========
    system_prompt = f"""你是一位资深的新媒体内容创作者，擅长为{platform_info['name']}创作内容。

你的写作风格是：{style_info['description']}

关键原则：
{style_info['guidance']}

平台特点：
{platform_info['tone_desc']}
{platform_info['structure_hint']}

举个例子：
{platform_info['example']}

务必避免：
{platform_info['avoid']}

篇幅要求：
{length_info['description']}（{length_info['label']}）
结构建议：{length_info['structure']}"""

    # 添加受众和语气信息（如果有）
    if audience:
        system_prompt += f"\n\n目标读者：{audience}。写作时要想象你在跟这群人对话，用他们能理解的语言，关注他们关心的问题。"

    if tone:
        system_prompt += f"\n\n语气基调：{tone}。这种语气应该贯穿全文，让读者感受到你的态度。"

    # ========== 用户提示词 ==========
    if mode == "analyze":
        user_prompt = f"""请分析这篇文章：《{source_title}》

不要写成学术论文的摘要，而是像给朋友讲解一样：
• 这篇文章主要在说什么事？（用一句话概括核心）
• 最有价值的3个要点是什么？（每个都用一个具体例子或场景来说明）
• 如果要应用到实际工作中，可以怎么做？（给出可操作的建议）

文章内容：
{source_content[:8000]}"""

    elif mode == "rewrite":
        user_prompt = f"""请改写这篇文章：《{source_title}》

不是简单改个表述，而是：
• 保留核心观点和事实
• 用更{style_info['description']}的方式重新讲述
• 增加{platform_info['name']}读者喜欢的元素（{platform_info['tone_desc']}）
• {length_info['description']}，{length_info['structure']}

原文内容：
{source_content[:8000]}"""

    else:  # create
        user_prompt = f"""基于这篇文章的主题，创作一篇新的内容：《{source_title}》

不要简单复述原文，而是：
• 提炼出核心话题和关键洞察
• 结合你的"经验"和视角，给出新的观点或案例
• {style_info['description']}
• 符合{platform_info['name']}的调性（{platform_info['tone_desc']}）
• {length_info['description']}，{length_info['structure']}

参考素材：
{source_content[:8000]}"""

    # 添加用户的补充要求
    if instruction:
        user_prompt += f"\n\n【特别要求】\n{instruction}"

    return system_prompt, user_prompt


# ============================================================================
# 前端选项数据（供 API 返回）
# ============================================================================

def get_frontend_options() -> Dict:
    """
    获取前端创作选项的场景化描述数据

    Returns:
        包含平台、风格、篇幅选项的字典
    """
    return {
        "platforms": [
            {
                "key": "wechat",
                "label": "微信公众号",
                "style": "深度有料，专业不端着",
                "structure": "适合长文深度分析",
            },
            {
                "key": "xiaohongshu",
                "label": "小红书",
                "style": "真诚分享，接地气有画面感",
                "structure": "适合干货清单和生活经验",
            },
            {
                "key": "zhihu",
                "label": "知乎",
                "style": "理性思考，深入浅出",
                "structure": "适合专业观点和系统方法论",
            },
            {
                "key": "twitter",
                "label": "推特/X",
                "style": "简洁有力，观点鲜明",
                "structure": "适合短平快的洞察",
            },
        ],
        "styles": [
            {
                "key": "专业深度",
                "label": "专业深度",
                "desc": "像行业白皮书那样，用数据和逻辑说服人",
                "hint": "适合B端内容、技术分析、行业报告",
            },
            {
                "key": "故事共鸣",
                "label": "故事共鸣",
                "desc": "像讲朋友故事一样，让读者感同身受",
                "hint": "适合品牌故事、用户案例、情感营销",
            },
            {
                "key": "实操清单",
                "label": "实操清单",
                "desc": "像操作手册那样，每一步都能照着做",
                "hint": "适合教程指南、工具推荐、方法论",
            },
            {
                "key": "犀利观点",
                "label": "犀利观点",
                "desc": "像时评专栏那样，旗帜鲜明地表达立场",
                "hint": "适合行业评论、趋势分析、反思类内容",
            },
        ],
        "lengths": [
            {
                "key": "short",
                "label": "短篇 (300-500字)",
                "desc": "像朋友圈长文那样，一口气能读完",
                "best_for": "适合单一观点、快速教程、碎片化阅读",
            },
            {
                "key": "medium",
                "label": "中篇 (800-1200字)",
                "desc": "像一篇公众号推文那样，有深度但不累",
                "best_for": "适合深度分析、经验分享、案例拆解",
            },
            {
                "key": "long",
                "label": "长篇 (1500-2200字)",
                "desc": "像一篇研究报告那样，值得收藏反复看",
                "best_for": "适合系统方法论、多案例对比、行业洞察",
            },
        ],
    }


# ============================================================================
# 配图提示词生成（自然化）
# ============================================================================

def build_image_prompt(
    context: str,
    platform: str,
    style: str,
    image_index: int = 0,
    total_images: int = 1,
) -> str:
    """
    生成配图提示词（自然化描述）

    Args:
        context: 内容上下文
        platform: 发布平台
        style: 写作风格
        image_index: 图片序号（从0开始）
        total_images: 总图片数

    Returns:
        配图提示词
    """
    platform_info = PLATFORM_CHARACTERISTICS.get(platform, PLATFORM_CHARACTERISTICS["wechat"])
    style_info = WRITING_STYLES.get(style, WRITING_STYLES["专业深度"])

    # 根据位置确定图片类型
    if image_index == 0:
        image_type = "封面主图"
        position_hint = "这是读者第一眼看到的图，要能快速传达主题，吸引点击"
    elif image_index == total_images - 1 and total_images > 2:
        image_type = "结尾配图"
        position_hint = "这是文章的收尾图，可以呼应主题或者给人启发"
    else:
        image_type = "内容配图"
        position_hint = "这是文中的配图，要能帮助读者更好地理解内容"

    prompt = f"""为这段内容生成一张{image_type}：

内容片段：
{context[:500]}

设计要求：
• {position_hint}
• 符合{platform_info['name']}的视觉风格（简洁、清晰、有设计感）
• 体现"{style_info['description']}"的气质
• 不要有多余的文字，让画面自己说话

生成一个简洁的图片描述（英文），突出核心元素和氛围。"""

    return prompt
