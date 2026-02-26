from fastapi import APIRouter, Depends, HTTPException, Query
from core.auth import get_current_user
from core.db import DB
from core.models.user_notice import UserNotice
from .base import success_response, error_response
from core.log import get_logger
from core.events import log_event, E
logger = get_logger(__name__)

router = APIRouter(prefix="/notices", tags=["站内信"])


def _owner(current_user: dict) -> str:
    return current_user.get("username", "")


@router.get("", summary="获取站内信列表")
async def list_notices(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: int = Query(None),
    current_user: dict = Depends(get_current_user),
):
    session = DB.get_session()
    try:
        owner_id = _owner(current_user)
        query = session.query(UserNotice).filter(UserNotice.owner_id == owner_id)
        if status is not None:
            query = query.filter(UserNotice.status == status)
        total = query.count()
        rows = (
            query.order_by(UserNotice.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return success_response({
            "list": [_serialize(r) for r in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        })
    except Exception as e:
        return error_response(code=500, message=str(e))
    finally:
        try:
            session.close()
        except Exception:
            pass


@router.get("/unread-count", summary="获取未读数量")
async def get_unread_count(current_user: dict = Depends(get_current_user)):
    session = DB.get_session()
    try:
        owner_id = _owner(current_user)
        count = session.query(UserNotice).filter(
            UserNotice.owner_id == owner_id,
            UserNotice.status == 0,
        ).count()
        return success_response({"count": count})
    except Exception as e:
        return error_response(code=500, message=str(e))
    finally:
        try:
            session.close()
        except Exception:
            pass


@router.put("/read-all", summary="全部标记已读")
async def mark_all_read(current_user: dict = Depends(get_current_user)):
    session = DB.get_session()
    try:
        owner_id = _owner(current_user)
        session.query(UserNotice).filter(
            UserNotice.owner_id == owner_id,
            UserNotice.status == 0,
        ).update({"status": 1}, synchronize_session=False)
        session.commit()
        log_event(logger, E.NOTICE_READ_ALL, owner_id=owner_id)
        return success_response(message="已全部标记已读")
    except Exception as e:
        session.rollback()
        return error_response(code=500, message=str(e))
    finally:
        try:
            session.close()
        except Exception:
            pass


@router.put("/{notice_id}/read", summary="标记单条已读")
async def mark_read(notice_id: str, current_user: dict = Depends(get_current_user)):
    session = DB.get_session()
    try:
        owner_id = _owner(current_user)
        row = session.query(UserNotice).filter(
            UserNotice.id == notice_id,
            UserNotice.owner_id == owner_id,
        ).first()
        if not row:
            raise HTTPException(status_code=404, detail="通知不存在")
        row.status = 1
        session.commit()
        return success_response(message="已标记已读")
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        return error_response(code=500, message=str(e))
    finally:
        try:
            session.close()
        except Exception:
            pass


@router.delete("/{notice_id}", summary="删除站内信")
async def delete_notice(notice_id: str, current_user: dict = Depends(get_current_user)):
    session = DB.get_session()
    try:
        owner_id = _owner(current_user)
        row = session.query(UserNotice).filter(
            UserNotice.id == notice_id,
            UserNotice.owner_id == owner_id,
        ).first()
        if not row:
            raise HTTPException(status_code=404, detail="通知不存在")
        session.delete(row)
        session.commit()
        log_event(logger, E.NOTICE_DELETE, owner_id=owner_id, notice_id=notice_id)
        return success_response(message="已删除")
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        return error_response(code=500, message=str(e))
    finally:
        try:
            session.close()
        except Exception:
            pass


def _serialize(row: UserNotice) -> dict:
    return {
        "id": str(row.id or ""),
        "owner_id": str(row.owner_id or ""),
        "title": str(row.title or ""),
        "content": str(row.content or ""),
        "notice_type": str(row.notice_type or ""),
        "status": int(row.status or 0),
        "ref_id": str(row.ref_id or "") if row.ref_id else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
