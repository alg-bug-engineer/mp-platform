import requests
import json
import os
import re
import base64
import time
import uuid
from pathlib import Path
from typing import Dict, Iterable, Tuple, Optional

from bs4 import BeautifulSoup
from PIL import Image
from bs4 import BeautifulSoup, NavigableString
import os
import re  # 新增正则模块
from playwright.sync_api import sync_playwright

try:
    import markdown as simple_markdown
except ImportError:
    simple_markdown = None

class WeChatDraftHelper:
    def __init__(self, appid, appsecret):
        self.appid = appid
        self.appsecret = appsecret
        self.token = None
        self.token_expires_at = 0
        
        base_dir = Path(__file__).resolve().parent
        self.asset_dir = base_dir / "imgs"
        self.asset_dir.mkdir(exist_ok=True)
            
        # 限制配置
        self.max_article_img_size = 1 * 1024 * 1024  # 正文图片限制 1MB
        self.max_cover_img_size = 9 * 1024 * 1024    # 封面图片限制 10MB (留点余量)

    def get_access_token(self):
        """获取或刷新 Access Token"""
        if self.token and time.time() < self.token_expires_at:
            return self.token
            
        url = f"https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid={self.appid}&secret={self.appsecret}"
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

    def _compress_image(self, local_path, max_size):
        """通用图片压缩逻辑"""
        if not os.path.exists(local_path):
            return None
            
        file_size = os.path.getsize(local_path)
        if file_size <= max_size:
            return local_path

        print(f"   ⚠️ 图片({file_size/1024:.0f}KB)超限，正在压缩...")
        try:
            img = Image.open(local_path)
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            quality = 85
            scale = 0.9
            target_path = local_path # 覆盖原文件
            
            while True:
                img.save(target_path, format='JPEG', quality=quality)
                if os.path.getsize(target_path) <= max_size:
                    break
                
                if quality > 30:
                    quality -= 10
                else:
                    width, height = img.size
                    img = img.resize((int(width * scale), int(height * scale)), Image.LANCZOS)
        except Exception as e:
            print(f"   ❌ 压缩异常: {e}")
            
        return local_path

    def upload_cover_image(self, file_path):
        """
        步骤A：上传封面图片 (永久素材)
        返回: media_id
        """
        token = self.get_access_token()
        url = f"https://api.weixin.qq.com/cgi-bin/material/add_material?access_token={token}&type=image"
        
        # 1. 压缩封面到 10MB 以内
        processed_path = self._compress_image(file_path, self.max_cover_img_size)
        
        try:
            filename = os.path.basename(processed_path)
            with open(processed_path, 'rb') as f:
                # 必须指定 filename，否则微信可能报错
                files = {'media': (filename, f, 'image/jpeg')}
                resp = requests.post(url, files=files)
                
            res = resp.json()
            if 'media_id' in res:
                print(f"✅ 封面上传成功: {res['media_id']}")
                return res['media_id']
            else:
                print(f"❌ 封面上传失败: {res}")
                return None
        except Exception as e:
            print(f"❌ 上传请求异常: {e}")
            return None

    def _upload_article_img(self, local_path):
        """内部方法：上传正文插图 (返回 URL)"""
        token = self.get_access_token()
        url = f"https://api.weixin.qq.com/cgi-bin/media/uploadimg?access_token={token}"
        
        # 1. 压缩到 1MB 以内
        processed_path = self._compress_image(local_path, self.max_article_img_size)
        
        try:
            filename = os.path.basename(processed_path)
            with open(processed_path, 'rb') as f:
                files = {'media': (filename, f, 'image/jpeg')}
                resp = requests.post(url, files=files)
            
            res = resp.json()
            if 'url' in res:
                return res['url']
            else:
                print(f"   ❌ 正文图片上传失败: {res}")
                return None
        except Exception as e:
            print(f"   ❌ 请求异常: {e}")
            return None

    def _save_base64_to_local(self, base64_str, prefix="temp_b64"):
        """Base64 -> 本地临时文件"""
        try:
            pattern = r'data:image/(\w+);base64,(.+)'
            match = re.search(pattern, base64_str, re.DOTALL)
            if not match: return None
            
            ext = match.group(1).replace('jpeg', 'jpg')
            data = base64.b64decode(match.group(2))
            
            filename = f"{prefix}_{uuid.uuid4().hex}.{ext}"
            path = os.path.join(self.asset_dir, filename)
            with open(path, 'wb') as f:
                f.write(data)
            return path
        except Exception:
            return None

    def _save_url_to_local(self, url):
        """HTTP URL -> 本地临时文件"""
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code != 200: return None
            
            filename = f"temp_net_{uuid.uuid4().hex}.jpg"
            path = os.path.join(self.asset_dir, filename)
            with open(path, 'wb') as f:
                f.write(resp.content)
            return path
        except Exception:
            return None

    def save_image_from_base64(self, base64_str, prefix="img"):
        """对外暴露的 Base64 存储接口"""
        return self._save_base64_to_local(base64_str, prefix=prefix)

    def save_image_from_url(self, url):
        """对外暴露的 URL 图片下载接口"""
        return self._save_url_to_local(url)

    def process_html_content(self, html_content):
        """
        步骤B：处理 HTML 正文
        将 Base64 和外链替换为微信 URL
        """
        if not html_content:
            return "", {}
        
        print("🔄 开始清洗正文 HTML...")
        soup = BeautifulSoup(html_content, 'html.parser')
        imgs = soup.find_all('img')
        
        replacements: Dict[str, str] = {}
        count = 0
        for img in imgs:
            src = img.get('src')
            if not src: continue
            # 跳过已有微信链接
            if 'mmbiz.qpic.cn' in src: continue
            
            local_path = None
            if src.startswith('data:image'):
                local_path = self._save_base64_to_local(src)
            elif src.startswith('http'):
                local_path = self._save_url_to_local(src)
            
            if local_path:
                # 上传并获取微信 URL
                wechat_url = self._upload_article_img(local_path)
                if wechat_url:
                    replacements[src] = wechat_url
                    img['src'] = wechat_url
                    # 清理杂项属性
                    for attr in ['data-src', 'style', 'width', 'height']:
                        if img.get(attr): del img[attr]
                    count += 1
        
        print(f"✅ 正文清洗完成，替换了 {count} 张图片。")
        return str(soup), replacements

    def submit_draft(self, articles_data):
        """
        步骤C：提交到草稿箱
        :param articles_data: 包含文章字典的列表 [{}, {}]
        """
        token = self.get_access_token()
        url = f"https://api.weixin.qq.com/cgi-bin/draft/add?access_token={token}"
        
        payload = {
            "articles": articles_data
        }
        
        # ensure_ascii=False 确保中文正常显示，不会转义
        json_data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        headers = {'Content-Type': 'application/json'}
        
        try:
            resp = requests.post(url, data=json_data, headers=headers)
            res = resp.json()
            if 'media_id' in res:
                print(f"🎉 草稿发布成功！Media ID: {res['media_id']}")
                return res['media_id']
            else:
                print(f"❌ 草稿发布失败: {res}")
                return None
        except Exception as e:
            print(f"❌ 提交请求异常: {e}")
            return None

def _markdown_to_html(md_text: str) -> str:
    if not md_text:
        return ""
    if simple_markdown is None:
        raise ImportError("未检测到 markdown 库，请先执行 pip install markdown")
    return simple_markdown.markdown(
        md_text,
        extensions=[
            "extra",
            "fenced_code",
            "tables"
        ]
    )


def _extract_first_base64(markdown_text: str) -> Optional[str]:
    if not markdown_text:
        return None
    pattern = re.compile(r'(data:image/[a-zA-Z0-9.+-]+;base64,[^)]+)', re.MULTILINE)
    match = pattern.search(markdown_text)
    return match.group(1) if match else None


def _extract_first_image_url(markdown_text: str) -> Optional[str]:
    """从 Markdown 中提取第一个图片 URL（非 base64）"""
    if not markdown_text:
        return None
    # 匹配 Markdown 图片语法 ![alt](url) 或 HTML <img src="url">
    md_pattern = re.compile(r'!\[[^\]]*\]\((https?://[^)]+)\)', re.MULTILINE)
    match = md_pattern.search(markdown_text)
    if match:
        return match.group(1)
    # 尝试匹配 HTML img 标签
    html_pattern = re.compile(r'<img[^>]+src=["\']?(https?://[^"\'>\s]+)["\']?', re.IGNORECASE)
    match = html_pattern.search(markdown_text)
    return match.group(1) if match else None


def _extract_title(markdown_text: str, fallback: str) -> str:
    if markdown_text:
        heading_match = re.search(r'^\s*#\s+(.+)$', markdown_text, re.MULTILINE)
        if heading_match:
            return heading_match.group(1).strip()
    return fallback


def _build_digest(html_content: str, limit: int = 120) -> str:
    if not html_content:
        return ""
    soup = BeautifulSoup(html_content, 'html.parser')
    text = soup.get_text(separator=' ', strip=True)
    return text[:limit]


def _replace_markdown_sources(markdown_text: str, replacements: Dict[str, str]) -> str:
    if not markdown_text or not replacements:
        return markdown_text
    updated = markdown_text
    for old_src, new_src in replacements.items():
        updated = updated.replace(old_src, new_src)
    return updated


def _save_history_markdown(history_dir: Path, file_name: str, content: str):
    history_dir.mkdir(exist_ok=True)
    history_path = history_dir / file_name
    with history_path.open("w", encoding="utf-8") as f:
        f.write(content)
    print(f"📝 已保存清洗后的 Markdown 到 {history_path}")
    return history_path


def _save_formatted_html(html_dir: Path, file_name: str, content: str):
    html_dir.mkdir(exist_ok=True)
    html_path = html_dir / file_name
    with html_path.open("w", encoding="utf-8") as f:
        f.write(content)
    print(f"🧾 已保存排版 HTML 到 {html_path}")


def _iter_markdown_files(posts_dir: Path) -> Iterable[Tuple[Path, str]]:
    if not posts_dir.exists():
        raise FileNotFoundError(f"posts 目录不存在: {posts_dir}")
    for md_file in sorted(posts_dir.glob("*.md")):
        with md_file.open("r", encoding="utf-8") as f:
            yield md_file, f.read()


def format_markdown(markdown_content):
    with sync_playwright() as p:
        print("[系统] 正在启动无头浏览器...")
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(permissions=["clipboard-read", "clipboard-write"])
        page = context.new_page()

        print("[系统] 正在打开 https://www.md2wechat.com/ ...")
        page.goto("https://www.md2wechat.com/")

        # --- 剪贴板 Mock (保持不变) ---
        page.evaluate("""
            window._capturedContent = '';
            navigator.clipboard.writeText = async (text) => {
                window._capturedContent = text;
                return Promise.resolve();
            };
            navigator.clipboard.write = async (data) => {
                let items = [];
                if (Array.isArray(data)) items = data;
                else if (data && typeof data[Symbol.iterator] === 'function') items = Array.from(data);
                else if (data) items = [data];

                for (const item of items) {
                    try {
                        if (item && typeof item.getType === 'function') {
                            if (item.types.includes('text/html')) {
                                const blob = await item.getType('text/html');
                                window._capturedContent = await blob.text();
                            } else if (item.types.includes('text/plain')) {
                                const blob = await item.getType('text/plain');
                                window._capturedContent = await blob.text();
                            }
                        }
                    } catch (err) { console.error(err); }
                }
                return Promise.resolve();
            };
        """)
        print("[系统] 剪贴板 Mock 拦截器已注入。")

        # 填入内容
        print("[系统] 正在填入 Markdown 内容...")
        textarea_selector = 'textarea[placeholder="在此处输入 Markdown 内容..."]'
        page.wait_for_selector(textarea_selector)
        page.fill(textarea_selector, markdown_content)

        print("[系统] 等待 5 秒让页面进行渲染...")
        page.wait_for_timeout(5000)

        print("[系统] 点击“复制”按钮...")
        button_selector = 'button:has-text("复制")'
        page.wait_for_selector(button_selector)
        page.click(button_selector)

        page.wait_for_timeout(1000) 
        copied_content = page.evaluate("window._capturedContent")

        if not copied_content:
            print("[警告] 未捕获到内容！")
        else:
            print(f"[系统] 成功捕获内容，长度: {len(copied_content)}")
            
            # --- 统一后处理逻辑 (使用 BeautifulSoup) ---
            print("[系统] 正在执行 HTML 深度后处理...")
            try:
                soup = BeautifulSoup(copied_content, 'html.parser')

                # 1. 删除包含 "图：" 的 em 标签
                for em in soup.find_all('em'):
                    if '图：' in em.get_text():
                        em.decompose()
                        print("[系统] 已删除一个图片说明标签")

                # 2. 给所有 <p> 标签增加首行缩进
                # 【重要修改】排除掉 li 内部的 p 标签，防止列表文字相对于符号发生错位
                for p in soup.find_all('p'):
                    if p.parent and p.parent.name == 'li':
                        continue  # 跳过列表中的段落
                    
                    current_style = p.get('style', '')
                    p['style'] = f"{current_style}; text-indent: 2em;"

                # =====================================================
                # 3. 列表嵌套缩进处理 & 强制增加换行
                # =====================================================
                # 逻辑：查找所有作为 li 直接子元素的 ul 或 ol (即嵌套子列表)
                nested_lists = [tag for tag in soup.find_all(['ul', 'ol']) if tag.parent and tag.parent.name == 'li']
                
                if nested_lists:
                    print(f"[系统] 检测到 {len(nested_lists)} 个嵌套子列表，正在执行“强制换行与缩进”处理...")
                    for lst in nested_lists:
                        # A. 样式缩进 (增加左填充，体现层级)
                        # 修改说明：使用 padding-left 替代单纯的 margin，这更能保证符号(bullet)跟着内容一起移动。
                        # padding-left: 40px 是浏览器的默认值，这里我们设置为 2em 确保缩进可见。
                        current_style = lst.get('style', '')
                        lst['style'] = f"{current_style}; padding-left: 2em; list-style-position: outside;"
                        
                        # C. 【需求实现】子列表内的每一个 li 前插入 br
                        child_lis = lst.find_all('li', recursive=False)
                        for child_li in child_lis:
                            br_tag = soup.new_tag('br')
                            child_li.insert_before(br_tag)

                # 4. 列表符号与内容间距处理
                for li in soup.find_all('li'):
                    if li.contents and isinstance(li.contents[0], NavigableString):
                        text_node = li.contents[0]
                        match = re.match(r'^(\s*(?:\d+\.|[•\-·]))(\s+)', text_node)
                        if match:
                            marker = match.group(1)
                            space = match.group(2)
                            new_text = marker + space + '\u3000' + text_node[match.end():]
                            text_node.replace_with(new_text)

                # 生成最终 HTML
                final_html = str(soup)
            except Exception as e:
                print(f"[错误] HTML 后处理失败: {e}")
                # 如果 BS4 处理失败，保存原始内容作为备份
                final_html = None

        browser.close()
        return final_html


def publish_posts_to_wechat(helper: WeChatDraftHelper, posts_dir: Path):
    history_dir = posts_dir.parent / "history"
    html_history_dir = posts_dir.parent / "history_html"
    for md_path, md_body in _iter_markdown_files(posts_dir):
        article_name = md_path.stem
        print(f"📄 正在处理文章《{article_name}》...")

        cover_path = None

        # 优先尝试提取 Base64 封面
        cover_base64 = _extract_first_base64(md_body)
        if cover_base64:
            print(f"   🖼️ 检测到 Base64 封面图片")
            cover_path = helper.save_image_from_base64(cover_base64, prefix=f"{article_name}_cover")
        else:
            # 尝试提取 URL 封面
            cover_url = _extract_first_image_url(md_body)
            if cover_url:
                print(f"   🌐 检测到 URL 封面图片: {cover_url[:60]}...")
                cover_path = helper.save_image_from_url(cover_url)

        if not cover_path:
            print(f"⚠️ 未在 {md_path.name} 中找到有效封面图片，已跳过。")
            continue

        thumb_media_id = helper.upload_cover_image(cover_path)
        if not thumb_media_id:
            print(f"⚠️ 封面上传失败，跳过 {md_path.name}")
            continue

        try:
            html_content = _markdown_to_html(md_body)
        except ImportError as err:
            print(f"❌ Markdown 转 HTML 失败: {err}")
            break

        clean_content, replacement_map = helper.process_html_content(html_content)
        if not clean_content:
            clean_content = html_content

        cleaned_markdown = _replace_markdown_sources(md_body, replacement_map)
        _save_history_markdown(history_dir, md_path.name, cleaned_markdown)

        formatted_html = format_markdown(cleaned_markdown)
        if formatted_html:
            print("✨ 使用 Format 排版 HTML")
            html_file_name = md_path.with_suffix(".html").name
            _save_formatted_html(html_history_dir, html_file_name, formatted_html)
        else:
            print("ℹ️ Format 排版失败，改用普通 HTML")
        final_content = formatted_html or clean_content
        print(f"📌 当前正文来源: {'Format' if formatted_html else '普通 HTML'}")
        article_title = _extract_title(md_body, fallback=article_name)
        digest = _build_digest(final_content)

        article_payload = {
            "article_type": "news",
            "title": article_title,
            "author": "芝士AI吃鱼",
            "digest": "",
            "content": final_content,
            "content_source_url": "",
            "thumb_media_id": thumb_media_id,
            "need_open_comment": 1,
            "only_fans_can_comment": 0
        }
        
        print(f"🚀 正在提交《{article_title}》到草稿箱...")
        helper.submit_draft([article_payload])


def _load_app_config():
    app_id = "wx7643d18e996418be"
    app_secret = "6bb1e622f572f1d8008a5a03ad421030"
    if not app_id or not app_secret:
        raise EnvironmentError("请先通过环境变量 WECHAT_APP_ID / WECHAT_APP_SECRET 配置公众号凭证。")
    return app_id, app_secret


if __name__ == "__main__":
    APP_ID, APP_SECRET = _load_app_config()
    helper = WeChatDraftHelper(APP_ID, APP_SECRET)
    posts_directory = Path(__file__).resolve().parent / "posts"
    publish_posts_to_wechat(helper, posts_directory)
    