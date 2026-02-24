from .base import Base, Column, String, DateTime, Text


class AIComposeResult(Base):
    from_attributes = True
    __tablename__ = "ai_compose_results"

    id = Column(String(255), primary_key=True, index=True)
    owner_id = Column(String(50), index=True, nullable=False)
    article_id = Column(String(255), index=True, nullable=False)
    mode = Column(String(32), index=True, nullable=False)
    title = Column(String(300), default="")
    source_title = Column(String(300), default="")
    request_signature = Column(String(255), index=True, default="")
    request_payload = Column(Text, nullable=True)
    result_json = Column(Text, nullable=False)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
