import os
from typing import Dict

from core.config import cfg


PRODUCT_MODE_ALL_FREE = "all_free"
PRODUCT_MODE_COMMERCIAL = "commercial"
PRODUCT_MODE_VALUES = {PRODUCT_MODE_ALL_FREE, PRODUCT_MODE_COMMERCIAL}


def normalize_product_mode(mode: str) -> str:
    value = str(mode or "").strip().lower()
    if value in PRODUCT_MODE_VALUES:
        return value
    return PRODUCT_MODE_ALL_FREE


def get_product_mode() -> str:
    configured = cfg.get("product.mode", os.getenv("PRODUCT_MODE", PRODUCT_MODE_ALL_FREE))
    return normalize_product_mode(str(configured or ""))


def is_all_free_mode() -> bool:
    return get_product_mode() == PRODUCT_MODE_ALL_FREE


def get_runtime_flags() -> Dict[str, object]:
    mode = get_product_mode()
    return {
        "product_mode": mode,
        "is_all_free": mode == PRODUCT_MODE_ALL_FREE,
        "billing_visible": mode == PRODUCT_MODE_COMMERCIAL,
    }


def _set_nested_config(path: str, value):
    keys = [x for x in str(path or "").split(".") if x]
    if not keys:
        return
    if not isinstance(cfg.config, dict):
        cfg.config = {}
    cursor = cfg.config
    for key in keys[:-1]:
        current = cursor.get(key)
        if not isinstance(current, dict):
            cursor[key] = {}
        cursor = cursor[key]
    cursor[keys[-1]] = value


def set_product_mode(mode: str) -> str:
    normalized = normalize_product_mode(mode)
    _set_nested_config("product.mode", normalized)
    cfg.save_config()
    return normalized
