import uuid
from datetime import datetime
from core.log import get_logger
from core.events import log_event, E
from core.models.user_notice import UserNotice

logger = get_logger(__name__)


def create_notice(session, owner_id: str, title: str, content: str, notice_type: str, ref_id: str = None):
    """创建站内信通知"""
    try:
        notice = UserNotice(
            id=str(uuid.uuid4()),
            owner_id=str(owner_id or "").strip(),
            title=str(title or "")[:300],
            content=str(content or ""),
            notice_type=str(notice_type or "task")[:32],
            status=0,
            ref_id=str(ref_id or "")[:255] if ref_id else None,
            created_at=datetime.now(),
        )
        session.add(notice)
        session.flush()
        log_event(logger, E.NOTICE_CREATE, owner_id=owner_id, type=notice_type, title=str(title or "")[:100])
        return notice
    except Exception as e:
        logger.error("创建站内信失败: %s", e)
        return None
