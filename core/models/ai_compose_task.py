from .base import Base, Column, String, DateTime, Text


class AIComposeTask(Base):
    from_attributes = True
    __tablename__ = "ai_compose_tasks"

    id = Column(String(255), primary_key=True, index=True)
    owner_id = Column(String(50), index=True, nullable=False)
    article_id = Column(String(255), index=True, nullable=False)
    mode = Column(String(32), index=True, nullable=False)
    request_payload = Column(Text, nullable=False)
    status = Column(String(32), default="pending", index=True)
    status_message = Column(String(500), default="")
    error_message = Column(Text, nullable=True)
    result_json = Column(Text, nullable=True)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
