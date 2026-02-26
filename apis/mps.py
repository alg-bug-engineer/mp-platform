import re
from fastapi import APIRouter, Depends, HTTPException, status, Query, Body, UploadFile, File
from fastapi.responses import FileResponse
from fastapi.background import BackgroundTasks
from core.auth import get_current_user
from core.db import DB
from core.wx import search_Biz
from driver.wx import Wx
from .base import success_response, error_response
from datetime import datetime
from core.config import cfg
from core.res import save_avatar_locally
from core.wechat_auth_service import get_token_cookie
import io
import os
import uuid
from jobs.article import UpdateArticle
from driver.wxarticle import WXArticleFetcher
from core.log import get_logger
from core.events import log_event, E
logger = get_logger(__name__)
router = APIRouter(prefix=f"/mps", tags=["公众号管理"])
# import core.db as db
# UPDB=db.Db("数据抓取")
# def UpdateArticle(art:dict):
#             return UPDB.add_article(art)


def _owner(current_user: dict) -> str:
    return current_user.get("username")


def _is_auth_invalid_error(err_text: str) -> bool:
    text = str(err_text or "").strip().lower()
    if not text:
        return False
    patterns = [
        "invalid session",
        "请先扫码登录公众号平台",
        "公众号平台登录失效",
        "ret=200003",
        "ret=200013",
        "token",
    ]
    return any(p in text for p in patterns)


def _sanitize_error(err_text: str) -> str:
    text = str(err_text or "").strip()
    if not text:
        return "未知错误"
    # 去掉极长 traceback / HTML 片段，避免直接回传噪音信息。
    text = re.sub(r"\s+", " ", text)
    return text[:220]


def _resolve_gather_auth(session, owner_id: str, allow_global_fallback: bool = False):
    token, cookie = get_token_cookie(
        session,
        owner_id=owner_id,
        allow_global_fallback=allow_global_fallback,
    )
    return (
        str(token or "").strip(),
        str(cookie or "").strip(),
        str(cfg.get("user_agent", "") or "").strip(),
    )


@router.get("/search/{kw}", summary="搜索公众号")
async def search_mp(
    kw: str = "",
    limit: int = 10,
    offset: int = 0,
    current_user: dict = Depends(get_current_user)
):
    session = DB.get_session()
    try:
        owner_id = _owner(current_user)
        token, cookie = get_token_cookie(session, owner_id=owner_id, allow_global_fallback=False)
        if not token or not cookie:
            raise HTTPException(
                status_code=status.HTTP_201_CREATED,
                detail=error_response(
                    code=50001,
                    message="搜索公众号失败,请重新扫码授权！",
                )
            )

        result = search_Biz(
            kw,
            limit=limit,
            offset=offset,
            token=token,
            cookie=cookie,
            user_agent=str(cfg.get("user_agent", "")),
        )
        if result is None:
            raise RuntimeError("微信搜索接口返回空结果，可能触发平台频控，请稍后重试")
        data={
            'list':result.get('list') if result is not None else [],
            'page':{
                'limit':limit,
                'offset':offset
            },
            'total':result.get('total') if result is not None else 0
        }
        return success_response(data)
    except HTTPException:
        raise
    except Exception as e:
        err_text = _sanitize_error(str(e))
        logger.error(f"搜索公众号错误: {err_text}")
        if _is_auth_invalid_error(err_text):
            try:
                from core.wechat_auth_service import get_wechat_auth
                item = get_wechat_auth(session, owner_id=_owner(current_user))
                if item:
                    item.token = ""
                    item.cookie = ""
                    session.commit()
            except Exception:
                pass
            msg = f"搜索公众号失败,请重新扫码授权！（{err_text}）"
        else:
            msg = f"搜索公众号失败: {err_text}"
        raise HTTPException(
            status_code=status.HTTP_201_CREATED,
            detail=error_response(
                code=50001,
                message=msg,
            )
        )
    finally:
        try:
            session.close()
        except Exception:
            pass

@router.get("", summary="获取公众号列表")
async def get_mps(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    kw: str = Query(""),
    current_user: dict = Depends(get_current_user)
):
    session = DB.get_session()
    try:
        from core.models.feed import Feed
        query = session.query(Feed).filter(Feed.owner_id == _owner(current_user))
        if kw:
            query = query.filter(Feed.mp_name.ilike(f"%{kw}%"))
        total = query.count()
        mps = query.order_by(Feed.created_at.desc()).limit(limit).offset(offset).all()
        return success_response({
            "list": [{
                "id": mp.id,
                "mp_name": mp.mp_name,
                "mp_cover": mp.mp_cover,
                "mp_intro": mp.mp_intro,
                "status": mp.status,
                "created_at": mp.created_at.isoformat()
            } for mp in mps],
            "page": {
                "limit": limit,
                "offset": offset,
                "total": total
            },
            "total": total
        })
    except Exception as e:
        logger.error(f"获取公众号列表错误: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_201_CREATED,
            detail=error_response(
                code=50001,
                message="获取公众号列表失败"
            )
        )

@router.get("/update/{mp_id}", summary="更新公众号文章")
async def update_mps(
     mp_id: str,
     start_page: int = 0,
     end_page: int = 1,
    current_user: dict = Depends(get_current_user)
):
    session = DB.get_session()
    try:
        from core.models.feed import Feed
        mp = session.query(Feed).filter(
            Feed.id == mp_id,
            Feed.owner_id == _owner(current_user)
        ).first()
        if not mp:
           return error_response(
                    code=40401,
                    message="请选择一个公众号"
                )
        import time
        sync_interval=cfg.get("sync_interval",60)
        if mp.update_time is None:
            mp.update_time=int(time.time())-sync_interval
        time_span=int(time.time())-int(mp.update_time)
        if time_span<sync_interval:
           return error_response(
                    code=40402,
                    message="请不要频繁更新操作",
                    data={"time_span":time_span}
                )
        result=[]    
        token, cookie, user_agent = _resolve_gather_auth(
            session,
            owner_id=_owner(current_user),
            allow_global_fallback=False,
        )
        if not token or not cookie:
            return error_response(
                code=40101,
                message="当前账号公众号授权失效，请重新扫码授权后重试",
            )

        mp_payload = {
            "faker_id": str(mp.faker_id or ""),
            "id": str(mp.id or ""),
            "mp_name": str(mp.mp_name or ""),
        }
        if not mp_payload["faker_id"] or not mp_payload["id"]:
            return error_response(
                code=40403,
                message="公众号信息不完整，无法启动更新",
            )

        def UpArt(payload: dict):
            nonlocal result
            from core.wx import WxGather
            wx = WxGather().Model()
            try:
                wx.get_Articles(
                    payload.get("faker_id"),
                    Mps_id=payload.get("id"),
                    Mps_title=payload.get("mp_name", ""),
                    CallBack=UpdateArticle,
                    start_page=start_page,
                    MaxPage=end_page,
                    token=token,
                    cookie=cookie,
                    user_agent=user_agent,
                )
                result = wx.articles
            except Exception as e:
                logger.error(f"更新公众号文章线程异常: {e}")
        import threading
        threading.Thread(target=UpArt, args=(mp_payload,), daemon=True).start()
        return success_response({
            "time_span":time_span,
            "list":result,
            "total":len(result),
            "mps":mp
        })
    except Exception as e:
        logger.error(f"更新公众号文章: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_201_CREATED,
            detail=error_response(
                code=50001,
                message=f"更新公众号文章{str(e)}"
            )
        )

@router.get("/{mp_id}", summary="获取公众号详情")
async def get_mp(
    mp_id: str,
    current_user: dict = Depends(get_current_user)
):
    session = DB.get_session()
    try:
        from core.models.feed import Feed
        mp = session.query(Feed).filter(
            Feed.id == mp_id,
            Feed.owner_id == _owner(current_user)
        ).first()
        if not mp:
            raise HTTPException(
                status_code=status.HTTP_201_CREATED,
                detail=error_response(
                    code=40401,
                    message="公众号不存在"
                )
            )
        return success_response(mp)
    except Exception as e:
        logger.error(f"获取公众号详情错误: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_201_CREATED,
            detail=error_response(
                code=50001,
                message="获取公众号详情失败"
            )
        )
@router.post("/by_article", summary="通过文章链接获取公众号详情")
async def get_mp_by_article(
    url: str=Query(..., min_length=1),
    current_user: dict = Depends(get_current_user)
):
    try:
        info =await WXArticleFetcher().async_get_article_content(url)
        
        if not info:
            raise HTTPException(
                status_code=status.HTTP_201_CREATED,
                detail=error_response(
                    code=40401,
                    message="公众号不存在"
                )
            )
        return success_response(info)
    except Exception as e:
        logger.error(f"获取公众号详情错误: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_201_CREATED,
            detail=error_response(
                code=50001,
                message="请输入正确的公众号文章链接"
            )
        )

@router.post("", summary="添加公众号")
async def add_mp(
    mp_name: str = Body(..., min_length=1, max_length=255),
    mp_cover: str = Body(None, max_length=255),
    mp_id: str = Body(None, max_length=255),
    avatar: str = Body(None, max_length=500),
    mp_intro: str = Body(None, max_length=255),
    current_user: dict = Depends(get_current_user)
):
    session = DB.get_session()
    try:
        from core.models.feed import Feed
        import time
        now = datetime.now()
        owner_id = _owner(current_user)
        
        import base64
        try:
            mpx_id = base64.b64decode(mp_id).decode("utf-8")
        except Exception:
            mpx_id = mp_id
        local_avatar_path = f"{save_avatar_locally(avatar)}"
        
        # 检查公众号是否已存在
        existing_feed = session.query(Feed).filter(
            Feed.faker_id == mp_id,
            Feed.owner_id == owner_id
        ).first()
        
        if existing_feed:
            # 更新现有记录
            existing_feed.mp_name = mp_name
            existing_feed.mp_cover = local_avatar_path
            existing_feed.mp_intro = mp_intro
            existing_feed.updated_at = now
        else:
            # 创建新的Feed记录
            new_feed = Feed(
                id=f"MP_WXS_{owner_id}_{mpx_id}",
                owner_id=owner_id,
                mp_name=mp_name,
                mp_cover= local_avatar_path,
                mp_intro=mp_intro,
                status=1,  # 默认启用状态
                created_at=now,
                updated_at=now,
                faker_id=mp_id,
                update_time=0,
                sync_time=0,
            )
            session.add(new_feed)
           
        session.commit()
        
        feed = existing_feed if existing_feed else new_feed
         #在这里实现第一次添加获取公众号文章
        fetch_scheduled = False
        if not existing_feed:
            from core.queue import TaskQueue
            from core.wx import WxGather
            Max_page=int(cfg.get("max_page","2"))
            token, cookie, user_agent = _resolve_gather_auth(
                session,
                owner_id=owner_id,
                allow_global_fallback=False,
            )
            if token and cookie:
                TaskQueue.add_task(
                    WxGather().Model().get_Articles,
                    faker_id=feed.faker_id,
                    Mps_id=feed.id,
                    CallBack=UpdateArticle,
                    MaxPage=Max_page,
                    Mps_title=mp_name,
                    token=token,
                    cookie=cookie,
                    user_agent=user_agent,
                )
                fetch_scheduled = True
            
        log_event(logger, E.FEED_SUBSCRIBE, owner_id=owner_id, mp_name=mp_name, mp_id=feed.id)
        return success_response({
            "id": feed.id,
            "mp_name": feed.mp_name,
            "mp_cover": feed.mp_cover,
            "mp_intro": feed.mp_intro,
            "status": feed.status,
            "faker_id":mp_id,
            "created_at": feed.created_at.isoformat(),
            "fetch_scheduled": fetch_scheduled,
        })
    except Exception as e:
        session.rollback()
        logger.error(f"添加公众号错误: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_201_CREATED,
            detail=error_response(
                code=50001,
                message="添加公众号失败"
            )
        )


@router.delete("/{mp_id}", summary="删除订阅号")
async def delete_mp(
    mp_id: str,
    current_user: dict = Depends(get_current_user)
):
    session = DB.get_session()
    try:
        from core.models.feed import Feed
        from core.models.article import Article
        owner_id = _owner(current_user)
        mp = session.query(Feed).filter(
            Feed.id == mp_id,
            Feed.owner_id == owner_id
        ).first()
        if not mp:
            raise HTTPException(
                status_code=status.HTTP_201_CREATED,
                detail=error_response(
                    code=40401,
                    message="订阅号不存在"
                )
            )
        
        session.query(Article).filter(
            Article.mp_id == mp_id,
            Article.owner_id == owner_id
        ).delete(synchronize_session=False)
        session.delete(mp)
        session.commit()
        log_event(logger, E.FEED_UNSUBSCRIBE, owner_id=owner_id, mp_id=mp_id)
        return success_response({
            "message": "订阅号删除成功",
            "id": mp_id
        })
    except Exception as e:
        session.rollback()
        logger.error(f"删除订阅号错误: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_201_CREATED,
            detail=error_response(
                code=50001,
                message="删除订阅号失败"
            )
        )
