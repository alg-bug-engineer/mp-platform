"""
七牛云图床服务
用于将即梦生成的图片上传到七牛云，获取可长期访问的链接
"""
import os
import sys
import uuid
import re
from typing import List, Dict, Tuple
from urllib.parse import urlparse

from core.config import cfg
from core.log import get_logger

logger = get_logger(__name__)

try:
    import qiniu
    from qiniu import BucketManager, Auth
    QINIU_AVAILABLE = True
except ImportError as _qiniu_import_err:
    QINIU_AVAILABLE = False
    logger.warning(
        "[Qiniu] qiniu SDK 未安装，图片上传功能不可用 | "
        "error=%s | python=%s | path=%s",
        _qiniu_import_err,
        sys.executable,
        sys.path,
    )

def get_qiniu_config() -> Tuple[str, str, str, str]:
    """获取动态七牛云配置"""
    ak = os.environ.get("QINIU_AK") or cfg.get("qiniu.access_key", "")
    sk = os.environ.get("QINIU_SK") or cfg.get("qiniu.secret_key", "")
    bucket = os.environ.get("QINIU_BUCKET") or cfg.get("qiniu.bucket", "")
    domain = os.environ.get("QINIU_DOMAIN") or cfg.get("qiniu.domain", "")
    return ak, sk, bucket, domain


def is_configured() -> bool:
    """检查七牛云是否已配置"""
    if not QINIU_AVAILABLE:
        return False
    ak, sk, bucket, domain = get_qiniu_config()
    return all([ak, sk, bucket, domain])


def upload_image_to_qiniu(image_url: str) -> Tuple[bool, str]:
    """
    将网络图片上传到七牛云
    
    Args:
        image_url: 原始图片URL（即梦生成的图片URL）
        
    Returns:
        (success, new_url_or_error)
        - success: True 表示上传成功
        - new_url_or_error: 成功时返回七牛云URL，失败时返回错误信息
    """
    logger.debug("[Qiniu] upload_image_to_qiniu 调用 | python=%s | url=%s", sys.executable, image_url[:80])

    if not QINIU_AVAILABLE:
        logger.warning("[Qiniu] SDK 不可用，跳过上传 | python=%s | sys.path=%s", sys.executable, sys.path)
        return False, "qiniu SDK 未安装，请执行: pip install qiniu"

    ak, sk, bucket, domain = get_qiniu_config()
    logger.debug("[Qiniu] 配置读取 | bucket=%s | domain=%s | ak_set=%s | sk_set=%s",
                 bucket, domain, bool(ak), bool(sk))
    if not all([ak, sk, bucket, domain]):
        return False, "七牛云未配置，请设置 QINIU_AK/QINIU_SK/QINIU_BUCKET/QINIU_DOMAIN"

    try:
        q = Auth(ak, sk)
        bucket_manager = BucketManager(q)

        try:
            path = image_url.split("?")[0]
            _, ext = os.path.splitext(path)
            if not ext or len(ext) > 5:
                ext = ".jpg"
        except Exception:
            ext = ".jpg"

        key = f"uploads/{uuid.uuid4().hex}{ext}"
        logger.debug("[Qiniu] 开始 fetch | bucket=%s | key=%s | url=%s", bucket, key, image_url[:80])

        ret, info = bucket_manager.fetch(image_url, bucket, key)
        status = getattr(info, "status_code", None)
        logger.debug("[Qiniu] fetch 响应 | status=%s | ret=%s", status, ret)

        if status == 200:
            final_url = f"{domain.rstrip('/')}/{ret['key']}"
            logger.info("[Qiniu] 上传成功: %s -> %s", image_url[:50], final_url)
            return True, final_url

        error_msg = f"上传失败: 状态码={status}, 详情={info}"
        logger.warning("[Qiniu] %s", error_msg)
        return False, error_msg
            
    except Exception as e:
        logger.exception("[Qiniu] 上传异常: %s", e)
        return False, f"上传异常: {e}"


def upload_images_batch(image_urls: List[str]) -> Dict[str, str]:
    """
    批量上传图片到七牛云
    
    Args:
        image_urls: 图片URL列表
        
    Returns:
        原URL到新URL的映射字典，上传失败的保留原URL
    """
    mapping = {}
    
    if not image_urls:
        return mapping
    
    if not is_configured():
        logger.warning("[Qiniu] 未配置，跳过上传，保留原URL")
        for url in image_urls:
            mapping[url] = url
        return mapping
    
    logger.info("[Qiniu] 开始批量上传 %d 张图片到七牛云", len(image_urls))
    
    for idx, url in enumerate(image_urls, 1):
        if not url or not isinstance(url, str):
            continue
            
        url = url.strip()
        if not url:
            continue
        
        logger.info("[Qiniu] 处理[%d/%d]: %s", idx, len(image_urls), url[:60])
        success, new_url = upload_image_to_qiniu(url)
        
        if success:
            mapping[url] = new_url
        else:
            # 上传失败保留原URL
            mapping[url] = url
            logger.warning("[Qiniu] 上传失败保留原URL: %s", url[:60])
    
    success_count = sum(1 for k, v in mapping.items() if k != v)
    logger.info("[Qiniu] 批量上传完成: 成功 %d/%d", success_count, len(image_urls))
    
    return mapping


def replace_image_urls_in_markdown(content: str, url_mapping: Dict[str, str]) -> str:
    """
    替换 Markdown 中的图片URL
    
    Args:
        content: Markdown 内容
        url_mapping: 原URL到新URL的映射
        
    Returns:
        替换后的 Markdown 内容
    """
    if not url_mapping:
        return content
    
    result = content
    
    # 匹配 Markdown 图片语法: ![alt](url)
    pattern = r'!\[([^\]]*)\]\(([^)]+)\)'
    
    def replace_url(match):
        alt_text = match.group(1)
        old_url = match.group(2)
        # 去除URL中可能存在的空格
        old_url_clean = old_url.strip()
        
        new_url = url_mapping.get(old_url_clean, old_url_clean)
        return f'![{alt_text}]({new_url})'
    
    result = re.sub(pattern, replace_url, result)
    
    return result


def process_images_for_csdn(content: str, image_urls: List[str]) -> Tuple[str, Dict[str, str]]:
    """
    处理 CSDN 推送前的图片：上传到七牛云并替换链接
    
    Args:
        content: Markdown 内容
        image_urls: 需要上传的图片URL列表
        
    Returns:
        (new_content, url_mapping)
        - new_content: 替换后的 Markdown 内容
        - url_mapping: URL映射字典
    """
    if not image_urls:
        return content, {}
    
    # 上传图片到七牛云
    url_mapping = upload_images_batch(image_urls)
    
    # 替换 Markdown 中的图片链接
    new_content = replace_image_urls_in_markdown(content, url_mapping)
    
    return new_content, url_mapping
