import time
from threading import Thread

from core.config import cfg
from core.db import DB
from core.billing_service import sweep_expired_subscriptions
from core.log import logger


def _worker_loop():
    interval = max(300, int(cfg.get("billing.subscription_sweep_interval_seconds", 3600) or 3600))
    while True:
        session = None
        try:
            session = DB.get_session()
            result = sweep_expired_subscriptions(session=session, limit=1000)
            if int(result.get("total", 0) or 0) > 0:
                logger.info("订阅到期降级完成: %s", result)
        except Exception:
            logger.exception("订阅到期扫描异常")
        finally:
            if session is not None and hasattr(session, "close"):
                try:
                    session.close()
                except Exception:
                    pass
        time.sleep(interval)


def start_subscription_sweep_worker():
    t = Thread(target=_worker_loop, daemon=True)
    t.start()
    return t
