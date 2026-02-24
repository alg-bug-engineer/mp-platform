from .base import Base, Column, String, Integer, DateTime, Text


class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"

    id = Column(String(64), primary_key=True)
    owner_id = Column(String(50), index=True)
    user_id = Column(String(255), index=True)
    username = Column(String(50), index=True)
    session_id = Column(String(120), index=True)

    event_type = Column(String(64), index=True)
    page = Column(String(255), index=True)
    feature = Column(String(120), index=True)
    action = Column(String(120), index=True)

    method = Column(String(16), index=True)
    path = Column(String(500), index=True)
    status_code = Column(Integer, index=True)
    duration_ms = Column(Integer)

    input_name = Column(String(120), index=True)
    input_length = Column(Integer)
    value = Column(String(255))
    metadata_json = Column(Text)

    created_at = Column(DateTime, index=True)
    updated_at = Column(DateTime, index=True)
