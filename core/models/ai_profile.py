from .base import Base, Column, String, DateTime, Integer


class AIProfile(Base):
    from_attributes = True
    __tablename__ = "ai_profiles"

    id = Column(String(255), primary_key=True)
    owner_id = Column(String(50), unique=True, index=True, nullable=False)
    provider_name = Column(String(50), default="openai-compatible")
    model_name = Column(String(100), default="kimi-k2-0711-preview")
    base_url = Column(String(500), nullable=False)
    api_key = Column(String(500), nullable=False)
    temperature = Column(Integer, default=70)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
