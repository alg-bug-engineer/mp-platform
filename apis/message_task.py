from pydantic import BaseModel

# 标准导入分组和顺序
# 1. 标准库导入
import uuid
from datetime import datetime
from typing import List, Optional
from core.log import get_logger
from core.events import log_event, E
logger = get_logger(__name__)
# 2. 第三方库导入
from fastapi import APIRouter, Depends, HTTPException, status,Body,Query
from sqlalchemy.orm import Session
from sqlalchemy import or_

# 3. 本地应用/模块导入
from core.auth import get_current_user
from core.db import DB
from core.models.message_task import MessageTask
from core.models.message_task_log import MessageTaskLog
from .base import success_response, error_response

router = APIRouter(prefix="/message_tasks", tags=["消息任务"])


def _owner(current_user: dict) -> str:
    return current_user.get("username")


def _serialize_log_item(item: MessageTaskLog) -> dict:
    return {
        "id": str(getattr(item, "id", "") or ""),
        "task_id": str(getattr(item, "task_id", "") or ""),
        "mps_id": str(getattr(item, "mps_id", "") or ""),
        "owner_id": str(getattr(item, "owner_id", "") or ""),
        "update_count": int(getattr(item, "update_count", 0) or 0),
        "status": int(getattr(item, "status", 0) or 0),
        "log": str(getattr(item, "log", "") or ""),
        "created_at": item.created_at.isoformat() if getattr(item, "created_at", None) else None,
        "updated_at": item.updated_at.isoformat() if getattr(item, "updated_at", None) else None,
    }

@router.get("", summary="获取消息任务列表")
async def list_message_tasks(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: Optional[int] = None,
    current_user: dict = Depends(get_current_user)
):
    db=DB.get_session()
    """
    获取消息任务列表
    
    参数:
        skip: 跳过的记录数，用于分页
        limit: 每页返回的最大记录数
        status: 可选，按状态筛选任务
        db: 数据库会话
        current_user: 当前认证用户
        
    返回:
        包含消息任务列表的成功响应，或错误响应
        
    异常:
        数据库查询异常: 返回500内部服务器错误
    """
    try:
        db.expire_all()
        query = db.query(MessageTask).filter(MessageTask.owner_id == _owner(current_user))
        if status is not None:
            query = query.filter(MessageTask.status == status)
        
        total = query.count()
        message_tasks = query.offset(offset).limit(limit).all()
        
        return success_response({
            "list": message_tasks ,
            "page": {
                "limit": limit,
                "offset": offset
            },
            "total": total
        })
    except Exception as e:
        return error_response(code=500, message=str(e))

@router.get("/{task_id}", summary="获取单个消息任务详情")
async def get_message_task(
    task_id: str,
    current_user: dict = Depends(get_current_user)
):
    db=DB.get_session()
    """
    获取单个消息任务详情
    
    参数:
        task_id: 消息任务ID
        db: 数据库会话
        current_user: 当前认证用户
        
    返回:
        包含消息任务详情的成功响应，或错误响应
        
    异常:
        404: 消息任务不存在
        500: 数据库查询异常
    """
    try:
        message_task = db.query(MessageTask).filter(
            MessageTask.id == task_id,
            MessageTask.owner_id == _owner(current_user)
        ).first()
        if not message_task:
            raise HTTPException(status_code=404, detail="Message task not found")
        return success_response(data=message_task)
    except Exception as e:
        return error_response(code=500, message=str(e))


@router.get("/{task_id}/logs", summary="获取消息任务执行日志")
async def get_message_task_logs(
    task_id: str,
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
):
    db = DB.get_session()
    try:
        task = db.query(MessageTask).filter(
            MessageTask.id == task_id,
            MessageTask.owner_id == _owner(current_user),
        ).first()
        if not task:
            raise HTTPException(status_code=404, detail="Message task not found")
        query = db.query(MessageTaskLog).filter(
            MessageTaskLog.task_id == task_id,
            or_(
                MessageTaskLog.owner_id == _owner(current_user),
                MessageTaskLog.owner_id.is_(None),
                MessageTaskLog.owner_id == "",
            ),
        )
        total = query.count()
        rows = query.order_by(MessageTaskLog.created_at.desc()).offset(offset).limit(limit).all()
        return success_response(
            {
                "list": [_serialize_log_item(item) for item in rows],
                "total": total,
                "page": {"limit": limit, "offset": offset},
            }
        )
    except Exception as e:
        return error_response(code=500, message=str(e))
@router.get("/message/test/{task_id}", summary="测试消息")
async def test_message_task(
    task_id: str,
    current_user: dict = Depends(get_current_user)
):
    db=DB.get_session()
    """
    测试消息消息任务详情
    
    参数:
        task_id: 消息任务ID
        
    返回:
        包含消息任务详情的成功响应，或错误响应
        
    异常:
        404: 消息任务不存在
        500: 数据库查询异常
    """
    try:
        message_task = db.query(MessageTask).filter(
            MessageTask.id == task_id,
            MessageTask.owner_id == _owner(current_user)
        ).first()
        if not message_task:
            raise HTTPException(status_code=404, detail="Message task not found")
        return success_response(data=message_task)
    except Exception as e:
        return error_response(code=500, message=str(e))
@router.get("/{task_id}/run", summary="执行单个消息任务详情")
async def run_message_task(
    task_id: str,
    isTest:bool=Query(False),
    current_user: dict = Depends(get_current_user)
):
    """
    执行单个消息任务详情
    
    参数:
        task_id: 消息任务ID
        db: 数据库会话
        current_user: 当前认证用户
        
    返回:
        包含消息任务详情的成功响应，或错误响应
        
    异常:
        404: 消息任务不存在
        500: 数据库查询异常
    """
    try:
        from jobs.mps import run
        mps={
            "count":0,
            "list":[]
        }
        tasks=run(task_id,isTest=isTest,owner_id=_owner(current_user))
        count=0
        if not tasks:
            raise HTTPException(status_code=404, detail="Message task not found")
        else:
            import json
            for task in tasks:
                try:
                    ids=json.loads(task.mps_id)
                    count+=len(ids)
                    mps['count']=count
                    mps['list'].append(ids)
                except Exception as e:
                    logger.error(str(e))
                    pass
        if isTest:
            count=1
        mps["message"]=f"执行成功，共执行更新{count}个订阅号"
        return success_response(data=mps,message=f"执行成功，共执行更新{count}个订阅号")

    except Exception as e:
        logger.error(str(e))
        return error_response(code=402, message=str(e))


class MessageTaskCreate(BaseModel):
    message_template: str=""
    web_hook_url: str=""
    mps_id: str=""
    name: str=""
    message_type: int=0
    cron_exp:str=""
    auto_compose_sync_enabled: int = 0
    auto_compose_platform: str = "wechat"
    auto_compose_instruction: str = ""
    auto_compose_topk: int = 1
    csdn_publish_enabled: int = 0
    csdn_publish_topk: int = 3
    task_type: str = 'crawl'
    publish_platforms: list = []
    status: Optional[int] = 0

@router.post("", summary="创建消息任务", status_code=status.HTTP_201_CREATED)
async def create_message_task(
    task_data: MessageTaskCreate = Body(...),
    current_user: dict = Depends(get_current_user)
):
    """
    创建新消息任务
    
    参数:
        task_data: 消息任务创建数据
        db: 数据库会话
        current_user: 当前认证用户
        
    返回:
        201: 包含新创建消息任务的响应
        400: 请求数据验证失败
        500: 数据库操作异常
    """
    db=DB.get_session()
    try:
        import json as _json
        db_task = MessageTask(
            id=str(uuid.uuid4()),
            owner_id=_owner(current_user),
            message_template=task_data.message_template,
            web_hook_url=task_data.web_hook_url,
            cron_exp=task_data.cron_exp,
            mps_id=task_data.mps_id,
            message_type=task_data.message_type,
            name=task_data.name,
            auto_compose_sync_enabled=1 if int(task_data.auto_compose_sync_enabled or 0) else 0,
            auto_compose_platform=str(task_data.auto_compose_platform or "wechat").strip().lower() or "wechat",
            auto_compose_instruction=str(task_data.auto_compose_instruction or "").strip(),
            auto_compose_topk=max(1, int(task_data.auto_compose_topk or 1)),
            csdn_publish_enabled=1 if int(task_data.csdn_publish_enabled or 0) else 0,
            csdn_publish_topk=max(1, int(task_data.csdn_publish_topk or 3)),
            task_type=str(task_data.task_type or 'crawl').strip() or 'crawl',
            publish_platforms=_json.dumps(task_data.publish_platforms or [], ensure_ascii=False),
            status=task_data.status if task_data.status is not None else 0
        )
        db.add(db_task)
        db.commit()
        db.refresh(db_task)
        log_event(logger, E.TASK_SCHEDULE_ADD, owner_id=_owner(current_user), task_id=db_task.id, name=db_task.name)
        return success_response(data=db_task)
    except Exception as e:
        db.rollback()
        logger.error(str(e))
        return error_response(code=500, message=str(e))

@router.put("/{task_id}", summary="更新消息任务")
async def update_message_task(
    task_id: str,
    task_data: MessageTaskCreate = Body(...),
    current_user: dict = Depends(get_current_user)
):
    db=DB.get_session()
    """
    更新消息任务
    
    参数:
        task_id: 要更新的消息任务ID
        task_data: 消息任务更新数据
        db: 数据库会话
        current_user: 当前认证用户
        
    返回:
        包含更新后消息任务的响应
        404: 消息任务不存在
        400: 请求数据验证失败
        500: 数据库操作异常
    """
    try:
        db_task = db.query(MessageTask).filter(
            MessageTask.id == task_id,
            MessageTask.owner_id == _owner(current_user)
        ).first()
        if not db_task:
            raise HTTPException(status_code=404, detail="Message task not found")
        
        if task_data.message_template is not None:
            db_task.message_template = task_data.message_template
        if task_data.web_hook_url is not None:
            db_task.web_hook_url = task_data.web_hook_url
        if task_data.mps_id is not None:
            db_task.mps_id = task_data.mps_id
        if task_data.status is not None:
            db_task.status = task_data.status
        if task_data.cron_exp is not None:
            db_task.cron_exp = task_data.cron_exp
        if task_data.message_type is not None:
            db_task.message_type = task_data.message_type
        if task_data.name is not None:
            db_task.name = task_data.name
        import json as _json
        db_task.auto_compose_sync_enabled = 1 if int(task_data.auto_compose_sync_enabled or 0) else 0
        db_task.auto_compose_platform = str(task_data.auto_compose_platform or "wechat").strip().lower() or "wechat"
        db_task.auto_compose_instruction = str(task_data.auto_compose_instruction or "").strip()
        db_task.auto_compose_topk = max(1, int(task_data.auto_compose_topk or 1))
        db_task.csdn_publish_enabled = 1 if int(task_data.csdn_publish_enabled or 0) else 0
        db_task.csdn_publish_topk = max(1, int(task_data.csdn_publish_topk or 3))
        db_task.publish_platforms = _json.dumps(task_data.publish_platforms or [], ensure_ascii=False)
        db.commit()
        db.refresh(db_task)
        return success_response(data=db_task)
    except Exception as e:
        db.rollback()
        return error_response(code=500, message=str(e))
@router.put("/job/fresh",summary="重载任务")
async def fresh_message_task(
     current_user: dict = Depends(get_current_user)
):
    """
    重载任务
    """
    from jobs.mps import reload_job
    owner_id = _owner(current_user)
    if current_user.get("role") == "admin":
        reload_job()
        return success_response(message="任务已重载（全量）")
    reload_job(owner_id=owner_id)
    return success_response(message="任务已重载（当前账号）")
@router.delete("/{task_id}",summary="删除消息任务")
async def delete_message_task(
    task_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    删除消息任务
    
    参数:
        task_id: 要删除的消息任务ID
        db: 数据库会话
        current_user: 当前认证用户
        
    返回:
        204: 成功删除，无返回内容
        404: 消息任务不存在
        500: 数据库操作异常
    """
    db=DB.get_session()
    try:
        db_task = db.query(MessageTask).filter(
            MessageTask.id == task_id,
            MessageTask.owner_id == _owner(current_user)
        ).first()
        if not db_task:
            raise HTTPException(status_code=404, detail="Message task not found")
        
        db.delete(db_task)
        db.commit()
        log_event(logger, E.TASK_SCHEDULE_REMOVE, owner_id=_owner(current_user), task_id=task_id)
        return success_response(message="Message task deleted successfully")
    except Exception as e:
        db.rollback()
        return error_response(code=500, message=str(e))
