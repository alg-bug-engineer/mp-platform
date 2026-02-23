from datetime import datetime
from typing import Dict, Tuple


DEFAULT_PLAN_TIER = "free"

PLAN_DEFINITIONS: Dict[str, Dict] = {
    "free": {
        "tier": "free",
        "label": "免费用户",
        "price_hint": "￥0/月",
        "description": "适合个人试用与轻量创作",
        "ai_quota": 30,
        "image_quota": 5,
        "can_generate_images": False,
        "can_publish_wechat_draft": False,
        "allowed_modes": ["analyze", "create", "rewrite"],
        "highlights": [
            "基础 AI 分析/创作/仿写",
            "本地草稿箱保存",
            "按月配额重置",
        ],
    },
    "pro": {
        "tier": "pro",
        "label": "付费用户",
        "price_hint": "建议 ￥99/月",
        "description": "适合稳定更新的个人博主",
        "ai_quota": 300,
        "image_quota": 80,
        "can_generate_images": True,
        "can_publish_wechat_draft": True,
        "allowed_modes": ["analyze", "create", "rewrite"],
        "highlights": [
            "高配额 AI 生产",
            "即梦图片生成",
            "公众号草稿箱一键投递",
        ],
    },
    "premium": {
        "tier": "premium",
        "label": "高级用户",
        "price_hint": "建议 ￥399/月",
        "description": "适合团队化运营和矩阵账号",
        "ai_quota": 1200,
        "image_quota": 400,
        "can_generate_images": True,
        "can_publish_wechat_draft": True,
        "allowed_modes": ["analyze", "create", "rewrite"],
        "highlights": [
            "大规模内容生产配额",
            "完整图文生成链路",
            "适配多账号团队协作场景",
        ],
    },
}


def normalize_plan_tier(tier: str) -> str:
    value = str(tier or "").strip().lower()
    return value if value in PLAN_DEFINITIONS else DEFAULT_PLAN_TIER


def get_plan_definition(tier: str) -> Dict:
    key = normalize_plan_tier(tier)
    return PLAN_DEFINITIONS[key]


def _int_value(value, default=0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def ensure_user_plan_defaults(user, preferred_tier: str = DEFAULT_PLAN_TIER) -> Dict:
    tier = normalize_plan_tier(getattr(user, "plan_tier", "") or preferred_tier)
    plan = get_plan_definition(tier)
    now = datetime.now()

    if not getattr(user, "plan_tier", None):
        user.plan_tier = tier

    if getattr(user, "monthly_ai_quota", None) is None:
        user.monthly_ai_quota = plan["ai_quota"]
    if getattr(user, "monthly_ai_used", None) is None:
        user.monthly_ai_used = 0

    if getattr(user, "monthly_image_quota", None) is None:
        user.monthly_image_quota = plan["image_quota"]
    if getattr(user, "monthly_image_used", None) is None:
        user.monthly_image_used = 0

    if getattr(user, "quota_reset_at", None) is None:
        user.quota_reset_at = now

    return plan


def maybe_reset_monthly_usage(user, now: datetime = None) -> bool:
    now = now or datetime.now()
    reset_at = getattr(user, "quota_reset_at", None)
    if not reset_at:
        user.quota_reset_at = now
        return True
    if reset_at.year == now.year and reset_at.month == now.month:
        return False
    user.monthly_ai_used = 0
    user.monthly_image_used = 0
    user.quota_reset_at = now
    return True


def get_user_plan_summary(user) -> Dict:
    ensure_user_plan_defaults(user)
    maybe_reset_monthly_usage(user)
    is_admin = str(getattr(user, "role", "")) == "admin"
    tier = normalize_plan_tier(getattr(user, "plan_tier", DEFAULT_PLAN_TIER))
    if is_admin:
        tier = "premium"
    plan = get_plan_definition(tier)

    ai_quota = _int_value(getattr(user, "monthly_ai_quota", plan["ai_quota"]), plan["ai_quota"])
    ai_used = max(0, _int_value(getattr(user, "monthly_ai_used", 0), 0))
    image_quota = _int_value(getattr(user, "monthly_image_quota", plan["image_quota"]), plan["image_quota"])
    image_used = max(0, _int_value(getattr(user, "monthly_image_used", 0), 0))

    if is_admin:
        ai_quota = 999999
        image_quota = 999999

    ai_remaining = max(0, ai_quota - ai_used)
    image_remaining = max(0, image_quota - image_used)

    return {
        "tier": tier,
        "label": f'{plan["label"]}（管理员）' if is_admin else plan["label"],
        "description": plan["description"],
        "price_hint": "内部账号" if is_admin else plan["price_hint"],
        "allowed_modes": plan["allowed_modes"],
        "can_generate_images": bool(plan["can_generate_images"] or is_admin),
        "can_publish_wechat_draft": bool(plan["can_publish_wechat_draft"] or is_admin),
        "highlights": plan["highlights"],
        "ai_quota": ai_quota,
        "ai_used": ai_used,
        "ai_remaining": ai_remaining,
        "image_quota": image_quota,
        "image_used": image_used,
        "image_remaining": image_remaining,
        "quota_reset_at": getattr(user, "quota_reset_at", None),
        "plan_expires_at": getattr(user, "plan_expires_at", None),
    }


def validate_ai_action(user, mode: str, image_count: int = 0, publish_to_wechat: bool = False) -> Tuple[bool, str, Dict]:
    summary = get_user_plan_summary(user)
    action = str(mode or "").strip().lower()
    if action not in summary["allowed_modes"]:
        return False, f"当前套餐不支持 {action} 操作", summary

    if summary["ai_remaining"] <= 0:
        return False, "本月 AI 配额已用完，请升级套餐或下月重置后再试", summary

    need_images = max(0, int(image_count or 0))
    if need_images > 0:
        if not summary["can_generate_images"]:
            return False, "当前套餐不支持图片生成功能，请升级后再试", summary
        if summary["image_remaining"] < need_images:
            return False, "本月图片配额不足，请降低图片数量或升级套餐", summary

    if publish_to_wechat and not summary["can_publish_wechat_draft"]:
        return False, "当前套餐不支持公众号草稿箱投递，请升级后再试", summary

    return True, "", summary


def consume_ai_usage(user, image_count: int = 0):
    ensure_user_plan_defaults(user)
    maybe_reset_monthly_usage(user)
    user.monthly_ai_used = _int_value(getattr(user, "monthly_ai_used", 0), 0) + 1
    user.monthly_image_used = _int_value(getattr(user, "monthly_image_used", 0), 0) + max(0, int(image_count or 0))
    user.updated_at = datetime.now()


def get_plan_catalog():
    return [PLAN_DEFINITIONS[key] for key in ["free", "pro", "premium"]]
