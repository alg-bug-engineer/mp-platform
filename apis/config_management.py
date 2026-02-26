from typing import Any, Dict, List, Optional

import yaml
from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel

from .base import error_response, success_response
from core.auth import get_current_user
from core.config import cfg
from core.log import get_logger
logger = get_logger(__name__)

router = APIRouter(prefix="/configs", tags=["配置管理"])


def _require_config_edit_permission(current_user: dict) -> None:
    permissions = current_user.get("permissions") or []
    if isinstance(permissions, str):
        permissions = [permissions]
    if current_user.get("role") == "admin":
        return
    if "admin" in permissions or "config:edit" in permissions:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="无权限修改系统配置",
    )


def _safe_hide_keys() -> set:
    raw = str(cfg.get("safe.hide_config", "db") or "db")
    return {x.strip() for x in raw.split(",") if x.strip()}


def _is_masked_key(config_key: str, hide_keys: set) -> bool:
    if config_key in hide_keys:
        return True
    return any(config_key.startswith(f"{key}.") for key in hide_keys)


def _flatten_config(data: Dict[str, Any], hide_keys: set, prefix: str = "") -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for raw_key, value in data.items():
        key = str(raw_key)
        config_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            rows.extend(_flatten_config(value, hide_keys=hide_keys, prefix=config_key))
            continue
        masked = _is_masked_key(config_key, hide_keys)
        rows.append({
            "config_key": config_key,
            "config_value": "***" if masked else ("" if value is None else str(value)),
            "description": "系统配置项" if "." not in config_key else f"{config_key.split('.')[0]}配置的子项",
            "is_masked": masked,
        })
    return rows


def _split_config_key(config_key: str) -> List[str]:
    parts = [x.strip() for x in str(config_key or "").split(".") if x.strip()]
    if not parts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="配置键不能为空",
        )
    return parts


def _root_config() -> Dict[str, Any]:
    if not isinstance(cfg.config, dict):
        cfg.config = {}
    return cfg.config


def _resolved_root_config() -> Dict[str, Any]:
    root = _root_config()
    resolved = cfg.replace_env_vars(root)
    return resolved if isinstance(resolved, dict) else {}


def _matches_keyword(item: Dict[str, Any], keyword: str) -> bool:
    if not keyword:
        return True
    key_lc = keyword.lower()
    return (
        key_lc in str(item.get("config_key", "")).lower()
        or key_lc in str(item.get("config_value", "")).lower()
        or key_lc in str(item.get("description", "")).lower()
    )


def _get_nested(config: Dict[str, Any], config_key: str) -> tuple:
    parts = _split_config_key(config_key)
    current: Any = config
    for part in parts:
        if not isinstance(current, dict) or part not in current:
            return False, None
        current = current[part]
    return True, current


def _set_nested(config: Dict[str, Any], config_key: str, value: Any, create_missing: bool) -> bool:
    parts = _split_config_key(config_key)
    current: Any = config
    for part in parts[:-1]:
        next_value = current.get(part) if isinstance(current, dict) else None
        if next_value is None:
            if not create_missing:
                return False
            current[part] = {}
            next_value = current[part]
        if not isinstance(next_value, dict):
            if not create_missing:
                return False
            current[part] = {}
            next_value = current[part]
        current = next_value
    leaf = parts[-1]
    if not create_missing and leaf not in current:
        return False
    current[leaf] = value
    return True


def _delete_nested(config: Dict[str, Any], config_key: str) -> bool:
    parts = _split_config_key(config_key)
    current: Any = config
    parents: List[tuple] = []
    for part in parts[:-1]:
        if not isinstance(current, dict) or part not in current or not isinstance(current[part], dict):
            return False
        parents.append((current, part))
        current = current[part]
    leaf = parts[-1]
    if not isinstance(current, dict) or leaf not in current:
        return False
    del current[leaf]

    # Prune empty dict nodes from bottom to top.
    for parent, key in reversed(parents):
        value = parent.get(key)
        if isinstance(value, dict) and not value:
            del parent[key]
        else:
            break
    return True


def _parse_config_value(raw_value: Optional[str]) -> Any:
    text = "" if raw_value is None else str(raw_value)
    if text == "":
        return ""
    try:
        return yaml.safe_load(text)
    except Exception:
        return text


def _find_config_item(config_key: str) -> Optional[Dict[str, Any]]:
    hide_keys = _safe_hide_keys()
    rows = _flatten_config(_resolved_root_config(), hide_keys=hide_keys)
    for item in rows:
        if item["config_key"] == config_key:
            return item
    return None


@router.get("", summary="获取配置项列表")
def list_configs(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    keyword: Optional[str] = Query(None, description="按配置键/值/描述模糊搜索，不区分大小写"),
    current_user: dict = Depends(get_current_user),
):
    try:
        hide_keys = _safe_hide_keys()
        rows = _flatten_config(_resolved_root_config(), hide_keys=hide_keys)
        normalized_keyword = str(keyword or "").strip()
        if normalized_keyword:
            rows = [item for item in rows if _matches_keyword(item, normalized_keyword)]
        rows.sort(key=lambda x: x["config_key"])
        total = len(rows)
        page_rows = rows[offset : offset + limit]
        return success_response(data={
            "list": page_rows,
            "page": {
                "limit": limit,
                "offset": offset,
            },
            "total": total,
        })
    except Exception as e:
        return error_response(code=500, message=str(e))


@router.get("/{config_key}", summary="获取单个配置项详情")
def get_config(
    config_key: str = Path(..., min_length=1),
    current_user: dict = Depends(get_current_user),
):
    try:
        item = _find_config_item(config_key)
        if not item:
            raise HTTPException(status_code=404, detail="Config not found")
        return success_response(data=item)
    except HTTPException:
        raise
    except Exception as e:
        return error_response(code=500, message=str(e))


class ConfigManagementCreate(BaseModel):
    config_key: str
    config_value: str
    description: Optional[str] = None


class ConfigManagementUpdate(BaseModel):
    config_value: Optional[str] = None
    description: Optional[str] = None


@router.post("", summary="创建配置项")
def create_config(
    config_data: ConfigManagementCreate = Body(...),
    current_user: dict = Depends(get_current_user),
):
    _require_config_edit_permission(current_user)
    try:
        config_key = str(config_data.config_key or "").strip()
        root = _root_config()
        exists, _ = _get_nested(root, config_key)
        if exists:
            raise HTTPException(status_code=400, detail="Config with this key already exists")

        value = _parse_config_value(config_data.config_value)
        ok = _set_nested(root, config_key, value, create_missing=True)
        if not ok:
            raise HTTPException(status_code=400, detail="Invalid config key")
        cfg.save_config()
        item = _find_config_item(config_key)
        return success_response(data=item, message="Config created successfully")
    except HTTPException:
        raise
    except Exception as e:
        return error_response(code=500, message=str(e))


@router.put("/{config_key}", summary="更新配置项")
def update_config(
    config_key: str = Path(..., min_length=1),
    config_data: ConfigManagementUpdate = Body(...),
    current_user: dict = Depends(get_current_user),
):
    _require_config_edit_permission(current_user)
    try:
        root = _root_config()
        exists, _ = _get_nested(root, config_key)
        if not exists:
            raise HTTPException(status_code=404, detail="Config not found")

        hide_keys = _safe_hide_keys()
        new_value = config_data.config_value
        if _is_masked_key(config_key, hide_keys) and str(new_value or "").strip() == "***":
            raise HTTPException(status_code=400, detail="敏感配置已脱敏，请输入新值后再保存")
        if new_value is None:
            raise HTTPException(status_code=400, detail="config_value is required")

        ok = _set_nested(root, config_key, _parse_config_value(new_value), create_missing=False)
        if not ok:
            raise HTTPException(status_code=400, detail="Invalid config key")
        cfg.save_config()
        item = _find_config_item(config_key)
        return success_response(data=item, message="Config updated successfully")
    except HTTPException:
        raise
    except Exception as e:
        return error_response(code=500, message=str(e))


@router.delete("/{config_key}", summary="删除配置项")
def delete_config(
    config_key: str = Path(..., min_length=1),
    current_user: dict = Depends(get_current_user),
):
    _require_config_edit_permission(current_user)
    try:
        root = _root_config()
        deleted = _delete_nested(root, config_key)
        if not deleted:
            raise HTTPException(status_code=404, detail="Config not found")
        cfg.save_config()
        return success_response(message="Config deleted successfully")
    except HTTPException:
        raise
    except Exception as e:
        return error_response(code=500, message=str(e))
