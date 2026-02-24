"""
微信公众号草稿箱服务

基于 pipeline.py 的 WeChatDraftHelper 改造，支持多用户隔离。
"""

from pathlib import Path
from typing import Dict, Optional
import requests
import json
import time
import re
from bs4 import BeautifulSoup

from core.image_service import ImageService


class WeChatDraftService:
    """微信公众号草稿箱服务（多用户隔离）"""

    # 微信限制
    MAX_ARTICLE_IMG_SIZE = 1 * 1024 * 1024   # 正文图片 1MB
    MAX_COVER_IMG_SIZE = 9 * 1024 * 1024     # 封面图片 9MB
    MAX_TITLE_BYTES = 50  # 标题字节限制（保守值，避免 errcode=45003）

    def __init__(self, app_id: str, app_secret: str, owner_id: str):
        """
        初始化微信草稿服务

        Args:
            app_id: 微信公众号 App ID
            app_secret: 微信公众号 App Secret
            owner_id: 用户ID（用于图片存储隔离）
        """
        self.app_id = app_id
        self.app_secret = app_secret
        self.owner_id = owner_id
        self.token = None
        self.token_expires_at = 0
        self.image_service = ImageService(owner_id)

    def get_access_token(self) -> str:
        """获取或刷新 Access Token"""
        if self.token and time.time() < self.token_expires_at:
            return self.token

        url = (
            f"https://api.weixin.qq.com/cgi-bin/token"
            f"?grant_type=client_credential"
            f"&appid={self.app_id}"
            f"&secret={self.app_secret}"
        )
        resp = requests.get(url)
        data = resp.json()

        if 'access_token' in data:
            self.token = data['access_token']
            # 提前 5 分钟过期，防止临界点问题
            self.token_expires_at = time.time() + data['expires_in'] - 300
            print(f"✅ 获取 Access Token 成功")
            return self.token
        else:
            raise Exception(f"获取 Token 失败: {data}")

    def upload_cover_image(self, image_path: Path) -> str:
        """
        上传封面图片（永久素材）

        Args:
            image_path: 本地图片路径

        Returns:
            media_id
        """
        token = self.get_access_token()
        url = (
            f"https://api.weixin.qq.com/cgi-bin/material/add_material"
            f"?access_token={token}&type=image"
        )

        # 压缩图片到 9MB 以内
        compressed_path = self.image_service.compress_local_file(
            image_path,
            self.MAX_COVER_IMG_SIZE
        )

        if not compressed_path:
            raise Exception(f"封面图片压缩失败: {image_path}")

        try:
            filename = compressed_path.name
            with open(compressed_path, 'rb') as f:
                files = {'media': (filename, f, 'image/jpeg')}
                resp = requests.post(url, files=files)

            result = resp.json()

            if 'media_id' in result:
                print(f"✅ 封面上传成功: {result['media_id']}")
                return result['media_id']
            else:
                raise Exception(f"封面上传失败: {result}")

        except Exception as e:
            raise Exception(f"上传封面图片异常: {e}")

    def upload_article_image(self, image_url: str) -> Optional[str]:
        """
        上传正文图片（临时素材，返回 URL）

        Args:
            image_url: 图片 URL

        Returns:
            微信 CDN URL，失败返回 None
        """
        token = self.get_access_token()
        url = (
            f"https://api.weixin.qq.com/cgi-bin/media/uploadimg"
            f"?access_token={token}"
        )

        # 下载并压缩（内存处理，不落盘）
        compressed_stream = self.image_service.download_and_compress(
            image_url,
            self.MAX_ARTICLE_IMG_SIZE
        )

        if not compressed_stream:
            print(f"   ❌ 图片下载或压缩失败: {image_url}")
            return None

        try:
            import uuid
            filename = f"img_{uuid.uuid4().hex}.jpg"
            files = {'media': (filename, compressed_stream, 'image/jpeg')}
            resp = requests.post(url, files=files)
            result = resp.json()

            if 'url' in result:
                return result['url']
            else:
                print(f"   ❌ 正文图片上传失败: {result}")
                return None

        except Exception as e:
            print(f"   ❌ 上传正文图片异常: {e}")
            return None

    def process_html_images(self, html_content: str) -> str:
        """
        处理 HTML 中的图片（替换为微信 URL）

        Args:
            html_content: 原始 HTML

        Returns:
            处理后的 HTML
        """
        if not html_content:
            return ""

        print("🔄 开始处理正文图片...")
        soup = BeautifulSoup(html_content, 'html.parser')
        imgs = soup.find_all('img')

        count = 0
        for img in imgs:
            src = img.get('src')
            if not src:
                continue

            # 跳过已经是微信链接的图片
            if 'mmbiz.qpic.cn' in src:
                continue

            # 上传并替换
            try:
                wechat_url = self.upload_article_image(src)
                if wechat_url:
                    img['src'] = wechat_url
                    # 清理多余属性
                    for attr in ['data-src', 'style', 'width', 'height']:
                        if img.get(attr):
                            del img[attr]
                    count += 1
                else:
                    print(f"   ⚠️ 图片上传失败，保留原 URL: {src[:60]}...")
            except Exception as e:
                print(f"   ❌ 处理图片异常 {src[:60]}...: {e}")

        print(f"✅ 正文图片处理完成，成功替换 {count} 张。")
        return str(soup)

    @staticmethod
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

    def submit_draft(self, article_data: dict) -> str:
        """
        提交草稿到微信公众号

        Args:
            article_data: 文章数据字典，必须包含：
                - title: 标题
                - content: 正文（HTML）
                - thumb_media_id: 封面 media_id
                - author: 作者（可选）
                - digest: 摘要（可选）
                - content_source_url: 原文链接（可选）
                - need_open_comment: 是否打开评论（默认1）
                - only_fans_can_comment: 仅粉丝可评论（默认0）

        Returns:
            media_id
        """
        # 清理标题，避免 errcode=45003 (title size out of limit)
        raw_title = article_data.get('title', '未命名草稿')
        article_data['title'] = self._clean_title(raw_title, max_bytes=self.MAX_TITLE_BYTES)

        token = self.get_access_token()
        url = (
            f"https://api.weixin.qq.com/cgi-bin/draft/add"
            f"?access_token={token}"
        )

        payload = {"articles": [article_data]}

        # 确保中文正常显示
        json_data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        headers = {'Content-Type': 'application/json; charset=utf-8'}

        try:
            resp = requests.post(url, data=json_data, headers=headers)
            result = resp.json()

            if 'media_id' in result:
                print(f"🎉 草稿发布成功！Media ID: {result['media_id']}")
                return result['media_id']
            else:
                raise Exception(f"草稿提交失败: {result}")

        except Exception as e:
            raise Exception(f"提交草稿异常: {e}")
