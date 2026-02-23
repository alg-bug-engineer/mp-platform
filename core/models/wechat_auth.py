from .base import Base, Column, String, DateTime, Text


class WechatAuth(Base):
    __tablename__ = "wechat_auths"

    id = Column(String(255), primary_key=True, index=True)
    owner_id = Column(String(50), index=True, nullable=False, unique=True)
    token = Column(String(255), nullable=False, default="")
    cookie = Column(Text, nullable=False, default="")
    fingerprint = Column(String(255), default="")
    wx_app_name = Column(String(255), default="")
    wx_user_name = Column(String(255), default="")
    expiry_time = Column(String(64), default="")
    raw_json = Column(Text, default="")
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
