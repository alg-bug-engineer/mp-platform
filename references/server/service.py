# -*- coding: utf-8 -*-
"""
七牛云图片上传服务 + 小红书热点(60s API)封装
供 Node.js 调用

- 七牛：POST /fetch   批量抓取网络图片并上传七牛
- 小红书热点：GET /xhs/hot   从 60s API 获取小红书热点词
- 健康检查：GET /health
"""

from flask import Flask, request, jsonify
import os
import uuid
import json
import threading
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

import requests
import qiniu
from qiniu import BucketManager

app = Flask(__name__)

# ================= 配置区 =================
# Qiniu
ACCESS_KEY = os.environ.get("QINIU_AK", "SNAgrFIInkIbvDfsLviLWCleJzTmyoyqVc4aHP4L")
SECRET_KEY = os.environ.get("QINIU_SK", "mEpjB1LRdRMtPL-FSRoLk98k3j-dH3OGK0rSfL2p")
BUCKET_NAME = os.environ.get("QINIU_BUCKET", "zhishiaichiyu")
DOMAIN = os.environ.get("QINIU_DOMAIN", "http://t9ewq12hu.hd-bkt.clouddn.com")
PORT = int(os.environ.get("QINIU_SERVICE_PORT", 5112))

# 60s API（可改为你自己部署的地址）
# 官方实例： https://60s.viki.moe
SIXTY_S_BASE = os.environ.get("SIXTY_S_BASE", "https://60s.viki.moe").rstrip("/")
SIXTY_S_TIMEOUT = int(os.environ.get("SIXTY_S_TIMEOUT", "10"))

# 缓存配置
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
CACHE_FILE = os.path.join(CACHE_DIR, "xhs_hot_cache.json")
CACHE_TTL_MINUTES = 10  # 缓存有效期（分钟）
_cache_lock = threading.Lock()  # 缓存文件读写锁
# ==========================================


# ================= 缓存工具函数 =================
def _ensure_cache_dir():
    """确保缓存目录存在"""
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)
        print(f"[Cache] 创建缓存目录: {CACHE_DIR}")


def _load_cache() -> Dict[str, Any]:
    """加载缓存文件，返回缓存数据结构"""
    _ensure_cache_dir()
    if not os.path.exists(CACHE_FILE):
        print(f"[Cache] 缓存文件不存在，返回空结构")
        return {"current": None, "history": []}

    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            print(f"[Cache] 成功加载缓存文件，历史记录数: {len(data.get('history', []))}")
            return data
    except Exception as e:
        print(f"[Cache] ✗ 加载缓存文件失败: {e}")
        return {"current": None, "history": []}


def _save_cache(cache_data: Dict[str, Any]):
    """保存缓存到文件"""
    _ensure_cache_dir()
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
        history_count = len(cache_data.get("history", []))
        print(f"[Cache] ✓ 缓存已保存，历史记录数: {history_count}")
    except Exception as e:
        print(f"[Cache] ✗ 保存缓存文件失败: {e}")


def _is_cache_valid(cache_entry: Optional[Dict], cnt: int) -> bool:
    """检查缓存是否有效（10分钟内且cnt匹配）"""
    if not cache_entry:
        print(f"[Cache] 缓存条目为空，无效")
        return False

    try:
        cached_time = datetime.fromisoformat(cache_entry.get("timestamp", ""))
        cached_cnt = cache_entry.get("cnt", 0)
        now = datetime.now()
        age_minutes = (now - cached_time).total_seconds() / 60

        # cnt 必须匹配且在有效期内
        if cached_cnt >= cnt and age_minutes < CACHE_TTL_MINUTES:
            print(f"[Cache] ✓ 缓存有效 - 年龄: {age_minutes:.1f}分钟, 缓存cnt: {cached_cnt}, 请求cnt: {cnt}")
            return True
        else:
            print(f"[Cache] ✗ 缓存无效 - 年龄: {age_minutes:.1f}分钟(限制{CACHE_TTL_MINUTES}), 缓存cnt: {cached_cnt}, 请求cnt: {cnt}")
            return False
    except Exception as e:
        print(f"[Cache] ✗ 解析缓存时间失败: {e}")
        return False


def _get_cached_xhs_hot(cnt: int) -> Optional[List[Dict[str, Any]]]:
    """获取缓存的小红书热点数据"""
    with _cache_lock:
        cache_data = _load_cache()
        current = cache_data.get("current")

        if _is_cache_valid(current, cnt):
            cached_data = current.get("data", [])
            # 返回请求数量的数据
            return cached_data[:cnt]

        return None


def _set_cached_xhs_hot(cnt: int, data: List[Dict[str, Any]]):
    """设置缓存的小红书热点数据，旧数据移入历史"""
    with _cache_lock:
        cache_data = _load_cache()

        # 如果有旧的current，移入history
        old_current = cache_data.get("current")
        if old_current and old_current.get("data"):
            cache_data.setdefault("history", []).append(old_current)
            print(f"[Cache] 旧缓存移入历史，时间: {old_current.get('timestamp')}")

        # 设置新的current
        cache_data["current"] = {
            "timestamp": datetime.now().isoformat(),
            "cnt": cnt,
            "data": data
        }

        _save_cache(cache_data)
        print(f"[Cache] 新缓存已设置，数据条数: {len(data)}, cnt: {cnt}")


# ================= 七牛上传相关 =================
def fetch_and_get_url(image_url: str, custom_key: Optional[str] = None) -> Dict[str, Any]:
    """抓取网络图片并返回七牛云存储后的完整链接"""
    q = qiniu.Auth(ACCESS_KEY, SECRET_KEY)
    bucket = BucketManager(q)

    if not custom_key:
        try:
            path = image_url.split("?")[0]
            _, ext = os.path.splitext(path)
            if not ext or len(ext) > 5:
                ext = ".jpg"
        except Exception:
            ext = ".jpg"
        custom_key = f"uploads/{uuid.uuid4().hex}{ext}"

    ret, info = bucket.fetch(image_url, BUCKET_NAME, custom_key)

    if getattr(info, "status_code", None) == 200:
        final_url = f"{DOMAIN.rstrip('/')}/{ret['key']}"
        return {"success": True, "url": final_url, "key": ret["key"]}
    return {"success": False, "error": f"状态码: {getattr(info,'status_code',None)}, 详情: {info}"}


@app.route("/fetch", methods=["POST"])
def fetch_images():
    """
    批量抓取图片
    请求体: {"urls": ["url1", "url2", ...]}
    响应: {"success": true/false, "mapping": {"原url": "新url", ...}, "errors": [...]}
    """
    data = request.get_json(silent=True) or {}
    urls = data.get("urls", [])

    print(f"\n{'='*60}")
    print(f"[Qiniu Service] 收到批量上传请求，URL数量: {len(urls)}")
    print(f"{'='*60}")

    if not urls:
        print("[Qiniu Service] 无URL，返回空结果")
        return jsonify({"success": True, "mapping": {}, "errors": []})

    for idx, url in enumerate(urls):
        print(f"[Qiniu Service] 待处理[{idx}]: {str(url)[:80]}...")

    mapping: Dict[str, str] = {}
    errors: List[str] = []

    for idx, url in enumerate(urls):
        if not url or not isinstance(url, str):
            print(f"[Qiniu Service] 跳过[{idx}]: 无效URL")
            continue

        url = url.strip()
        if not url:
            print(f"[Qiniu Service] 跳过[{idx}]: 空URL")
            continue

        print(f"\n[Qiniu Service] 处理[{idx+1}/{len(urls)}]: {url[:60]}...")
        result = fetch_and_get_url(url)

        if result.get("success"):
            mapping[url] = result["url"]
            print(f"[Qiniu Service] ✓ 成功[{idx}]: {url[:40]}...")
            print(f"[Qiniu Service]    -> 新URL: {result['url']}")
        else:
            mapping[url] = url  # 失败时保留原 URL
            error_msg = f"{url[:50]}: {result.get('error')}"
            errors.append(error_msg)
            print(f"[Qiniu Service] ✗ 失败[{idx}]: {error_msg}")

    print(f"\n{'='*60}")
    print("[Qiniu Service] 批量处理完成")
    print(f"[Qiniu Service] 成功: {len(mapping) - len(errors)}/{len(urls)}")
    print(f"[Qiniu Service] 失败: {len(errors)}/{len(urls)}")
    print(f"[Qiniu Service] 映射数量: {len(mapping)}")
    print(f"{'='*60}\n")

    return jsonify({"success": len(errors) == 0, "mapping": mapping, "errors": errors})


# ================= 小红书热点（60s API）相关 =================
def fetch_xhs_hot_from_60s(cnt: int = 10) -> Optional[List[Dict[str, Any]]]:
    """
    从 60s API 获取小红书热点（热词/热搜）
    60s 接口：GET {SIXTY_S_BASE}/v2/rednote

    返回示例条目字段（可能会随上游更新增减字段）：
    - rank: int
    - title: str
    - score: str
    - word_type: str
    - work_type_icon: str
    - link: str
    """
    url = f"{SIXTY_S_BASE}/v2/rednote"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    print(f"\n[XHS-Hot] {'='*50}")
    print(f"[XHS-Hot] 开始请求60s API")
    print(f"[XHS-Hot] URL: {url}")
    print(f"[XHS-Hot] 请求数量: {cnt}")
    print(f"[XHS-Hot] 超时设置: {SIXTY_S_TIMEOUT}秒")

    try:
        print(f"[XHS-Hot] 发送HTTP GET请求...")
        resp = requests.get(url, headers=headers, timeout=SIXTY_S_TIMEOUT)
        print(f"[XHS-Hot] 响应状态码: {resp.status_code}")
        print(f"[XHS-Hot] 响应头Content-Type: {resp.headers.get('Content-Type', 'N/A')}")

        resp.raise_for_status()
        payload = resp.json()
        print(f"[XHS-Hot] JSON解析成功，响应code: {payload.get('code', 'N/A')}")

        # 60s API 通常结构：{"code":200,"message":"...","data":[...]}
        data = payload.get("data")
        if not isinstance(data, list):
            print(f"[XHS-Hot] ✗ 响应data字段不是列表，类型: {type(data)}")
            return None

        print(f"[XHS-Hot] 上游返回数据条数: {len(data)}")

        items = data[: max(0, int(cnt))]
        # 只保留常用字段（你也可以直接返回 items 原样）
        cleaned: List[Dict[str, Any]] = []
        for it in items:
            cleaned.append(
                {
                    "rank": it.get("rank"),
                    "title": it.get("title"),
                    "score": it.get("score"),
                    "word_type": it.get("word_type"),
                    "work_type_icon": it.get("work_type_icon"),
                    "link": it.get("link"),
                }
            )

        print(f"[XHS-Hot] ✓ 成功获取 {len(cleaned)} 条热点数据")
        if cleaned:
            print(f"[XHS-Hot] 第1条: {cleaned[0].get('title', 'N/A')[:30]}...")
        print(f"[XHS-Hot] {'='*50}\n")

        return cleaned

    except requests.exceptions.Timeout as e:
        print(f"[XHS-Hot] ✗ 请求超时: {e}")
        print(f"[XHS-Hot] {'='*50}\n")
        return None
    except requests.exceptions.ConnectionError as e:
        print(f"[XHS-Hot] ✗ 连接错误: {e}")
        print(f"[XHS-Hot] {'='*50}\n")
        return None
    except requests.exceptions.HTTPError as e:
        print(f"[XHS-Hot] ✗ HTTP错误: {e}")
        print(f"[XHS-Hot] {'='*50}\n")
        return None
    except json.JSONDecodeError as e:
        print(f"[XHS-Hot] ✗ JSON解析失败: {e}")
        print(f"[XHS-Hot] {'='*50}\n")
        return None
    except Exception as e:
        print(f"[XHS-Hot] ✗ 未知异常: {type(e).__name__}: {e}")
        print(f"[XHS-Hot] {'='*50}\n")
        return None


@app.route("/xhs/hot", methods=["GET"])
def xhs_hot():
    """
    获取小红书热点（来自 60s API，支持本地缓存）

    Query:
      - cnt: int (默认 10，最大 100)
      - force: bool (默认 false，设为 true 强制刷新缓存)
    Response:
      {
        "success": true/false,
        "data": [...],
        "upstream": "https://60s.viki.moe/v2/rednote",
        "cached": true/false,
        "cache_time": "2024-01-26T10:00:00" (如果是缓存),
        "error": "..." (失败时)
      }
    """
    request_id = uuid.uuid4().hex[:8]
    print(f"\n[API /xhs/hot] {'='*50}")
    print(f"[API /xhs/hot] 请求ID: {request_id}")
    print(f"[API /xhs/hot] 请求参数: {dict(request.args)}")

    try:
        cnt = int(request.args.get("cnt", "10"))
    except Exception as e:
        print(f"[API /xhs/hot] cnt参数解析失败: {e}, 使用默认值10")
        cnt = 10

    # 是否强制刷新
    force_refresh = request.args.get("force", "").lower() in ("true", "1", "yes")
    print(f"[API /xhs/hot] 请求数量: {cnt}, 强制刷新: {force_refresh}")

    # 做个简单限流/保护：最多 100 条
    if cnt < 0:
        cnt = 0
    if cnt > 100:
        cnt = 100
        print(f"[API /xhs/hot] cnt超过上限，限制为100")

    upstream = f"{SIXTY_S_BASE}/v2/rednote"

    # 尝试从缓存获取
    if not force_refresh:
        print(f"[API /xhs/hot] 检查缓存...")
        cached_data = _get_cached_xhs_hot(cnt)
        if cached_data is not None:
            # 获取缓存时间用于响应
            cache_info = _load_cache().get("current", {})
            cache_time = cache_info.get("timestamp", "")
            print(f"[API /xhs/hot] ✓ 缓存命中! 返回 {len(cached_data)} 条数据")
            print(f"[API /xhs/hot] 缓存时间: {cache_time}")
            print(f"[API /xhs/hot] {'='*50}\n")
            return jsonify({
                "success": True,
                "data": cached_data,
                "upstream": upstream,
                "cached": True,
                "cache_time": cache_time
            })
        print(f"[API /xhs/hot] 缓存未命中，需要请求上游")
    else:
        print(f"[API /xhs/hot] 强制刷新模式，跳过缓存检查")

    # 从上游获取数据
    print(f"[API /xhs/hot] 开始请求上游API...")
    data = fetch_xhs_hot_from_60s(cnt=cnt)

    if data is None:
        print(f"[API /xhs/hot] ✗ 上游请求失败")
        print(f"[API /xhs/hot] {'='*50}\n")
        return jsonify({
            "success": False,
            "data": [],
            "upstream": upstream,
            "cached": False,
            "error": "获取失败或上游返回异常"
        }), 502

    # 保存到缓存
    print(f"[API /xhs/hot] 保存数据到缓存...")
    _set_cached_xhs_hot(cnt, data)

    print(f"[API /xhs/hot] ✓ 成功返回 {len(data)} 条新鲜数据")
    print(f"[API /xhs/hot] {'='*50}\n")

    return jsonify({
        "success": True,
        "data": data,
        "upstream": upstream,
        "cached": False
    })


# ================= 健康检查 =================
@app.route("/health", methods=["GET"])
def health():
    """健康检查，包含缓存状态信息"""
    cache_status = {
        "cache_file": CACHE_FILE,
        "cache_ttl_minutes": CACHE_TTL_MINUTES,
        "cache_exists": os.path.exists(CACHE_FILE)
    }

    # 尝试获取缓存详情
    try:
        if os.path.exists(CACHE_FILE):
            cache_data = _load_cache()
            current = cache_data.get("current")
            if current:
                cache_status["current_cache_time"] = current.get("timestamp")
                cache_status["current_cache_cnt"] = current.get("cnt")
                cache_status["current_cache_items"] = len(current.get("data", []))
            cache_status["history_count"] = len(cache_data.get("history", []))
    except Exception as e:
        cache_status["error"] = str(e)

    return jsonify({
        "status": "ok",
        "cache": cache_status
    })


if __name__ == "__main__":
    print(f"\n{'='*60}")
    print(f"服务启动在端口 {PORT}")
    print(f"{'='*60}")
    print(f"[Qiniu] Bucket: {BUCKET_NAME}")
    print(f"[Qiniu] Domain: {DOMAIN}")
    print(f"[60s] Base: {SIXTY_S_BASE}")
    print(f"[60s] Timeout: {SIXTY_S_TIMEOUT}秒")
    print(f"[Cache] 目录: {CACHE_DIR}")
    print(f"[Cache] 文件: {CACHE_FILE}")
    print(f"[Cache] TTL: {CACHE_TTL_MINUTES}分钟")
    print(f"{'='*60}\n")

    # 确保缓存目录存在
    _ensure_cache_dir()

    app.run(host="0.0.0.0", port=PORT)
