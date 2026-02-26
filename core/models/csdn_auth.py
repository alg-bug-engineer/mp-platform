from .base import Base, Column, String, DateTime, Text


class CsdnAuth(Base):
    __tablename__ = "csdn_auths"

    id = Column(String(255), primary_key=True)
    owner_id = Column(String(50), index=True, nullable=False, unique=True)
    # Playwright context.storage_state() 序列化 JSON（含 cookies + localStorage）
    storage_state = Column(Text, default="")
    # valid / expired
    status = Column(String(20), default="expired")
    csdn_username = Column(String(100), default="")
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
