from datetime import datetime
import uuid
from typing import Optional
from core.models.article import Article
from .article import UpdateArticle,Update_Over
import core.db as db
from core.wx import WxGather
from core.log import logger
from core.task import TaskScheduler
from core.models.feed import Feed
from core.config import cfg,DEBUG
from core.print import print_info,print_success,print_error,print_warning
from driver.wx import WX_API
from driver.success import Success
from core.wechat_auth_service import get_token_cookie
from core.models.message_task_log import MessageTaskLog
wx_db=db.Db(tag="任务调度")


def _resolve_auth(owner_id: str):
    session = db.DB.get_session()
    try:
        token, cookie = get_token_cookie(
            session=session,
            owner_id=str(owner_id or "").strip(),
            allow_global_fallback=False,
        )
        return str(token or "").strip(), str(cookie or "").strip(), str(cfg.get("user_agent", "") or "").strip()
    finally:
        try:
            session.close()
        except Exception:
            pass

def fetch_all_article():
    print("开始更新")
    wx=WxGather().Model()
    try:
        # 获取公众号列表
        mps=db.DB.get_all_mps()
        for item in mps:
            try:
                token, cookie, user_agent = _resolve_auth(getattr(item, "owner_id", ""))
                if not token or not cookie:
                    continue
                wx.get_Articles(
                    item.faker_id,
                    CallBack=UpdateArticle,
                    Mps_id=item.id,
                    Mps_title=item.mp_name,
                    MaxPage=1,
                    token=token,
                    cookie=cookie,
                    user_agent=user_agent,
                )
            except Exception as e:
                print(e)
        print(wx.articles) 
    except Exception as e:
        print(e)         
    finally:
        logger.info(f"所有公众号更新完成,共更新{wx.all_count()}条数据")


def test(info:str):
    print("任务测试成功",info)

from core.models.message_task import MessageTask
# from core.queue import TaskQueue
from .webhook import web_hook
interval=int(cfg.get("interval",60)) # 每隔多少秒执行一次


def _latest_article_for_feed(session, owner_id: str, feed_id: str) -> Optional[Article]:
    from core.models.base import DATA_STATUS

    return session.query(Article).filter(
        Article.owner_id == str(owner_id or "").strip(),
        Article.mp_id == str(feed_id or "").strip(),
        Article.status != DATA_STATUS.DELETED,
    ).order_by(
        Article.publish_time.desc(),
        Article.created_at.desc(),
    ).first()


def _run_auto_compose_sync(task: MessageTask, mp: Feed) -> str:
    enabled = int(getattr(task, "auto_compose_sync_enabled", 0) or 0)
    if enabled != 1:
        return ""
    platform = str(getattr(task, "auto_compose_platform", "wechat") or "wechat").strip().lower()
    if platform != "wechat":
        msg = f"自动创作仅支持 wechat 平台，当前={platform}"
        print_warning(f"任务({task.id})[{mp.mp_name}] {msg}")
        return msg

    owner_id = str(getattr(task, "owner_id", "") or getattr(mp, "owner_id", "") or "").strip()
    if not owner_id:
        msg = "缺少 owner_id，跳过自动创作"
        print_error(f"任务({task.id})[{mp.mp_name}] {msg}")
        return msg

    session = db.DB.get_session()
    try:
        from core.models.user import User as DBUser
        from core.ai_service import (
            build_prompt,
            call_openai_compatible,
            extract_first_image_url_from_text,
            get_or_create_profile,
            mark_local_draft_delivery,
            publish_batch_to_wechat_draft,
            refine_draft,
            save_local_draft,
        )
        from core.plan_service import consume_ai_usage, validate_ai_action
        from core.models.message_task import MessageTask as MessageTaskModel

        article = _latest_article_for_feed(session, owner_id=owner_id, feed_id=getattr(mp, "id", ""))
        if not article:
            msg = "未找到最新文章，跳过自动创作"
            print_warning(f"任务({task.id})[{mp.mp_name}] {msg}")
            return msg

        last_article_id = str(getattr(task, "auto_compose_last_article_id", "") or "").strip()
        if last_article_id and last_article_id == str(article.id or "").strip():
            msg = "最新文章已创作投递，跳过重复执行"
            print_info(f"任务({task.id})[{mp.mp_name}] {msg}")
            return msg

        user = session.query(DBUser).filter(DBUser.username == owner_id).first()
        if not user:
            msg = "用户不存在，无法自动创作"
            print_error(f"任务({task.id})[{mp.mp_name}] {msg}")
            return msg
        can_run, reason, _ = validate_ai_action(user, mode="create", publish_to_wechat=True)
        if not can_run:
            msg = f"自动创作被拦截: {reason}"
            print_warning(f"任务({task.id})[{mp.mp_name}] {msg}")
            return msg

        source_content = str(article.content or article.description or article.title or "").strip()
        if not source_content:
            msg = "最新文章内容为空，跳过自动创作"
            print_warning(f"任务({task.id})[{mp.mp_name}] {msg}")
            return msg

        instruction = str(getattr(task, "auto_compose_instruction", "") or "").strip()
        profile = get_or_create_profile(session, owner_id)
        create_options = {
            "platform": "wechat",
            "style": "专业深度",
            "length": "medium",
            "image_count": 0,
            "audience": "",
            "tone": "",
            "generate_images": False,
        }
        system_prompt, user_prompt = build_prompt(
            mode="create",
            title=str(article.title or ""),
            content=source_content,
            instruction=instruction,
            create_options=create_options,
        )
        draft_text = call_openai_compatible(profile, system_prompt, user_prompt)
        draft_text = refine_draft(
            profile=profile,
            mode="create",
            draft=draft_text,
            title=str(article.title or ""),
            create_options=create_options,
            instruction=instruction,
        )
        cover_url = extract_first_image_url_from_text(draft_text)
        local_draft = save_local_draft(
            owner_id=owner_id,
            article_id=str(article.id or ""),
            title=str(article.title or "AI 创作草稿").strip(),
            content=draft_text,
            platform="wechat",
            mode="create",
            metadata={
                "digest": "",
                "author": "",
                "cover_url": cover_url,
                "instruction": instruction,
                "options": create_options,
                "source": "message_task_auto",
                "message_task_id": str(task.id or ""),
                "feed_id": str(getattr(mp, "id", "") or ""),
            },
        )

        wechat_app_id = str(getattr(user, "wechat_app_id", "") or "").strip()
        wechat_app_secret = str(getattr(user, "wechat_app_secret", "") or "").strip()
        synced, message, raw = publish_batch_to_wechat_draft(
            [
                {
                    "title": str(article.title or "AI 创作草稿").strip(),
                    "content": draft_text,
                    "digest": "",
                    "author": "",
                    "cover_url": cover_url,
                }
            ],
            owner_id=owner_id,
            session=session,
            wechat_app_id=wechat_app_id,
            wechat_app_secret=wechat_app_secret,
        )

        mark_local_draft_delivery(
            owner_id=owner_id,
            draft_id=str(local_draft.get("id") or ""),
            platform="wechat",
            status="success" if synced else "failed",
            message=message,
            source="message_task_auto_sync",
            task_id=str(task.id or ""),
            extra={
                "media_id": str((raw or {}).get("media_id") or ""),
                "errmsg": str((raw or {}).get("errmsg") or (raw or {}).get("msg") or ""),
            },
        )

        consume_ai_usage(user, image_count=0)
        if synced:
            session.query(MessageTaskModel).filter(
                MessageTaskModel.id == str(task.id or ""),
                MessageTaskModel.owner_id == owner_id,
            ).update(
                {
                    MessageTaskModel.auto_compose_last_article_id: str(article.id or ""),
                    MessageTaskModel.auto_compose_last_sync_at: datetime.now(),
                },
                synchronize_session=False,
            )
            msg = (
                f"自动创作并同步成功（文章《{str(article.title or '').strip()[:36]}》，"
                f"草稿ID={str(local_draft.get('id') or '')[:8]}，"
                f"media_id={str((raw or {}).get('media_id') or '')[:24]}）"
            )
            print_success(f"任务({task.id})[{mp.mp_name}] {msg}")
        else:
            msg = (
                f"自动创作完成，但同步失败: {message}"
                f"（errmsg={str((raw or {}).get('errmsg') or (raw or {}).get('msg') or '')[:120]}）"
            )
            print_warning(f"任务({task.id})[{mp.mp_name}] {msg}")
        session.commit()
        return msg
    except Exception as e:
        try:
            session.rollback()
        except Exception:
            pass
        msg = f"自动创作异常: {e}"
        print_error(f"任务({getattr(task, 'id', '')})[{getattr(mp, 'mp_name', '')}] {msg}")
        return msg
    finally:
        try:
            session.close()
        except Exception:
            pass


def _write_task_execution_log(
    task: MessageTask,
    mp: Feed,
    update_count: int,
    status_code: int,
    log_text: str,
):
    session = db.DB.get_session()
    try:
        now = datetime.now()
        owner_id = str(getattr(task, "owner_id", "") or getattr(mp, "owner_id", "") or "").strip()
        if (not owner_id) and str(getattr(task, "id", "") or "").strip():
            try:
                from core.models.message_task import MessageTask as MessageTaskModel
                owner_row = session.query(MessageTaskModel.owner_id).filter(
                    MessageTaskModel.id == str(getattr(task, "id", "") or "").strip()
                ).first()
                owner_id = str(getattr(owner_row, "owner_id", "") or "")
            except Exception:
                owner_id = ""
        row = MessageTaskLog(
            id=str(uuid.uuid4()),
            owner_id=owner_id,
            task_id=str(getattr(task, "id", "") or ""),
            mps_id=str(getattr(mp, "id", "") or ""),
            update_count=max(0, int(update_count or 0)),
            status=int(status_code or 0),
            log=str(log_text or "")[:12000],
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        session.commit()
    except Exception as e:
        try:
            session.rollback()
        except Exception:
            pass
        print_error(f"写入任务执行日志失败: {e}")
    finally:
        try:
            session.close()
        except Exception:
            pass


def do_job(mp=None,task:MessageTask=None):
        # TaskQueue.add_task(test,info=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        # print("执行任务", task.mps_id)
        print("执行任务")
        started_at = datetime.now()
        logs = [f"任务开始: {started_at.strftime('%Y-%m-%d %H:%M:%S')}"]
        all_count=0
        count = 0
        status_code = 1
        wx=WxGather().Model()
        try:
            token, cookie, user_agent = _resolve_auth(getattr(mp, "owner_id", ""))
            if not token or not cookie:
                status_code = 2
                msg = "授权无效，跳过抓取"
                logs.append(msg)
                print_error(f"任务({getattr(task, 'id', '')})[{getattr(mp, 'mp_name', '')}] {msg}")
                return
            wx.get_Articles(
                mp.faker_id,
                CallBack=UpdateArticle,
                Mps_id=mp.id,
                Mps_title=mp.mp_name,
                MaxPage=1,
                Over_CallBack=Update_Over,
                interval=interval,
                token=token,
                cookie=cookie,
                user_agent=user_agent,
            )
            count = wx.all_count()
            logs.append(f"文章抓取完成，更新 {count} 条")
        except Exception as e:
            status_code = 2
            logs.append(f"执行异常: {e}")
            print_error(e)
            # raise
        finally:
            count=wx.all_count()
            all_count+=count
            from jobs.webhook import MessageWebHook 
            tms=MessageWebHook(task=task,feed=mp,articles=wx.articles)
            try:
                web_hook(tms)
                logs.append("消息通知处理完成")
            except Exception as e:
                status_code = 2
                logs.append(f"消息通知处理异常: {e}")
                print_error(e)

            if count <= 0:
                logs.append("没有更新到文章")

            auto_msg = _run_auto_compose_sync(task=task, mp=mp)
            if auto_msg:
                logs.append(f"自动创作同步: {auto_msg}")

            ended_at = datetime.now()
            duration = (ended_at - started_at).total_seconds()
            logs.append(f"任务结束: {ended_at.strftime('%Y-%m-%d %H:%M:%S')}")
            logs.append(f"执行耗时: {duration:.2f}秒")
            logs.append(f"更新完成: 成功{count}条")
            _write_task_execution_log(
                task=task,
                mp=mp,
                update_count=count,
                status_code=status_code if count >= 0 else 2,
                log_text="\n".join(logs),
            )
            if status_code == 1:
                print_success(f"任务({task.id})[{mp.mp_name}]执行成功,{count}成功条数")
            else:
                print_warning(f"任务({task.id})[{mp.mp_name}]执行结束,成功{count}条,请查看执行日志")

from core.queue import TaskQueue
def add_job(feeds:list[Feed]=None,task:MessageTask=None,isTest=False):
    if isTest:
        TaskQueue.clear_queue()
    for feed in feeds:
        TaskQueue.add_task(do_job,feed,task)
        if isTest:
            print(f"测试任务，{feed.mp_name}，加入队列成功")
            return
        print(f"{feed.mp_name}，加入队列成功")
    print_success(TaskQueue.get_queue_info())
    pass
import json
def get_feeds(task:MessageTask=None):
     try:
         mps = json.loads(str(getattr(task, "mps_id", "") or "[]"))
         if not isinstance(mps, list):
             mps = []
     except Exception:
         mps = []
     ids=",".join([str(item.get("id") or "").strip() for item in mps if isinstance(item, dict) and str(item.get("id") or "").strip()])
     if ids:
         mps=wx_db.get_mps_list(ids)
         if len(mps)>0:
            return mps
     return wx_db.get_all_mps()
scheduler=TaskScheduler()
def _owner_all_task_ids(owner_id: str) -> list[str]:
    owner = str(owner_id or "").strip()
    if not owner:
        return []
    session = db.DB.get_session()
    try:
        from core.models.message_task import MessageTask as MessageTaskModel
        rows = session.query(MessageTaskModel.id).filter(
            MessageTaskModel.owner_id == owner
        ).all()
        return [str(getattr(item, "id", "") or "") for item in rows if str(getattr(item, "id", "") or "").strip()]
    except Exception:
        return []
    finally:
        try:
            session.close()
        except Exception:
            pass


def reload_job(owner_id: str = ""):
    owner = str(owner_id or "").strip()
    if not owner:
        print_success("重载全部任务")
        scheduler.clear_all_jobs()
        TaskQueue.clear_queue()
        start_job()
        return

    print_success(f"重载用户任务: {owner}")
    for task_id in _owner_all_task_ids(owner):
        try:
            scheduler.remove_job(task_id)
        except Exception:
            pass
    start_job(owner_id=owner)

def run(job_id:str=None,isTest=False,owner_id: str = None):
    from .taskmsg import get_message_task
    tasks=get_message_task(job_id, owner_id=owner_id)
    if not tasks:
        print("没有任务")
        return None
    for task in tasks:
            #添加测试任务
            from core.print import print_warning
            print_warning(f"{task.name} 添加到队列运行")
            add_job(get_feeds(task),task,isTest=isTest)
            pass
    return tasks
def start_job(job_id:str=None, owner_id: str = ""):
    from .taskmsg import get_message_task
    tasks=get_message_task(job_id, owner_id=owner_id)
    if not tasks:
        print("没有任务")
        return
    tag="定时采集"
    for task in tasks:
        cron_exp=task.cron_exp
        if not cron_exp:
            print_error(f"任务[{task.id}]没有设置cron表达式")
            continue
      
        job_id=scheduler.add_cron_job(add_job,cron_expr=cron_exp,args=[get_feeds(task),task],job_id=str(task.id),tag="定时采集")
        print(f"已添加任务: {job_id}")
    scheduler.start()
    print("启动任务")
def start_all_task():
      #开启自动同步未同步 文章任务
    from jobs.fetch_no_article import start_sync_content
    from jobs.ai_publish import start_publish_queue_worker
    from jobs.billing import start_subscription_sweep_worker
    start_sync_content()
    start_publish_queue_worker()
    start_subscription_sweep_worker()
    start_job()
if __name__ == '__main__':
    # do_job()
    # start_all_task()
    pass
