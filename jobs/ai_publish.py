import time
from threading import Thread

from core.config import cfg
from core.db import DB
from core.ai_service import process_pending_publish_tasks
from core.log import get_logger
from core.events import log_event, E

logger = get_logger(__name__)


def _worker_loop():
    interval = max(10, int(cfg.get("ai.publish_queue_interval_seconds", 45) or 45))
    while True:
        session = None
        try:
            session = DB.get_session()
            log_event(logger, E.AI_PUBLISH_START, interval=interval)
            process_pending_publish_tasks(session=session, owner_id="", limit=20)
        except Exception:
            logger.exception("草稿投递队列处理异常")
        finally:
            if session is not None and hasattr(session, "close"):
                try:
                    session.close()
                except Exception:
                    pass
        time.sleep(interval)


def start_publish_queue_worker():
    t = Thread(target=_worker_loop, daemon=True)
    t.start()
    return t
