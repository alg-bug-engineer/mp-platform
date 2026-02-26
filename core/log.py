"""
core/log.py — 统一日志系统

特性：
• trace_id 通过 ContextVar 自动传播，无需手动传参
• 格式: 时间 [级别] [trace_id] 模块.函数:行号 - 消息
• get_logger(__name__) 获取任意模块的命名 logger
• set_trace_id / get_trace_id 管理请求/任务上下文
• trace_ctx() 上下文管理器供后台 Job 使用
• 根日志器统一配置，所有子模块自动继承（无需各自添加 handler）

使用方式：
    from core.log import get_logger, log_event, trace_ctx, set_trace_id, get_trace_id
    logger = get_logger(__name__)
    logger.info("普通消息")

    # 后台 Job：
    with trace_ctx(task.id) as tid:
        logger.info("event=task.start | task_id=%s", task.id)
"""

import logging
import logging.handlers
import sys
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Generator, Optional

try:
    import colorlog
except ImportError:
    colorlog = None

from core.config import cfg

# ─── Trace ID ContextVar ──────────────────────────────────────────────────────
_trace_id_var: ContextVar[str] = ContextVar("trace_id", default="-")


def _new_trace_id() -> str:
    """生成 8 位短 UUID。"""
    return uuid.uuid4().hex[:8]


def set_trace_id(tid: Optional[str] = None) -> str:
    """设置当前上下文的 trace_id，返回实际值。"""
    tid = str(tid or "").strip()[:16] or _new_trace_id()
    _trace_id_var.set(tid)
    return tid


def get_trace_id() -> str:
    """获取当前上下文的 trace_id（未设置时返回 '-'）。"""
    return _trace_id_var.get()


@contextmanager
def trace_ctx(trace_id: Optional[str] = None) -> Generator[str, None, None]:
    """
    后台 Job 的 trace 上下文管理器，退出时自动重置。

    用法：
        with trace_ctx(task.id) as tid:
            logger.info("event=task.start | task_id=%s", task.id)
    """
    token = _trace_id_var.set(str(trace_id or "").strip()[:16] or _new_trace_id())
    try:
        yield _trace_id_var.get()
    finally:
        _trace_id_var.reset(token)


# ─── Log Level ────────────────────────────────────────────────────────────────
_LOG_LEVEL_STR = cfg.get("log.level", "INFO").upper()
_LOG_FILE = cfg.get("log.file", "")

_LEVEL_MAP = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}
_level = _LEVEL_MAP.get(_LOG_LEVEL_STR, logging.INFO)

# ─── 日志格式 ─────────────────────────────────────────────────────────────────
# 时间 [级别  ] [trace_id] 模块.函数:行号 - 消息
_FMT = "%(asctime)s [%(levelname)-5s] [%(trace_id)s] %(name)s.%(funcName)s:%(lineno)d - %(message)s"
_DATE_FMT = "%Y-%m-%d %H:%M:%S"


# ─── Trace Filter ─────────────────────────────────────────────────────────────
class _TraceIdFilter(logging.Filter):
    """自动将 trace_id 注入每条日志 record，供 %(trace_id)s 使用。"""

    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = _trace_id_var.get()
        return True


_trace_filter = _TraceIdFilter()

# ─── Handler 注册（幂等，防止 uvicorn --reload 重复添加）──────────────────────
_APP_HANDLER_MARKER = "_is_app_log_handler"


def _setup_app_logging() -> None:
    """向根日志器注册 handler（幂等）。"""
    root = logging.getLogger()
    if any(getattr(h, _APP_HANDLER_MARKER, False) for h in root.handlers):
        return

    root.setLevel(_level)

    # 控制台 handler（stdout，被 nohup 捕获到 content-studio.log）
    if colorlog:
        ch = colorlog.StreamHandler(stream=sys.stdout)
        ch.setFormatter(
            colorlog.ColoredFormatter(
                "%(log_color)s" + _FMT,
                datefmt=_DATE_FMT,
                log_colors={
                    "DEBUG": "cyan",
                    "INFO": "green",
                    "WARNING": "yellow",
                    "ERROR": "red",
                    "CRITICAL": "red,bg_white",
                },
            )
        )
    else:
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(logging.Formatter(_FMT, datefmt=_DATE_FMT))

    ch.setLevel(_level)
    ch.addFilter(_trace_filter)
    setattr(ch, _APP_HANDLER_MARKER, True)
    root.addHandler(ch)

    # 文件 handler（可选，log.file 配置项）
    if _LOG_FILE:
        fh = logging.handlers.RotatingFileHandler(
            f"{_LOG_FILE}.log",
            maxBytes=5 * 1024 * 1024,
            backupCount=7,
            encoding="utf-8",
        )
        fh.setLevel(_level)
        fh.setFormatter(logging.Formatter(_FMT, datefmt=_DATE_FMT))
        fh.addFilter(_trace_filter)
        setattr(fh, _APP_HANDLER_MARKER, True)
        root.addHandler(fh)


_setup_app_logging()

# ─── 向后兼容 ─────────────────────────────────────────────────────────────────
# 旧代码 `from core.log import logger` 仍然可用
logger = logging.getLogger(__name__)


def get_logger(name: str) -> logging.Logger:
    """
    获取命名 logger，各模块标准用法：

        from core.log import get_logger
        logger = get_logger(__name__)
    """
    return logging.getLogger(name)
