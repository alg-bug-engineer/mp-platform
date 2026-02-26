from core.config import cfg
from core.log import get_logger
from core.events import log_event, E
import time

logger = get_logger(__name__)

def sys_notice(text:str="",title:str="",tag:str='系统通知',type=""):
    from core.notice import notice
    markdown_text = f"### {title} {type} {tag}\n{text}"
    log_event(logger, E.NOTICE_CREATE, title=title[:60], tag=tag, type=type)
    webhook = cfg.get('notice')['dingding']
    if len(webhook)>0:
        notice(webhook, title, markdown_text)
    feishu_webhook = cfg.get('notice')['feishu']
    if len(feishu_webhook)>0:
        notice(feishu_webhook, title, markdown_text)
    wechat_webhook = cfg.get('notice')['wechat']
    if len(wechat_webhook)>0:
        notice(wechat_webhook, title, markdown_text)
    custom_webhook = cfg.get('notice')['custom']
    if len(custom_webhook)>0:
        notice(custom_webhook, title, markdown_text)
