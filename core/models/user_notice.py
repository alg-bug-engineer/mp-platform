from .base import Base, Column, String, Integer, DateTime, Text


class UserNotice(Base):
    __tablename__ = 'user_notices'
    id = Column(String(255), primary_key=True)
    owner_id = Column(String(50), index=True)
    title = Column(String(300))
    content = Column(Text)
    notice_type = Column(String(32))  # task/compose/analytics/imitation
    status = Column(Integer, default=0)  # 0=未读 1=已读
    ref_id = Column(String(255), nullable=True)  # 关联资源ID
    created_at = Column(DateTime)
