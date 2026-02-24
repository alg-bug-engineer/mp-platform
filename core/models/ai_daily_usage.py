from .base import Base, Column, String, Integer, DateTime


class AIDailyUsage(Base):
    __tablename__ = "ai_daily_usages"

    id = Column(String(255), primary_key=True, index=True)
    owner_id = Column(String(50), index=True, nullable=False)
    usage_date = Column(String(10), index=True, nullable=False)  # YYYY-MM-DD
    used_count = Column(Integer, default=0)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
