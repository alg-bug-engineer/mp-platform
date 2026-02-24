"""
图片下载、压缩和处理服务

用于处理即梦生成的图片和临时外链图片：
- 即梦图片：持久化到用户目录 imgs/{owner_id}/jimeng_*.jpg
- 临时图片：内存流式处理，不落盘
"""

from pathlib import Path
from io import BytesIO
from typing import Optional
import uuid
import requests
from PIL import Image


class ImageService:
    """图片下载、压缩、处理服务（多用户隔离）"""

    def __init__(self, owner_id: str):
        """
        初始化图片服务

        Args:
            owner_id: 用户ID，用于目录隔离
        """
        self.owner_id = owner_id
        self.owner_dir = Path(f"imgs/{owner_id}")
        self.owner_dir.mkdir(parents=True, exist_ok=True)

    def download_jimeng_image(self, url: str, prefix: str = "jimeng") -> Optional[Path]:
        """
        下载即梦图片到用户目录（持久化）

        Args:
            url: 即梦图片 URL
            prefix: 文件名前缀

        Returns:
            本地文件路径，失败返回 None
        """
        try:
            filename = f"{prefix}_{uuid.uuid4().hex}.jpg"
            local_path = self.owner_dir / filename

            # 下载图片
            headers = {'User-Agent': 'Mozilla/5.0'}
            resp = requests.get(url, headers=headers, timeout=30)
            resp.raise_for_status()

            # 保存到本地
            with open(local_path, 'wb') as f:
                f.write(resp.content)

            print(f"✅ 即梦图片已下载: {local_path.name}")
            return local_path

        except Exception as e:
            print(f"❌ 下载即梦图片失败 {url}: {e}")
            return None

    def compress_image_stream(
        self,
        image_bytes: bytes,
        max_size: int,
        format: str = 'JPEG',
    ) -> BytesIO:
        """
        内存流式压缩图片（不落盘）

        Args:
            image_bytes: 原始图片字节流
            max_size: 最大文件大小（字节）
            format: 输出格式（默认 JPEG）

        Returns:
            压缩后的字节流
        """
        img = Image.open(BytesIO(image_bytes))

        # 转换为 RGB（JPEG 不支持透明度）
        if img.mode != 'RGB':
            img = img.convert('RGB')

        quality = 85
        scale = 0.9

        while True:
            output = BytesIO()
            img.save(output, format=format, quality=quality)
            output_size = output.tell()

            if output_size <= max_size:
                output.seek(0)
                return output

            # 降低质量
            if quality > 30:
                quality -= 10
            else:
                # 缩小尺寸
                width, height = img.size
                new_width = int(width * scale)
                new_height = int(height * scale)

                if new_width < 100 or new_height < 100:
                    # 已经缩到极限，返回当前结果
                    output.seek(0)
                    return output

                img = img.resize((new_width, new_height), Image.LANCZOS)

    def download_and_compress(
        self,
        url: str,
        max_size: int,
    ) -> Optional[BytesIO]:
        """
        下载外链图片并压缩（内存处理，不落盘）

        Args:
            url: 图片 URL
            max_size: 最大文件大小（字节）

        Returns:
            压缩后的字节流，失败返回 None
        """
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            resp = requests.get(url, headers=headers, timeout=30)
            resp.raise_for_status()

            return self.compress_image_stream(resp.content, max_size)

        except Exception as e:
            print(f"❌ 下载并压缩图片失败 {url}: {e}")
            return None

    def compress_local_file(
        self,
        local_path: Path,
        max_size: int,
    ) -> Optional[Path]:
        """
        压缩本地图片文件（覆盖原文件）

        Args:
            local_path: 本地图片路径
            max_size: 最大文件大小（字节）

        Returns:
            压缩后的文件路径（同原路径），失败返回 None
        """
        if not local_path.exists():
            print(f"⚠️ 文件不存在: {local_path}")
            return None

        file_size = local_path.stat().st_size

        # 如果已经符合大小要求，直接返回
        if file_size <= max_size:
            return local_path

        print(f"   ⚠️ 图片({file_size/1024:.0f}KB)超限，正在压缩...")

        try:
            # 读取图片
            with open(local_path, 'rb') as f:
                image_bytes = f.read()

            # 压缩
            compressed_stream = self.compress_image_stream(image_bytes, max_size)

            # 覆盖原文件
            with open(local_path, 'wb') as f:
                f.write(compressed_stream.read())

            new_size = local_path.stat().st_size
            print(f"   ✅ 压缩完成: {new_size/1024:.0f}KB")

            return local_path

        except Exception as e:
            print(f"   ❌ 压缩异常: {e}")
            return None
