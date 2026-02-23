from fastapi import APIRouter, Depends, HTTPException, status as fast_status, Query
from core.auth import get_current_user
from core.db import DB
from core.models.base import DATA_STATUS
from core.models.article import Article,ArticleBase
from sqlalchemy import and_, or_, desc
from .base import success_response, error_response
from core.config import cfg
from apis.base import format_search_kw
from core.print import print_warning, print_info, print_error, print_success
from core.cache import clear_cache_pattern
from tools.fix import fix_article
router = APIRouter(prefix=f"/articles", tags=["文章管理"])


def _owner(current_user: dict) -> str:
    return current_user.get("username")


def _try_fetch_article_content(article: Article, session) -> tuple[bool, str]:
    """
    在正文为空时尝试抓取全文。
    返回: (是否成功, 错误信息)
    """
    if (article.content or "").strip():
        return True, "正文已存在，无需重新抓取"

    url = (article.url or "").strip()
    if not url:
        return False, "文章缺少原文链接，无法抓取全文"

    try:
        mode = str(cfg.get("gather.content_mode", "web")).lower()
        content = ""
        if mode == "web":
            from driver.wxarticle import Web
            info = Web.get_article_content(url)
            content = (info or {}).get("content", "") or ""
        else:
            from core.wx.base import WxGather
            content = WxGather().Model().content_extract(url) or ""

        content = content.strip()
        if not content:
            return False, "未抓取到正文内容，请检查公众号授权状态后重试"

        if content == "DELETED":
            article.status = DATA_STATUS.DELETED
            session.commit()
            return False, "该文章已删除或不可访问"

        article.content = content
        session.commit()
        return True, ""
    except Exception as e:
        return False, f"抓取正文失败: {e}"


def _build_article_detail(article: Article) -> dict:
    data = fix_article(article)
    has_content = bool((article.content or "").strip())
    data["has_content"] = has_content
    data["content_tip"] = "" if has_content else "正文暂未抓取，可点击“抓取全文”或直接查看原文"
    return data


    
@router.delete("/clean", summary="清理无效文章(MP_ID不存在于Feeds表中的文章)")
async def clean_orphan_articles(
    current_user: dict = Depends(get_current_user)
):
    session = DB.get_session()
    try:
        from core.models.feed import Feed
        from core.models.article import Article
        
        # 找出Articles表中mp_id不在Feeds表中的记录
        owner_id = _owner(current_user)
        subquery = session.query(Feed.id).filter(Feed.owner_id == owner_id).subquery()
        deleted_count = session.query(Article)\
            .filter(Article.owner_id == owner_id)\
            .filter(~Article.mp_id.in_(subquery))\
            .delete(synchronize_session=False)
        
        session.commit()
        
        # 清除相关缓存
        clear_cache_pattern("articles_list")
        clear_cache_pattern("home_page")
        clear_cache_pattern("tag_detail")
        
        return success_response({
            "message": "清理无效文章成功",
            "deleted_count": deleted_count
        })
    except Exception as e:
        session.rollback()
        print(f"清理无效文章错误: {str(e)}")
        raise HTTPException(
            status_code=fast_status.HTTP_201_CREATED,
            detail=error_response(
                code=50001,
                message="清理无效文章失败"
            )
        )

@router.put("/{article_id}/read", summary="改变文章阅读状态")
async def toggle_article_read_status(
    article_id: str,
    is_read: bool = Query(..., description="阅读状态: true为已读, false为未读"),
    current_user: dict = Depends(get_current_user)
):
    session = DB.get_session()
    try:
        from core.models.article import Article
        
        # 检查文章是否存在
        article = session.query(Article).filter(
            Article.id == article_id,
            Article.owner_id == _owner(current_user)
        ).first()
        if not article:
            raise HTTPException(
                status_code=fast_status.HTTP_404_NOT_FOUND,
                detail=error_response(
                    code=40401,
                    message="文章不存在"
                )
            )
        
        # 更新阅读状态
        article.is_read = 1 if is_read else 0
        session.commit()
        
        # 清除相关缓存
        clear_cache_pattern("articles_list")
        clear_cache_pattern("article_detail")
        clear_cache_pattern("tag_detail")
        
        return success_response({
            "message": f"文章已标记为{'已读' if is_read else '未读'}",
            "is_read": is_read
        })
    except HTTPException as e:
        raise e
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=fast_status.HTTP_406_NOT_ACCEPTABLE,
            detail=error_response(
                code=50001,
                message=f"更新文章阅读状态失败: {str(e)}"
            )
        )
    
@router.delete("/clean_duplicate_articles", summary="清理重复文章")
async def clean_duplicate(
    current_user: dict = Depends(get_current_user)
):
    session = DB.get_session()
    try:
        owner_id = _owner(current_user)
        # 仅清理当前用户名下重复URL，保留最新一条
        query = session.query(Article).filter(
            Article.owner_id == owner_id,
            Article.status != DATA_STATUS.DELETED
        ).order_by(Article.url.asc(), Article.publish_time.desc())
        seen_urls = set()
        deleted_count = 0
        for item in query:
            url = item.url or f"__EMPTY__{item.id}"
            if url in seen_urls:
                item.status = DATA_STATUS.DELETED
                deleted_count += 1
            else:
                seen_urls.add(url)
        session.commit()
        msg = "清理重复文章成功"
        return success_response({
            "message": msg,
            "deleted_count": deleted_count
        })
    except Exception as e:
        session.rollback()
        print(f"清理重复文章: {str(e)}")
        raise HTTPException(
            status_code=fast_status.HTTP_201_CREATED,
            detail=error_response(
                code=50001,
                message="清理重复文章"
            )
        )


@router.api_route("", summary="获取文章列表",methods= ["GET", "POST"], operation_id="get_articles_list")
async def get_articles(
    offset: int = Query(0, ge=0),
    limit: int = Query(5, ge=1, le=100),
    status: str = Query(None),
    search: str = Query(None),
    mp_id: str = Query(None),
    has_content:bool=Query(False),
    current_user: dict = Depends(get_current_user)
):
    session = DB.get_session()
    try:
      
        
        # 构建查询条件
        owner_id = _owner(current_user)
        query = session.query(ArticleBase).filter(ArticleBase.owner_id == owner_id)
        if has_content:
            query = session.query(Article).filter(Article.owner_id == owner_id)
        if status:
            query = query.filter(Article.status == status)
        else:
            query = query.filter(Article.status != DATA_STATUS.DELETED)
        if mp_id:
            query = query.filter(Article.mp_id == mp_id)
        if search:
            query = query.filter(
               format_search_kw(search)
            )
        
        # 获取总数
        total = query.count()
        query= query.order_by(Article.publish_time.desc()).offset(offset).limit(limit)
        # query= query.order_by(Article.id.desc()).offset(offset).limit(limit)
        # 分页查询（按发布时间降序）
        articles = query.all()
        
        # 打印生成的 SQL 语句（包含分页参数）
        print_warning(query.statement.compile(compile_kwargs={"literal_binds": True}))
                       
        # 查询公众号名称
        from core.models.feed import Feed
        mp_names = {}
        for article in articles:
            if article.mp_id and article.mp_id not in mp_names:
                feed = session.query(Feed).filter(
                    Feed.id == article.mp_id,
                    Feed.owner_id == owner_id
                ).first()
                mp_names[article.mp_id] = feed.mp_name if feed else "未知公众号"
        
        # 合并公众号名称到文章列表
        article_list = []
        for article in articles:
            article_dict = article.__dict__
            article_dict["mp_name"] = mp_names.get(article.mp_id, "未知公众号")
            article_list.append(article_dict)
        
        from .base import success_response
        return success_response({
            "list": article_list,
            "total": total
        })
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=fast_status.HTTP_406_NOT_ACCEPTABLE,
            detail=error_response(
                code=50001,
                message=f"获取文章列表失败: {str(e)}"
            )
        )

@router.get("/{article_id}", summary="获取文章详情")
async def get_article_detail(
    article_id: str,
    content: bool = False,
    auto_fetch: bool = Query(False, description="正文为空时自动尝试抓取全文"),
    current_user: dict = Depends(get_current_user)
):
    session = DB.get_session()
    try:
        article = session.query(Article).filter(
            Article.id == article_id,
            Article.owner_id == _owner(current_user),
            Article.status != DATA_STATUS.DELETED
        ).first()
        if not article:
            from .base import error_response
            raise HTTPException(
                status_code=fast_status.HTTP_404_NOT_FOUND,
                detail=error_response(
                    code=40401,
                    message="文章不存在"
                )
            )
        if auto_fetch and not (article.content or "").strip():
            _try_fetch_article_content(article, session)
            session.refresh(article)

        return success_response(_build_article_detail(article))
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=fast_status.HTTP_406_NOT_ACCEPTABLE,
            detail=error_response(
                code=50001,
                message=f"获取文章详情失败: {str(e)}"
            )
        )   

@router.delete("/{article_id}", summary="删除文章")
async def delete_article(
    article_id: str,
    current_user: dict = Depends(get_current_user)
):
    session = DB.get_session()
    try:
        from core.models.article import Article
        
        # 检查文章是否存在
        article = session.query(Article).filter(
            Article.id == article_id,
            Article.owner_id == _owner(current_user)
        ).first()
        if not article:
            raise HTTPException(
                status_code=fast_status.HTTP_406_NOT_ACCEPTABLE,
                detail=error_response(
                    code=40401,
                    message="文章不存在"
                )
            )
        # 逻辑删除文章（更新状态为deleted）
        article.status = DATA_STATUS.DELETED
        if cfg.get("article.true_delete", False):
            session.delete(article)
        session.commit()
        
        return success_response(None, message="文章已标记为删除")
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=fast_status.HTTP_406_NOT_ACCEPTABLE,
            detail=error_response(
                code=50001,
                message=f"删除文章失败: {str(e)}"
            )
        )


@router.post("/{article_id}/fetch_content", summary="抓取文章全文")
async def fetch_article_content(
    article_id: str,
    current_user: dict = Depends(get_current_user)
):
    session = DB.get_session()
    try:
        article = session.query(Article).filter(
            Article.id == article_id,
            Article.owner_id == _owner(current_user),
            Article.status != DATA_STATUS.DELETED
        ).first()
        if not article:
            raise HTTPException(
                status_code=fast_status.HTTP_404_NOT_FOUND,
                detail=error_response(
                    code=40401,
                    message="文章不存在"
                )
            )

        ok, reason = _try_fetch_article_content(article, session)
        session.refresh(article)
        data = _build_article_detail(article)
        data["fetch_ok"] = ok
        data["fetch_message"] = "抓取全文成功" if ok else reason
        return success_response(data, message=data["fetch_message"])
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=fast_status.HTTP_406_NOT_ACCEPTABLE,
            detail=error_response(
                code=50001,
                message=f"抓取文章全文失败: {str(e)}"
            )
        )

@router.get("/{article_id}/next", summary="获取下一篇文章")
async def get_next_article(
    article_id: str,
    current_user: dict = Depends(get_current_user)
):
    session = DB.get_session()
    try:
        # 获取当前文章的发布时间
        owner_id = _owner(current_user)
        current_article = session.query(Article).filter(
            Article.id == article_id,
            Article.owner_id == owner_id
        ).first()
        if not current_article:
            raise HTTPException(
                status_code=fast_status.HTTP_404_NOT_FOUND,
                detail=error_response(
                    code=40401,
                    message="当前文章不存在"
                )
            )
        
        # 查询发布时间更晚的第一篇文章
        next_article = session.query(Article)\
            .filter(Article.publish_time > current_article.publish_time)\
            .filter(Article.status != DATA_STATUS.DELETED)\
            .filter(Article.owner_id == owner_id)\
            .filter(Article.mp_id == current_article.mp_id)\
            .order_by(Article.publish_time.asc())\
            .first()
        
        if not next_article:
            raise HTTPException(
                status_code=fast_status.HTTP_406_NOT_ACCEPTABLE,
                detail=error_response(
                    code=40402,
                    message="没有下一篇文章"
                )
            )
        return success_response(fix_article(next_article))
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=fast_status.HTTP_406_NOT_ACCEPTABLE,
            detail=error_response(
                code=50001,
                message=f"获取下一篇文章失败: {str(e)}"
            )
        )

@router.get("/{article_id}/prev", summary="获取上一篇文章")
async def get_prev_article(
    article_id: str,
    current_user: dict = Depends(get_current_user)
):
    session = DB.get_session()
    try:
        # 获取当前文章的发布时间
        owner_id = _owner(current_user)
        current_article = session.query(Article).filter(
            Article.id == article_id,
            Article.owner_id == owner_id
        ).first()
        if not current_article:
            raise HTTPException(
                status_code=fast_status.HTTP_404_NOT_FOUND,
                detail=error_response(
                    code=40401,
                    message="当前文章不存在"
                )
            )
        
        # 查询发布时间更早的第一篇文章
        prev_article = session.query(Article)\
            .filter(Article.publish_time < current_article.publish_time)\
            .filter(Article.status != DATA_STATUS.DELETED)\
            .filter(Article.owner_id == owner_id)\
            .filter(Article.mp_id == current_article.mp_id)\
            .order_by(Article.publish_time.desc())\
            .first()
        
        if not prev_article:
            raise HTTPException(
                status_code=fast_status.HTTP_406_NOT_ACCEPTABLE,
                detail=error_response(
                    code=40403,
                    message="没有上一篇文章"
                )
            )
        return success_response(fix_article(prev_article))
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=fast_status.HTTP_406_NOT_ACCEPTABLE,
            detail=error_response(
                code=50001,
                message=f"获取上一篇文章失败: {str(e)}"
            )
        )
