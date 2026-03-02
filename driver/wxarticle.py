import random
from socket import timeout
from .playwright_driver import PlaywrightController
from typing import Dict
from core.print import print_error,print_info,print_success,print_warning
import time
from core.wait import Wait
import base64
import re
from bs4 import BeautifulSoup
import os
from datetime import datetime
from core.config import cfg
from core.proxy_pool import proxy_pool

# 启动代理池
proxy_pool.start()

class WXArticleFetcher:
    """微信公众号文章获取器
    
    基于WX_API登录状态获取文章内容
    
    Attributes:
        wait_timeout: 显式等待超时时间(秒)
    """
    
    def __init__(self, wait_timeout: int = 10000):
        """初始化文章获取器"""
        self.wait_timeout = wait_timeout
        self.controller = PlaywrightController()
        if not self.controller:
            raise Exception("WebDriver未初始化或未登录")
    
    def convert_publish_time_to_timestamp(self, publish_time_str: str) -> int:
        """将发布时间字符串转换为时间戳
        
        Args:
            publish_time_str: 发布时间字符串，如 "2024-01-01" 或 "2024-01-01 12:30"
            
        Returns:
            时间戳（秒）
        """
        try:
            # 尝试解析不同的时间格式
            formats = [
                "%Y-%m-%d %H:%M:%S",  # 2024-01-01 12:30:45
                "%Y年%m月%d日 %H:%M",        # 2024年03月24日 17:14
                "%Y-%m-%d %H:%M",     # 2024-01-01 12:30
                "%Y-%m-%d",           # 2024-01-01
                "%Y年%m月%d日",        # 2024年01月01日
                "%m月%d日",            # 01月01日 (当年)
            ]
            
            for fmt in formats:
                try:
                    if fmt == "%m月%d日":
                        # 对于只有月日的格式，智能判断年份
                        current_date = datetime.now()
                        current_year = current_date.year
                        full_time_str = f"{current_year}年{publish_time_str}"
                        dt = datetime.strptime(full_time_str, "%Y年%m月%d日")
                        
                        # 如果解析出的日期在未来，使用上一年
                        if dt > current_date:
                            dt = dt.replace(year=current_year - 1)
                    else:
                        dt = datetime.strptime(publish_time_str, fmt)
                    return int(dt.timestamp())
                except ValueError:
                    continue
            
            # 如果所有格式都失败，返回当前时间戳
            print_warning(f"无法解析时间格式: {publish_time_str}，使用当前时间")
            return int(datetime.now().timestamp())
            
        except Exception as e:
            print_error(f"时间转换失败: {e}")
            return int(datetime.now().timestamp())
       
        
    def extract_biz_from_source(self, url: str, page=None) -> str:
        """从URL或页面源码中提取biz参数
        
        Args:
            url: 文章URL
            page: Playwright Page实例，可选
            
        Returns:
            biz参数值
        """
        # 尝试从URL中提取
        match = re.search(r'[?&]__biz=([^&]+)', url)
        if match:
            return match.group(1)
            
        # 从页面源码中提取（需要page参数）
        if page is None:
            if not hasattr(self, 'page') or self.page is None:
                return ""
            page = self.page
            
        try:
            # 从页面源码中查找biz信息
            page_source = page.content()
            print_info(f'开始解析Biz')
            biz_match = re.search(r'var biz = "([^"]+)"', page_source)
            if biz_match:
                return biz_match.group(1)
                
            # 尝试其他可能的biz存储位置
            biz_match = re.search(r'window\.__biz=([^&]+)', page_source)
            if biz_match:
                return biz_match.group(1)
            # biz_match=page.evaluate('() =>window.biz')
            return ""
            
        except Exception as e:
            print_error(f"从页面源码中提取biz参数失败: {e}")
            return ""
    def extract_id_from_url(self, url: str) -> str:
        """从微信文章URL中提取ID
        
        Args:
            url: 文章URL
            
        Returns:
            文章ID字符串，如果提取失败返回None
        """
        try:
            # 从URL中提取ID部分
            match = re.search(r'/s/([A-Za-z0-9_-]+)', url)
            if not match:
                return ""
                
            id_str = match.group(1)
            
            # 添加必要的填充
            padding = 4 - len(id_str) % 4
            if padding != 4:
                id_str += '=' * padding
                
            # 尝试解码base64
            try:
                id_number = base64.b64decode(id_str).decode("utf-8")
                return id_number
            except Exception as e:
                # 如果base64解码失败，返回原始ID字符串
                return id_str
                
        except Exception as e:
            print_error(f"提取文章ID失败: {e}")
            return ""  
    def FixArticle(self, urls: list = [], mp_id: str = "") -> bool:
        """批量修复文章内容
        
        Args:
            urls: 文章URL列表，默认为示例URL
            mp_id: 公众号ID，可选
            
        Returns:
            操作是否成功
        """
        try:
            from jobs.article import UpdateArticle
            
            # 设置默认URL列表
            if urls is []:
                urls = ["https://mp.weixin.qq.com/s/YTHUfxzWCjSRnfElEkL2Xg"]
                
            success_count = 0
            total_count = len(urls)
            
            for i, url in enumerate(urls, 1):
                if url=="":
                    continue
                print_info(f"正在处理第 {i}/{total_count} 篇文章: {url}")
                
                try:
                    article_data = self.get_article_content(url)
                    
                    # 构建文章数据
                    article = {
                        "id": article_data.get('id'), 
                        "title": article_data.get('title'),
                        "mp_id": article_data.get('mp_id') if mp_id is None else mp_id, 
                        "publish_time": article_data.get('publish_time'),
                        "pic_url": article_data.get('pic_url'),
                        "content": article_data.get('content'),
                        "url": url,
                    }
                    
                    # 删除content字段避免重复存储
                    content_backup = article_data.get('content', '')
                    del article_data['content']
                    
                    print_success(f"获取成功: {article_data}")
                    
                    # 更新文章
                    ok = UpdateArticle(article, check_exist=True)
                    if ok:
                        success_count += 1
                        print_info(f"已更新文章: {article_data.get('title', '未知标题')}")
                    else:
                        print_warning(f"更新失败: {article_data.get('title', '未知标题')}")
                        
                    # 恢复content字段
                    article_data['content'] = content_backup
                    
                    # 避免请求过快，但只在非最后一个请求时等待
                    Wait(1,2,tips=f"处理第 {i}/{total_count} 篇文章")
                        
                except Exception as e:
                    print_error(f"处理文章失败 {url}: {e}")
                    continue
                    
            print_success(f"批量处理完成: 成功 {success_count}/{total_count}")
            return success_count > 0
            
        except Exception as e:
            print_error(f"批量修复文章失败: {e}")
            return False
        finally:
            self.Close() 
    async def async_get_article_content(self,url:str)->Dict:
        import asyncio
        return await asyncio.to_thread(self.get_article_content, url)
    def get_article_content(self, url: str) -> Dict:
        """获取单篇文章详细内容
        
        Args:
            url: 文章URL (如: https://mp.weixin.qq.com/s/qfe2F6Dcw-uPXW_XW7UAIg)
            
        Returns:
            文章内容数据字典，包含:
            - title: 文章标题
            - author: 作者
            - publish_time: 发布时间
            - content: 正文HTML
            - images: 图片URL列表
            
        Raises:
            Exception: 如果未登录或获取内容失败
        """
        info={
                "id": self.extract_id_from_url(url),
                "title": "",
                "publish_time": "",
                "content": "",
                "images": "",
                "mp_info":{
                "mp_name":"",   
                "logo":"",
                "biz": "",
                }
            }
        
        # 尝试次数
        max_retries = 3
        current_proxy = None
        
        for attempt in range(max_retries):
            try:
                print_info(f"正在尝试获取文章内容 (尝试 {attempt + 1}/{max_retries}): {url}")
                if current_proxy:
                    print_info(f"使用代理: {current_proxy}")
                
                self.controller.start_browser(proxy=current_proxy)
                self.page = self.controller.page
                print_warning(f"Get:{url} Wait:{self.wait_timeout}")
                
                # 记录页面打开前的时间
                start_time = time.time()
                self.controller.open_url(url)
                print_info(f"页面加载耗时: {time.time() - start_time:.2f}s")
                
                page = self.page
                
                # 等待页面加载
                body_element = page.locator("body")
                body = body_element.text_content().strip()
                
                info["content"] = body
                if "当前环境异常，完成验证后即可继续访问" in body:
                    info["content"] = ""
                    print_warning(f"检测到环境异常 (尝试 {attempt + 1})")
                    
                    if attempt < max_retries - 1:
                        # 换个代理试试
                        new_proxy = proxy_pool.get_proxy()
                        if new_proxy:
                            current_proxy = f"http://{new_proxy}"
                            print_info(f"已从代理池获取新代理: {current_proxy}")
                        else:
                            print_warning("代理池目前没有可用代理，尝试直接等待...")
                        
                        Wait(min=5, max=10, tips="环境异常，切换代理或等待后重试")
                        self.Close()
                        continue
                    else:
                        raise Exception("当前环境异常，已达到最大重试次数")
                
                if "该内容已被发布者删除" in body or "The content has been deleted by the author." in body:
                    info["content"] = "DELETED"
                    raise Exception("该内容已被发布者删除")
                    
                if "内容审核中" in body:
                    info['content'] = "DELETED"
                    raise Exception("内容审核中")
                    
                if "该内容暂时无法查看" in body:
                    info["content"] = "DELETED"
                    raise Exception("该内容暂时无法查看")
                    
                if "违规无法查看" in body:
                    info["content"] = "DELETED"
                    raise Exception("违规无法查看")
                    
                if "发送失败无法查看" in body:
                    info["content"] = "DELETED"
                    raise Exception("发送失败无法查看")
                    
                if "Unable to view this content because it violates regulation" in body:     
                    info["content"] = "DELETED"
                    raise Exception("违规无法查看")

                # 获取标题
                title = page.locator('meta[property="og:title"]').get_attribute("content") or ""
                # 获取作者
                author = page.locator('meta[property="og:article:author"]').get_attribute("content") or ""
                # 获取描述
                description = page.locator('meta[property="og:description"]').get_attribute("content") or ""
                # 获取题图
                topic_image = page.locator('meta[property="twitter:image"]').get_attribute("content") or ""

                if title:
                    self.export_to_pdf(f"./data/{title}.pdf")
                else:
                    title = page.evaluate('() => document.title')
                
                # 获取正文内容和图片
                content_element = page.locator("#js_content")
                content = ""
                try:
                    content = content_element.inner_html()
                except:
                    content_element = page.locator("#js_article")
                    try:
                        content = content_element.inner_html()
                    except:
                        pass

                content = self.clean_article_content(str(content))
                
                # 获取图像资源
                images = []
                try:
                    images = [
                        img.get_attribute("data-src") or img.get_attribute("src")
                        for img in content_element.locator("img").all()
                        if img.get_attribute("data-src") or img.get_attribute("src")
                    ]
                except:
                    pass
                    
                if images and len(images) > 0:
                    info["pic_url"] = images[0]

                publish_time = ""
                try:
                    # 获取发布时间
                    publish_time_element = page.locator("#publish_time")
                    publish_time_str = publish_time_element.text_content().strip()
                    # 将发布时间转换为时间戳
                    publish_time = self.convert_publish_time_to_timestamp(publish_time_str)
                except Exception as e:
                    print_warning(f"获取作者和发布时间失败: {e}")
                
                info.update({
                    "title": title,
                    "publish_time": publish_time,
                    "content": content,
                    "images": images,
                    "author": author,
                    "description": description,
                    "topic_image": topic_image
                })

                if info["content"] != "DELETED":
                    try:
                        # 获取公众号信息
                        ele_logo = page.locator('#js_like_profile_bar .wx_follow_avatar img')
                        logo_src = ele_logo.get_attribute('src')

                        # 获取公众号名称
                        mp_name = page.evaluate('() => $("#js_wx_follow_nickname").text()')
                        biz = page.evaluate('() => window.biz')
                        
                        info["mp_info"] = {
                            "mp_name": mp_name,
                            "logo": logo_src,
                            "biz": biz or self.extract_biz_from_source(url, page), 
                        }
                        if info["mp_info"]["biz"]:
                            info["mp_id"] = "MP_WXS_" + base64.b64decode(info["mp_info"]["biz"]).decode("utf-8")
                    except Exception as e:
                        print_error(f"获取公众号信息失败: {str(e)}")
                
                # 如果成功获取内容，跳出重试循环
                break

            except Exception as e:
                print_error(f"文章内容获取失败 (尝试 {attempt + 1}/{max_retries}): {str(e)}")
                if 'body' in locals():
                    print_warning(f"页面内容预览: {body[:100]}...")
                
                if attempt < max_retries - 1:
                    # 只有在由于非删除原因导致的失败时才重试
                    if "已被发布者删除" not in str(e) and "内容审核中" not in str(e):
                        # 换个代理试试
                        new_proxy = proxy_pool.get_proxy()
                        if new_proxy:
                            current_proxy = f"http://{new_proxy}"
                            print_info(f"已从代理池获取新代理进行下一次尝试: {current_proxy}")
                        
                        Wait(min=3, max=7, tips="获取失败，准备重试")
                        self.Close()
                        continue
                
                # 如果是最后一次尝试或不可重试错误，重新抛出异常
                self.Close()
                # raise # 不一定要 raise，原代码是返回 info
            finally:
                self.Close()
            
        return info
    def Close(self):
        """关闭浏览器"""
        if hasattr(self, 'controller'):
            self.controller.Close()
        else:
            print("WXArticleFetcher未初始化或已销毁")
    def __del__(self):
        """销毁文章获取器"""
        try:
            if hasattr(self, 'controller') and self.controller is not None:
                self.controller.Close()
        except Exception as e:
            # 析构函数中避免抛出异常
            pass

    def export_to_pdf(self, title=None):
        """将文章内容导出为 PDF 文件
        
        Args:
            output_path: 输出 PDF 文件的路径（可选）
        """
        output_path=""
        try:
            if cfg.get("export.pdf.enable",False)==False:
                return
            # 使用浏览器打印功能生成 PDF
            if output_path:
                import os
                pdf_path=cfg.get("export.pdf.dir","./data/pdf")
                output_path=os.path.abspath(f"{pdf_path}/{title}.pdf")
            print_success(f"PDF 文件已生成{output_path}")
        except Exception as e:
            print_error(f"生成 PDF 失败: {str(e)}")
    
    def fix_images(self,content:str)->str:
        try:
            soup = BeautifulSoup(content, 'html.parser')
            # 找到内容
            js_content_div = soup
            # 移除style属性中的visibility: hidden;
            if js_content_div is None:
                return ""
            js_content_div.attrs.pop('style', None)
            # 找到所有的img标签
            img_tags = js_content_div.find_all('img')
            # 遍历每个img标签并修改属性，设置宽度为1080p
            for img_tag in img_tags:
                if 'data-src' in img_tag.attrs:
                    img_tag['src'] = img_tag['data-src']
                    del img_tag['data-src']
                if 'style' in img_tag.attrs:
                    style = img_tag['style']
                    # 使用正则表达式替换width属性
                    style = re.sub(r'width\s*:\s*\d+\s*px', 'width: 1080px', style)
                    img_tag['style'] = style
            return  js_content_div.prettify()
        except Exception as e:
            print_error(f"修复图片失败: {str(e)}")
        return content
    def get_image_url(self,url:str)->str:
        base_url=cfg.get("server.base_url","")
        return f"{base_url}/static/res/logo/{url}" 
    def get_description(self,content:str,length:int=200)->str:
        soup = BeautifulSoup(content, 'html.parser')
            # 找到内容
        js_content_div = soup
        if js_content_div is None:
            return ""
        content = js_content_div.get_text().strip().strip("\n").replace("\n"," ").replace("\r"," ")
        return content[:length]+"..." if len(content)>length else content

    def proxy_images(self,content:str)->str:
        try:
            soup = BeautifulSoup(content, 'html.parser')
            # 找到内容
            js_content_div = soup
            # 移除style属性中的visibility: hidden;
            if js_content_div is None:
                return ""
            js_content_div.attrs.pop('style', None)
            # 找到所有的img标签
            img_tags = js_content_div.find_all('img')
            # 遍历每个img标签并修改属性，设置宽度为1080p
            for img_tag in img_tags:
                if 'src' in img_tag.attrs:
                    img_tag['src'] = self.get_image_url(img_tag['src'])
                if 'style' in img_tag.attrs:
                    style = img_tag['style']
                    # 使用正则表达式替换width属性
                    style = re.sub(r'width\s*:\s*\d+\s*px', 'width: 100%', style)
                    img_tag['style'] = style
            return  js_content_div.prettify()
        except Exception as e:
            print_error(f"Proxy图片失败: {str(e)}")
        return content
   
    def clean_article_content(self,html_content: str):
        from tools.html import htmltools
        html_content=self.fix_images(html_content)
        if not cfg.get("gather.clean_html",False):
            return html_content
        return htmltools.clean_html(str(html_content).strip(),
                                 remove_selectors=[
                                     "link",
                                     "head",
                                     "script"
                                 ],
                                 remove_attributes=[
                                     {"name":"style","value":"display: none;"},
                                     {"name":"style","value":"display:none;"},
                                     {"name":"aria-hidden","value":"true"},
                                 ],
                                 remove_normal_tag=True
                                 )
   


Web=WXArticleFetcher()
