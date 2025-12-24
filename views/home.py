from fastapi import APIRouter, Request, Depends, Query, HTTPException
from fastapi.responses import HTMLResponse
from typing import Optional
import os
import json
from datetime import datetime

from core.db import DB
from core.models.tags import Tags
from core.models.feed import Feed
from core.models.article import Article
from core.lax.template_parser import TemplateParser
from views.config import base
from driver.wxarticle import Web
from core.cache import cache_view, clear_cache_pattern
# 创建路由器
router = APIRouter(tags=["首页"])

@router.get("/home", response_class=HTMLResponse, summary="首页 - 显示所有标签")
@cache_view("home_page", ttl=1800)  # 缓存30分钟
async def home_view(
    request: Request,
    page: int = Query(1, ge=1, description="页码"),
    limit: int = Query(12, ge=1, le=50, description="每页数量")
):
    """
    首页显示所有标签，支持分页
    """
    session = DB.get_session()
    try:
        # 查询标签总数
        total = session.query(Tags).filter(Tags.status == 1).count()
        
        # 计算偏移量
        offset = (page - 1) * limit
        
        # 查询标签列表
        tags = session.query(Tags).filter(Tags.status == 1).order_by(Tags.created_at.desc()).offset(offset).limit(limit).all()
        
        # 处理标签数据
        tag_list = []
        for tag in tags:
            # 解析mps_id JSON
            mps_ids = []
            if tag.mps_id:
                try:
                    mps_data = json.loads(tag.mps_id)
                    mps_ids = [str(mp['id']) for mp in mps_data] if isinstance(mps_data, list) else []
                except (json.JSONDecodeError, TypeError):
                    mps_ids = []
            
            # 统计文章数量
            article_count = 0
            if mps_ids:
                article_count = session.query(Article).filter(
                    Article.mp_id.in_(mps_ids),
                    Article.status == 1
                ).count()
            
            # 获取关联的公众号数量
            mp_count = len(mps_ids) if mps_ids else 0
            
            tag_data = {
                "id": tag.id,
                "name": tag.name,
                "cover": Web.get_image_url(tag.cover) if tag.cover else "",
                "intro": tag.intro,
                "mp_count": mp_count,
                "article_count": article_count,
                "sync_time": datetime.fromtimestamp(tag.sync_time).strftime('%Y-%m-%d %H:%M') if tag.sync_time else "未同步",
                "created_at": tag.created_at.strftime('%Y-%m-%d') if tag.created_at else ""
            }
            tag_list.append(tag_data)
        
        # 计算分页信息
        total_pages = (total + limit - 1) // limit
        has_prev = page > 1
        has_next = page < total_pages
        
        # 构建面包屑
        breadcrumb = [
            {"name": "首页", "url": "/views/home"}
        ]
        
        # 读取模板文件
        template_path = base.home_template
        with open(template_path, 'r', encoding='utf-8') as f:
            template_content = f.read()
        
        # 使用模板引擎渲染
        parser = TemplateParser(template_content, template_dir=base.public_dir)
        html_content = parser.render({
            "tags": tag_list,
            "current_page": page,
            "total_pages": total_pages,
            "total_items": total,
            "limit": limit,
            "has_prev": has_prev,
            "has_next": has_next,
        })
        
        return HTMLResponse(content=html_content)
        
    except Exception as e:
        print(f"获取首页数据错误: {str(e)}")
        # 读取模板文件
        template_path = base.home_template
        with open(template_path, 'r', encoding='utf-8') as f:
            template_content = f.read()
        
        parser = TemplateParser(template_content, template_dir=base.public_dir)
        html_content = parser.render({
            "error": f"加载数据时出现错误: {str(e)}",
            "breadcrumb": [{"name": "首页", "url": "/views/home"}]
        })
        
        return HTMLResponse(content=html_content)
    finally:
        session.close()

