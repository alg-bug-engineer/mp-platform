from .base import Base, Column, Integer, String, DateTime, Text


class MessageTaskLog(Base):
    from_attributes = True
    __tablename__ = "message_tasks_logs"

    id = Column(String(255), primary_key=True, index=True)
    owner_id = Column(String(50), index=True)
    task_id = Column(String(255), index=True, nullable=False)
    mps_id = Column(String(255), nullable=False)
    update_count = Column(Integer, default=0)
    log = Column(Text, nullable=True)
    status = Column(Integer, default=0)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)


# 兼容历史导入写法：from core.models.message_task_log import MessageTask as MessageTaskLog
MessageTask = MessageTaskLog
