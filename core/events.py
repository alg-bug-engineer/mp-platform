"""
core/events.py — 结构化事件日志

提供统一的事件类型常量（E 类）和 log_event() 格式化方法。
所有关键操作均通过此模块记录，确保日志可 grep / 统计。

格式：event=xxx | key=val | key=val
      ↑ 固定前缀    ↑ 可变语义字段

用法：
    from core.log import get_logger
    from core.events import log_event, E

    logger = get_logger(__name__)
    log_event(logger, E.TASK_EXECUTE_START, task_id="t001", mp="科技日报", type="publish")
    # 输出：event=task.execute.start | task_id=t001 | mp=科技日报 | type=publish
"""

import logging
from typing import Any


# ─── 事件类型常量 ──────────────────────────────────────────────────────────────
class E:
    """结构化事件类型常量，按功能模块分组。"""

    # ── 认证 Auth ──────────────────────────────────────────────────────────────
    AUTH_LOGIN_ATTEMPT = "auth.login.attempt"
    AUTH_LOGIN_SUCCESS = "auth.login.success"
    AUTH_LOGIN_FAIL = "auth.login.fail"
    AUTH_LOGOUT = "auth.logout"
    AUTH_QR_GENERATE = "auth.qr.generate"
    AUTH_QR_SCAN = "auth.qr.scan"
    AUTH_QR_SUCCESS = "auth.qr.login_success"
    AUTH_QR_FAIL = "auth.qr.fail"
    AUTH_TOKEN_REFRESH = "auth.token.refresh"
    AUTH_TOKEN_EXPIRE = "auth.token.expire"
    AUTH_TOKEN_VERIFY = "auth.token.verify"

    # ── 订阅 Feed ──────────────────────────────────────────────────────────────
    FEED_SUBSCRIBE = "feed.subscribe"
    FEED_UNSUBSCRIBE = "feed.unsubscribe"
    FEED_UPDATE = "feed.update"
    FEED_SYNC_START = "feed.sync.start"
    FEED_SYNC_COMPLETE = "feed.sync.complete"
    FEED_SYNC_FAIL = "feed.sync.fail"
    FEED_REFRESH = "feed.refresh"

    # ── 文章 Article ───────────────────────────────────────────────────────────
    ARTICLE_FETCH_START = "article.fetch.start"
    ARTICLE_FETCH_COMPLETE = "article.fetch.complete"
    ARTICLE_FETCH_FAIL = "article.fetch.fail"
    ARTICLE_UPDATE = "article.update"
    ARTICLE_DELETE = "article.delete"
    ARTICLE_READ = "article.read"
    ARTICLE_EXPORT = "article.export"
    ARTICLE_CONTENT_SYNC = "article.content_sync"

    # ── 消息任务 Task ──────────────────────────────────────────────────────────
    TASK_SCHEDULE_ADD = "task.schedule.add"
    TASK_SCHEDULE_REMOVE = "task.schedule.remove"
    TASK_EXECUTE_START = "task.execute.start"
    TASK_EXECUTE_COMPLETE = "task.execute.complete"
    TASK_EXECUTE_FAIL = "task.execute.fail"
    TASK_EXECUTE_SKIP = "task.execute.skip"
    TASK_LOG_WRITE = "task.log.write"

    # ── AI 创作 Compose ────────────────────────────────────────────────────────
    AI_COMPOSE_ENQUEUE = "ai.compose.enqueue"
    AI_COMPOSE_START = "ai.compose.start"
    AI_COMPOSE_COMPLETE = "ai.compose.complete"
    AI_COMPOSE_FAIL = "ai.compose.fail"
    AI_COMPOSE_RETRY = "ai.compose.retry"
    AI_USAGE_CHECK = "ai.usage.check"
    AI_USAGE_EXCEED = "ai.usage.exceed"
    AI_USAGE_CONSUME = "ai.usage.consume"

    # ── AI 发布 Publish ────────────────────────────────────────────────────────
    AI_PUBLISH_ENQUEUE = "ai.publish.enqueue"
    AI_PUBLISH_START = "ai.publish.start"
    AI_PUBLISH_COMPLETE = "ai.publish.complete"
    AI_PUBLISH_FAIL = "ai.publish.fail"

    # ── CSDN 授权 Auth ─────────────────────────────────────────────────────────
    CSDN_AUTH_QR_GENERATE = "csdn.auth.qr.generate"
    CSDN_AUTH_QR_SUCCESS = "csdn.auth.qr.success"
    CSDN_AUTH_QR_TIMEOUT = "csdn.auth.qr.timeout"
    CSDN_AUTH_QR_CANCEL = "csdn.auth.qr.cancel"
    CSDN_AUTH_EXPIRED = "csdn.auth.expired"

    # ── CSDN 推送 ──────────────────────────────────────────────────────────────
    CSDN_PUSH_START = "csdn.push.start"
    CSDN_PUSH_BROWSER_LAUNCH = "csdn.push.browser_launch"
    CSDN_PUSH_EDITOR_READY = "csdn.push.editor_ready"
    CSDN_PUSH_CONTENT_FILL = "csdn.push.content_fill"
    CSDN_PUSH_CONTENT_VERIFY = "csdn.push.content_verify"
    CSDN_PUSH_PUBLISH_CLICK = "csdn.push.publish_click"
    CSDN_PUSH_COMPLETE = "csdn.push.complete"
    CSDN_PUSH_FAIL = "csdn.push.fail"
    CSDN_PUSH_NEED_REAUTH = "csdn.push.need_reauth"

    # ── 计费 Billing ───────────────────────────────────────────────────────────
    BILLING_ORDER_CREATE = "billing.order.create"
    BILLING_ORDER_PAY = "billing.order.pay"
    BILLING_ORDER_CANCEL = "billing.order.cancel"
    BILLING_SUBSCRIPTION_EXPIRE = "billing.subscription.expire"
    BILLING_SUBSCRIPTION_RENEW = "billing.subscription.renew"
    BILLING_SWEEP_START = "billing.sweep.start"
    BILLING_SWEEP_COMPLETE = "billing.sweep.complete"

    # ── 站内信 Notice ──────────────────────────────────────────────────────────
    NOTICE_CREATE = "notice.create"
    NOTICE_READ = "notice.read"
    NOTICE_READ_ALL = "notice.read_all"
    NOTICE_DELETE = "notice.delete"
    NOTICE_DELETE_ALL = "notice.delete_all"

    # ── Webhook ────────────────────────────────────────────────────────────────
    WEBHOOK_SEND_START = "webhook.send.start"
    WEBHOOK_SEND_COMPLETE = "webhook.send.complete"
    WEBHOOK_SEND_FAIL = "webhook.send.fail"

    # ── 系统 System ────────────────────────────────────────────────────────────
    SYSTEM_STARTUP = "system.startup"
    SYSTEM_DB_INIT = "system.db_init"
    SYSTEM_QUEUE_START = "system.queue.start"
    SYSTEM_JOB_ADD = "system.job.add"
    SYSTEM_JOB_REMOVE = "system.job.remove"
    SYSTEM_CONFIG_LOAD = "system.config.load"
    SYSTEM_RELOAD = "system.reload"


# ─── 结构化日志方法 ────────────────────────────────────────────────────────────
def log_event(
    logger: logging.Logger,
    event: str,
    level: str = "info",
    **fields: Any,
) -> None:
    """
    记录结构化事件日志，格式：event=xxx | key=val | key=val

    示例：
        log_event(logger, E.TASK_EXECUTE_START,
                  task_id="t001", mp="科技日报", type="publish")
        # → event=task.execute.start | task_id=t001 | mp=科技日报 | type=publish

        log_event(logger, E.CSDN_PUSH_FAIL, level="error",
                  reason="content_mismatch", elapsed="8.2s")
        # → event=csdn.push.fail | reason=content_mismatch | elapsed=8.2s
    """
    parts = [f"event={event}"]
    for k, v in fields.items():
        sv = str(v) if not isinstance(v, str) else v
        # 截断超长字段，避免单行日志过大
        if len(sv) > 300:
            sv = sv[:297] + "..."
        parts.append(f"{k}={sv}")
    msg = " | ".join(parts)
    getattr(logger, level)(msg, stacklevel=2)
