from fastapi import APIRouter, Request, Depends, Query, HTTPException
from fastapi.responses import HTMLResponse
from typing import Optional
import os
from datetime import datetime
import re
import json
from views.base import process_content_images, _render_template_with_error
from core.db import DB
from core.models.article import Article
from core.models.feed import Feed
from core.models.tags import Tags
from apis.base import format_search_kw
from core.lax.template_parser import TemplateParser
from views.config import base
from driver.wxarticle import Web
from core.config import cfg
# 创建路由器
router = APIRouter(tags=["文章详情"])


def _fetch_article_content(url: str) -> tuple[str, str]:
    link = (url or "").strip()
    if not link:
        return "", "文章缺少原文链接，无法抓取正文"
    try:
        mode = str(cfg.get("gather.content_mode", "web")).lower()
        content = ""
        if mode == "web":
            info = Web.get_article_content(link)
            content = (info or {}).get("content", "") or ""
        else:
            from core.wx.base import WxGather
            content = WxGather().Model().content_extract(link) or ""
        text = (content or "").strip()
        if not text:
            return "", "正文尚未采集成功，请先检查扫码授权状态后重试"
        if text == "DELETED":
            return "", "原文已删除或不可访问"
        return text, ""
    except Exception as e:
        return "", f"抓取正文失败: {e}"


@router.get("/article/{article_id}", response_class=HTMLResponse, summary="文章详情页")
async def article_detail_view(
    request: Request,
    article_id: str,
    auto_fetch: bool = Query(True, description="正文为空时自动尝试抓取"),
    retry_fetch: bool = Query(False, description="手动触发正文重试抓取")
):
    """
    文章详情页面
    """
    session = DB.get_session()
    try:
        # 查询文章信息
        article_query = session.query(Article, Feed).join(
            Feed, Article.mp_id == Feed.id
        ).filter(Article.id == article_id, Article.status == 1, Feed.status == 1).first()
        
        if not article_query:
            raise HTTPException(status_code=404, detail="文章不存在")
        
        if len(article_query) != 2:
            raise HTTPException(status_code=500, detail="数据查询错误")
        article, feed = article_query
        
        # 标记为已读（可选）
        if not article.is_read:
            article.is_read = 1
            session.commit()

        fetch_attempted = False
        fetch_error = ""
        if not (article.content or "").strip() and (auto_fetch or retry_fetch):
            fetch_attempted = True
            content, fetch_error = _fetch_article_content(article.url or "")
            if content:
                article.content = content
                session.commit()
                session.refresh(article)
                fetch_error = ""
        
        # 获取相关文章（同公众号的其他文章）
        related_articles = session.query(Article).filter(
            Article.mp_id == article.mp_id,
            Article.id != article_id,
            Article.status == 1
        ).order_by(Article.publish_time.desc()).limit(5).all()
        
        # 获取上一个和下一个文章ID
        prev_article = session.query(Article.id,Article.title).filter(
            Article.mp_id == article.mp_id,
            Article.publish_time < article.publish_time,
            Article.status == 1
        ).order_by(Article.publish_time.desc()).first()
        
        next_article = session.query(Article.id,Article.title).filter(
            Article.mp_id == article.mp_id,
            Article.publish_time > article.publish_time,
            Article.status == 1
        ).order_by(Article.publish_time.asc()).first()
        
        related_list = []
        for rel_article in related_articles:
            rel_data = {
                "id": rel_article.id,
                "title": rel_article.title,
                "description": rel_article.description or Web.get_description(rel_article.content),
                "pic_url": Web.get_image_url(rel_article.pic_url),
                "publish_time": datetime.fromtimestamp(rel_article.publish_time).strftime('%Y-%m-%d %H:%M') if rel_article.publish_time else ""
            }
            related_list.append(rel_data)
        
        has_content = bool((article.content or "").strip())
        content_tip = "正文尚未采集，可能是未抓取成功或原文不可访问。可先查看原文链接。"
        if not has_content and retry_fetch:
            if fetch_error:
                content_tip = f"本次重试抓取失败：{fetch_error}"
            elif fetch_attempted:
                content_tip = "已触发重试抓取，但正文仍为空，请稍后再次重试。"
        elif not has_content and fetch_attempted:
            content_tip = "正文尚未采集，可能是未抓取成功或原文不可访问。可点击“重新抓取正文”再次尝试。"

        # 处理文章数据
        article_data = {
            "id": article.id,
            "title": article.title,
            "description": article.description or Web.get_description(article.content),
            "pic_url": Web.get_image_url(article.pic_url),
            "url": article.url,
            "publish_time": datetime.fromtimestamp(article.publish_time).strftime('%Y-%m-%d %H:%M') if article.publish_time else "",
            "created_at": article.created_at.strftime('%Y-%m-%d %H:%M') if article.created_at else "",
            "content": process_content_images(article.content or ""),
            "mp_name": feed.mp_name if feed else "未知公众号",
            "mp_id": article.mp_id,
            "mp_cover": Web.get_image_url(feed.mp_cover) if feed else "",
            "mp_intro": feed.mp_intro if feed else "",
            "has_content": has_content,
            "content_tip": content_tip,
            "retry_url": f"/views/article/{article.id}?auto_fetch=1&retry_fetch=1",
            "retry_fetch": retry_fetch
        }
        
        # 构建面包屑
        breadcrumb = [
            {"name": feed.mp_name, "url": f"/views/articles?mp_id={article_data['mp_id']}"},
            {"name": article_data["title"][:50] + "..." if len(article_data["title"]) > 50 else article_data["title"], "url": None}
        ]
        
        # 读取模板文件
        template_path=base.article_detail_template
        with open(template_path, 'r', encoding='utf-8') as f:
            template_content = f.read()
        
        parser = TemplateParser(template_content, template_dir=base.public_dir)
        html_content = parser.render({
            "site": base.site,
            "article": article_data,
            "related_articles": related_list,
            "prev_article": {"id": prev_article[0], "title": prev_article[1]} if prev_article else "",
            "next_article": {"id": next_article[0], "title": next_article[1]} if next_article else "",
            "breadcrumb": breadcrumb,
        })
        
        return HTMLResponse(content=html_content)
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"获取文章详情错误: {str(e)}")
        return _render_template_with_error(
            base.article_detail_template,
            f"加载文章时出现错误: {str(e)}",
            [{"name": "首页", "url": "/views/home"}, {"name": "文章列表", "url": "/views/articles"}]
        )
    finally:
        session.close()
