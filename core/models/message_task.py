# 从 sqlalchemy 导入所需的列类型和数据类型
from .base import Base,Column, Integer, String, DateTime,JSON,Text
# 从 datetime 模块导入 datetime 类，用于处理日期和时间
from datetime import datetime

# 定义 MessageTask 类，继承自 Base 基类
class MessageTask(Base):
    from_attributes = True
    # 指定数据库表名为 message_tasks
    __tablename__ = 'message_tasks'
    
    # 定义 id 字段，作为主键，同时创建索引
    id = Column(String(255), primary_key=True, index=True)
    owner_id = Column(String(50), index=True)
    # 定义消息类型字段，不允许为空
    message_type = Column(Integer, nullable=False)
    # 定义消息内容字段，使用 JSON 类型存储
    name = Column(String(100), nullable=False)

    # 定义消息模板字段，不允许为空
    message_template = Column(Text, nullable=False)
    # 定义发送接口
    web_hook_url = Column(String(500), nullable=False)
    # 定义需要通知的微信公众号ID集合
    mps_id = Column(Text, nullable=False)
    # 定义 cron_exp 表达式
    cron_exp=Column(String(100),nullable='* * 1 * *')
    # 自动创作并同步到平台（当前仅支持微信公众号草稿箱）
    auto_compose_sync_enabled = Column(Integer, default=0)
    auto_compose_platform = Column(String(32), default="wechat")
    auto_compose_instruction = Column(Text, default="")
    auto_compose_last_article_id = Column(String(255), default="")
    auto_compose_last_sync_at = Column(DateTime, nullable=True)
    auto_compose_topk = Column(Integer, default=1)  # 公众号topk检查篇数
    auto_compose_published_ids = Column(Text, default="[]")  # 已创作/推送文章ID列表(JSON)
    auto_compose_wechat_mode = Column(String(32), default="draft_only")  # "draft_only" | "draft_and_publish"
    csdn_publish_enabled = Column(Integer, default=0)  # 是否启用CSDN推送
    csdn_publish_topk = Column(Integer, default=3)  # CSDN推送检查topk篇数
    csdn_published_ids = Column(Text, default="[]")  # 已推送CSDN的文章ID列表(JSON)
    task_type = Column(String(20), default='crawl')  # 'crawl' | 'publish'
    publish_platforms = Column(Text, default='[]')  # JSON: ["wechat_mp","csdn"]
    # 定义任务状态字段，默认值为 pending
    status = Column(Integer, default=0)
    # 定义创建时间字段，默认值为当前 UTC 时间
    created_at = Column(DateTime)
    # 定义更新时间字段，默认值为当前 UTC 时间，更新时自动更新为当前时间
    updated_at = Column(DateTime )
