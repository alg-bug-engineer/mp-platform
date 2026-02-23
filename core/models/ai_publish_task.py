from .base import Base, Column, String, Integer, DateTime, Text


class AIPublishTask(Base):
    from_attributes = True
    __tablename__ = "ai_publish_tasks"

    id = Column(String(255), primary_key=True, index=True)
    owner_id = Column(String(50), index=True, nullable=False)
    article_id = Column(String(255), index=True, nullable=False)
    title = Column(String(300), nullable=False)
    content = Column(Text, nullable=False)
    digest = Column(String(300), default="")
    author = Column(String(100), default="")
    cover_url = Column(String(1000), default="")
    platform = Column(String(32), default="wechat")
    status = Column(String(32), default="pending", index=True)
    retries = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    next_retry_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)
    last_response = Column(Text, nullable=True)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
