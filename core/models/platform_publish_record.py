from .base import Base, Column, String, DateTime, Text
from datetime import datetime


class PlatformPublishRecord(Base):
    """跨任务平台推送记录，按 owner_id + platform + title_hash 去重，避免同一标题推送多次。"""
    __tablename__ = 'platform_publish_records'

    id = Column(String(255), primary_key=True, index=True)
    owner_id = Column(String(50), index=True, nullable=False)
    platform = Column(String(32), index=True, nullable=False)   # "csdn" | "wechat"
    title = Column(String(500), nullable=False)                  # 原始标题（展示用）
    title_hash = Column(String(64), index=True, nullable=False)  # MD5(title.strip().lower())
    article_id = Column(String(255), default="")                 # 来源文章 ID
    task_id = Column(String(255), default="")                    # 触发的任务 ID
    created_at = Column(DateTime, default=datetime.now)
