from datetime import datetime
import uuid
from typing import Optional
from core.models.article import Article
from .article import UpdateArticle,Update_Over
import core.db as db
from core.wx import WxGather
from core.log import get_logger, trace_ctx
from core.events import log_event, E
from core.task import TaskScheduler
from core.models.feed import Feed
from core.config import cfg,DEBUG
from driver.wx import WX_API
from driver.success import Success
from core.wechat_auth_service import get_token_cookie
from core.models.message_task_log import MessageTaskLog

logger = get_logger(__name__)
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
    logger.info("开始更新")
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
                logger.error("%s", e)
        logger.debug("%s", wx.articles)
    except Exception as e:
        logger.error("%s", e)
    finally:
        log_event(logger, E.ARTICLE_FETCH_COMPLETE, count=wx.all_count())


def test(info:str):
    logger.info("任务测试成功 %s", info)

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


def _topk_articles_for_feed(session, owner_id: str, feed_id: str, k: int) -> list:
    """返回按时间排序的 top-k 篇文章列表"""
    from core.models.base import DATA_STATUS

    k = max(1, int(k or 1))
    return session.query(Article).filter(
        Article.owner_id == str(owner_id or "").strip(),
        Article.mp_id == str(feed_id or "").strip(),
        Article.status != DATA_STATUS.DELETED,
    ).order_by(
        Article.publish_time.desc(),
        Article.created_at.desc(),
    ).limit(k).all()


def _run_auto_compose_sync(task: MessageTask, mp: Feed) -> str:
    enabled = int(getattr(task, "auto_compose_sync_enabled", 0) or 0)
    if enabled != 1:
        return ""
    platform = str(getattr(task, "auto_compose_platform", "wechat") or "wechat").strip().lower()
    if platform != "wechat":
        msg = f"自动创作仅支持 wechat 平台，当前={platform}"
        logger.warning("任务(%s)[%s] %s", task.id, mp.mp_name, msg)
        return msg

    owner_id = str(getattr(task, "owner_id", "") or getattr(mp, "owner_id", "") or "").strip()
    if not owner_id:
        msg = "缺少 owner_id，跳过自动创作"
        logger.error("任务(%s)[%s] %s", task.id, mp.mp_name, msg)
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

        topk = max(1, int(getattr(task, "auto_compose_topk", 1) or 1))
        candidates = _topk_articles_for_feed(session, owner_id=owner_id, feed_id=getattr(mp, "id", ""), k=topk)
        if not candidates:
            msg = "未找到最新文章，跳过自动创作"
            logger.warning("任务(%s)[%s] %s", task.id, mp.mp_name, msg)
            return msg

        # 读取已发布ID列表
        import json as _json
        try:
            published_ids = _json.loads(str(getattr(task, "auto_compose_published_ids", "[]") or "[]"))
            if not isinstance(published_ids, list):
                published_ids = []
        except Exception:
            published_ids = []

        # 兼容旧逻辑：auto_compose_last_article_id 也视为已发布
        last_article_id = str(getattr(task, "auto_compose_last_article_id", "") or "").strip()
        if last_article_id and last_article_id not in published_ids:
            published_ids.append(last_article_id)

        # 找第一篇未创作且内容非空的文章
        article = None
        for candidate in candidates:
            if str(candidate.id or "").strip() in published_ids:
                continue
            src = str(candidate.content or candidate.description or candidate.title or "").strip()
            if src:
                article = candidate
                break

        if not article:
            # 判断是因为内容都为空还是都已处理
            has_unpublished = any(str(c.id or "").strip() not in published_ids for c in candidates)
            if has_unpublished:
                msg = f"top-{topk} 未创作文章内容尚未同步，等待下次执行"
            else:
                msg = f"top-{topk} 文章均已创作投递，跳过重复执行"
            logger.info("任务(%s)[%s] %s", task.id, mp.mp_name, msg)
            return msg

        user = session.query(DBUser).filter(DBUser.username == owner_id).first()
        if not user:
            msg = "用户不存在，无法自动创作"
            logger.error("任务(%s)[%s] %s", task.id, mp.mp_name, msg)
            return msg
        can_run, reason, _ = validate_ai_action(user, mode="create", publish_to_wechat=True)
        if not can_run:
            msg = f"自动创作被拦截: {reason}"
            logger.warning("任务(%s)[%s] %s", task.id, mp.mp_name, msg)
            return msg

        source_content = str(article.content or article.description or article.title or "").strip()

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
        log_event(logger, E.AI_COMPOSE_START, task_id=str(task.id or ""), mp=mp.mp_name, article=str(article.title or "")[:50])
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
        log_event(logger, E.AI_PUBLISH_START, task_id=str(task.id or ""), mp=mp.mp_name, draft_id=str(local_draft.get("id") or "")[:8])
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
            new_published_ids = list(published_ids)
            article_id_str = str(article.id or "").strip()
            if article_id_str and article_id_str not in new_published_ids:
                new_published_ids.append(article_id_str)
            import json as _json2
            session.query(MessageTaskModel).filter(
                MessageTaskModel.id == str(task.id or ""),
                MessageTaskModel.owner_id == owner_id,
            ).update(
                {
                    MessageTaskModel.auto_compose_last_article_id: article_id_str,
                    MessageTaskModel.auto_compose_last_sync_at: datetime.now(),
                    MessageTaskModel.auto_compose_published_ids: _json2.dumps(new_published_ids, ensure_ascii=False),
                },
                synchronize_session=False,
            )
            msg = (
                f"自动创作并同步成功（文章《{str(article.title or '').strip()[:36]}》，"
                f"草稿ID={str(local_draft.get('id') or '')[:8]}，"
                f"media_id={str((raw or {}).get('media_id') or '')[:24]}）"
            )
            log_event(logger, E.AI_PUBLISH_COMPLETE, task_id=str(task.id or ""), mp=mp.mp_name,
                      article=str(article.title or "")[:50], media_id=str((raw or {}).get("media_id") or "")[:24])
            # 发送站内信通知
            try:
                from core.notice_service import create_notice
                create_notice(
                    session=session,
                    owner_id=owner_id,
                    title=f"AI自动创作完成：{str(article.title or '').strip()[:50]}",
                    content=msg,
                    notice_type="compose",
                    ref_id=str(local_draft.get("id") or ""),
                )
            except Exception:
                pass
        else:
            msg = (
                f"自动创作完成，但同步失败: {message}"
                f"（errmsg={str((raw or {}).get('errmsg') or (raw or {}).get('msg') or '')[:120]}）"
            )
            log_event(logger, E.AI_PUBLISH_FAIL, task_id=str(task.id or ""), mp=mp.mp_name,
                      reason=message[:120])
            logger.warning("任务(%s)[%s] %s", task.id, mp.mp_name, msg)
        session.commit()
        return msg
    except Exception as e:
        try:
            session.rollback()
        except Exception:
            pass
        msg = f"自动创作异常: {e}"
        log_event(logger, E.AI_COMPOSE_FAIL, task_id=str(getattr(task, "id", "")), mp=str(getattr(mp, "mp_name", "")), reason=str(e)[:200])
        return msg
    finally:
        try:
            session.close()
        except Exception:
            pass


def _run_csdn_publish_sync(task: MessageTask, mp: Feed) -> str:
    """CSDN 自动推送逻辑（topk 顺序）。
    流程：抓取内容 → AI 创作（配图 2 张，与用户创作指令保持一致）→ 推送到 CSDN。
    使用扫码登录的 storage_state，比 cookie 更稳定。
    """
    enabled = int(getattr(task, "csdn_publish_enabled", 0) or 0)
    if enabled != 1:
        return ""

    owner_id = str(getattr(task, "owner_id", "") or getattr(mp, "owner_id", "") or "").strip()
    if not owner_id:
        return "缺少 owner_id，跳过 CSDN 推送"

    session = db.DB.get_session()
    try:
        from core.notice_service import create_notice
        from core.csdn_auth_service import get_storage_state, mark_csdn_auth_expired
        import json as _json

        # ── 1. 获取 storage_state ──
        storage_state = get_storage_state(session, owner_id)
        if not storage_state:
            msg = "CSDN 未授权或登录态已失效，请到「CSDN 登录」页面扫码登录后再启用推送"
            logger.warning("任务(%s)[%s] %s", task.id, mp.mp_name, msg)
            return msg

        topk = max(1, int(getattr(task, "csdn_publish_topk", 3) or 3))
        candidates = _topk_articles_for_feed(session, owner_id=owner_id, feed_id=getattr(mp, "id", ""), k=topk)
        logger.info("任务(%s)[%s] CSDN推送 top-%d 候选文章数: %d", task.id, mp.mp_name, topk, len(candidates))
        if not candidates:
            return "未找到文章，跳过 CSDN 推送"

        try:
            csdn_published_ids = _json.loads(str(getattr(task, "csdn_published_ids", "[]") or "[]"))
            if not isinstance(csdn_published_ids, list):
                csdn_published_ids = []
        except Exception:
            csdn_published_ids = []

        logger.info("任务(%s)[%s] 已推送 ID 数: %d", task.id, mp.mp_name, len(csdn_published_ids))

        # ── 2. 找第一篇未推送且内容非空的文章 ──
        article = None
        for idx, candidate in enumerate(candidates):
            cid = str(candidate.id or "").strip()
            ctitle = str(candidate.title or "")[:40]
            clen = len(str(candidate.content or candidate.description or "").strip())
            already = cid in csdn_published_ids
            logger.info(
                "任务(%s)[%s] 候选[%d/%d] id=%s title=%r content_len=%d already_pushed=%s",
                task.id, mp.mp_name, idx + 1, len(candidates), cid, ctitle, clen, already,
            )
            if already:
                continue
            if clen > 0:
                article = candidate
                break

        if not article:
            has_unpublished = any(str(c.id or "").strip() not in csdn_published_ids for c in candidates)
            if has_unpublished:
                msg = f"top-{topk} 未推送文章内容尚未同步，等待下次执行"
            else:
                msg = f"top-{topk} 文章均已推送到 CSDN，跳过"
            logger.info("任务(%s)[%s] %s", task.id, mp.mp_name, msg)
            return msg

        article_id_str = str(article.id or "").strip()
        title = str(article.title or "").strip()
        source_content = str(article.content or article.description or "").strip()

        logger.info(
            "任务(%s)[%s] 选定文章 id=%s title=%r source_len=%d",
            task.id, mp.mp_name, article_id_str, title[:50], len(source_content),
        )

        # ── 3. AI 创作（与用户在任务配置中设置的创作指令保持一致，默认配图 2 张）──
        from core.models.user import User as DBUser
        from core.ai_service import (
            build_prompt,
            call_openai_compatible,
            get_or_create_profile,
            refine_draft,
        )
        from core.plan_service import consume_ai_usage, validate_ai_action

        user = session.query(DBUser).filter(DBUser.username == owner_id).first()
        if not user:
            msg = "用户不存在，无法 AI 创作"
            logger.error("任务(%s)[%s] %s", task.id, mp.mp_name, msg)
            return msg

        can_run, reason, _ = validate_ai_action(user, mode="create", publish_to_wechat=True)
        if not can_run:
            msg = f"CSDN AI 创作被拦截: {reason}"
            logger.warning("任务(%s)[%s] %s", task.id, mp.mp_name, msg)
            return msg

        instruction = str(getattr(task, "auto_compose_instruction", "") or "").strip()
        profile = get_or_create_profile(session, owner_id)
        create_options = {
            "platform": "csdn",
            "style": "专业深度",
            "length": "medium",
            "image_count": 0,       # CSDN 不插入图片 URL（外部图床无法转存），图片用文字标注代替
            "audience": "",
            "tone": "",
            "generate_images": False,
        }
        log_event(logger, E.AI_COMPOSE_START, task_id=str(task.id or ""), mp=mp.mp_name,
                  article=str(article.title or "")[:50], platform="csdn")
        system_prompt, user_prompt = build_prompt(
            mode="create",
            title=title,
            content=source_content,
            instruction=instruction,
            create_options=create_options,
        )
        draft_text = call_openai_compatible(profile, system_prompt, user_prompt)
        draft_text = refine_draft(
            profile=profile,
            mode="create",
            draft=draft_text,
            title=title,
            create_options=create_options,
            instruction=instruction,
        )
        consume_ai_usage(user, image_count=0)
        logger.info(
            "任务(%s)[%s] CSDN AI 创作完成，创作后内容长度: %d 字符",
            task.id, mp.mp_name, len(draft_text),
        )

        # ── 4. 剥离外部图片链接（CSDN 无法转存外部图床，会导致转存失败或丢图）──
        import re as _re
        def _strip_external_images(text: str) -> str:
            """将 ![alt](url) 替换为纯文字标注，避免 CSDN 转存失败。"""
            return _re.sub(
                r'!\[([^\]]*)\]\([^\)]+\)',
                lambda m: f'【图：{m.group(1).strip() or "配图"}】' if m.group(1).strip() else '',
                text,
            )
        draft_text_clean = _strip_external_images(draft_text)
        if draft_text_clean != draft_text:
            logger.info(
                "任务(%s)[%s] 已剥离 CSDN 外部图片链接，内容长度 %d → %d",
                task.id, mp.mp_name, len(draft_text), len(draft_text_clean),
            )

        # ── 5. 推送创作后的内容到 CSDN ──
        log_event(logger, E.CSDN_PUSH_START, task_id=str(task.id or ""), mp=mp.mp_name,
                  title=title[:50], content_len=len(draft_text_clean))
        from jobs.csdn_publish import push_to_csdn
        success, push_msg, needs_reauth = push_to_csdn(storage_state, title, draft_text_clean)

        # 登录态失效 → 标记过期 + 站内信提醒用户重新扫码
        if needs_reauth:
            mark_csdn_auth_expired(session, owner_id)
            log_event(logger, E.CSDN_PUSH_NEED_REAUTH, task_id=str(task.id or ""), mp=mp.mp_name)
            try:
                create_notice(
                    session=session,
                    owner_id=owner_id,
                    title="CSDN 登录态已失效，需要重新扫码",
                    content="自动推送时检测到 CSDN 登录状态已失效。请前往「CSDN 登录」页面重新扫码登录，之后推送将自动恢复。",
                    notice_type="system",
                )
            except Exception:
                pass
            session.commit()
            return f"CSDN 登录态失效，请重新扫码：{push_msg}"

        from core.models.message_task import MessageTask as MessageTaskModel
        if success:
            new_ids = list(csdn_published_ids)
            if article_id_str and article_id_str not in new_ids:
                new_ids.append(article_id_str)
            session.query(MessageTaskModel).filter(
                MessageTaskModel.id == str(task.id or ""),
                MessageTaskModel.owner_id == owner_id,
            ).update(
                {MessageTaskModel.csdn_published_ids: _json.dumps(new_ids, ensure_ascii=False)},
                synchronize_session=False,
            )
            msg = f"CSDN 推送成功：《{title[:40]}》  {push_msg}"
            log_event(logger, E.CSDN_PUSH_COMPLETE, task_id=str(task.id or ""), mp=mp.mp_name,
                      title=title[:50], detail=push_msg[:120])
            try:
                create_notice(
                    session=session,
                    owner_id=owner_id,
                    title=f"CSDN 推送成功：{title[:50]}",
                    content=push_msg,
                    notice_type="task",
                    ref_id=article_id_str,
                )
            except Exception:
                pass
        else:
            msg = f"CSDN 推送失败：{push_msg}"
            log_event(logger, E.CSDN_PUSH_FAIL, task_id=str(task.id or ""), mp=mp.mp_name,
                      title=title[:50], reason=push_msg[:200])
            logger.warning("任务(%s)[%s] %s", task.id, mp.mp_name, msg)
            try:
                create_notice(
                    session=session,
                    owner_id=owner_id,
                    title=f"CSDN 推送失败：{title[:40]}",
                    content=msg,
                    notice_type="task",
                    ref_id=article_id_str,
                )
            except Exception:
                pass

        session.commit()
        return msg
    except Exception as e:
        try:
            session.rollback()
        except Exception:
            pass
        msg = f"CSDN 推送异常: {e}"
        log_event(logger, E.CSDN_PUSH_FAIL, task_id=str(getattr(task, "id", "")), mp=str(getattr(mp, "mp_name", "")), reason=str(e)[:200])
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
        log_event(logger, E.TASK_LOG_WRITE, task_id=str(getattr(task, "id", "")), status=status_code, update_count=update_count)
    except Exception as e:
        try:
            session.rollback()
        except Exception:
            pass
        logger.error("写入任务执行日志失败: %s", e)
    finally:
        try:
            session.close()
        except Exception:
            pass


def do_job(mp=None,task:MessageTask=None):
    with trace_ctx(f"job-{str(getattr(task, 'id', '') or '')[:8]}") as tid:
        log_event(logger, E.TASK_EXECUTE_START, task_id=str(getattr(task, "id", "")),
                  mp=str(getattr(mp, "mp_name", "")), type=str(getattr(task, "task_type", "crawl") or "crawl"))
        started_at = datetime.now()
        logs = [f"任务开始: {started_at.strftime('%Y-%m-%d %H:%M:%S')}"]
        count = 0
        status_code = 1

        task_type = str(getattr(task, 'task_type', '') or 'crawl').strip() or 'crawl'

        if task_type == 'publish':
            # 纯发布任务：不执行抓取，只调用发布逻辑
            try:
                import json as _json
                platforms = _json.loads(str(getattr(task, 'publish_platforms', '[]') or '[]'))
                if not isinstance(platforms, list):
                    platforms = []
            except Exception:
                platforms = []

            logs.append(f"发布任务，目标平台: {platforms}")

            if 'wechat_mp' in platforms:
                auto_msg = _run_auto_compose_sync(task=task, mp=mp)
                if auto_msg:
                    logs.append(f"自动创作同步: {auto_msg}")

            if 'csdn' in platforms:
                csdn_msg = _run_csdn_publish_sync(task=task, mp=mp)
                if csdn_msg:
                    logs.append(f"CSDN推送: {csdn_msg}")

            ended_at = datetime.now()
            duration = (ended_at - started_at).total_seconds()
            logs.append(f"任务结束: {ended_at.strftime('%Y-%m-%d %H:%M:%S')}")
            logs.append(f"执行耗时: {duration:.2f}秒")
            _write_task_execution_log(
                task=task,
                mp=mp,
                update_count=0,
                status_code=status_code,
                log_text="\n".join(logs),
            )
            try:
                owner_id = str(getattr(task, "owner_id", "") or getattr(mp, "owner_id", "") or "").strip()
                if owner_id:
                    from core.notice_service import create_notice
                    notice_session = db.DB.get_session()
                    try:
                        create_notice(
                            session=notice_session,
                            owner_id=owner_id,
                            title=f"发布任务执行完成：{str(getattr(mp, 'mp_name', '') or '')}",
                            content="\n".join(logs[-5:]) if logs else "任务执行完毕",
                            notice_type="task",
                            ref_id=str(getattr(task, "id", "") or ""),
                        )
                        notice_session.commit()
                    except Exception:
                        pass
                    finally:
                        try:
                            notice_session.close()
                        except Exception:
                            pass
            except Exception:
                pass
            log_event(logger, E.TASK_EXECUTE_COMPLETE, task_id=str(getattr(task, "id", "")),
                      mp=str(getattr(mp, "mp_name", "")), type="publish", duration=f"{duration:.2f}s")
            return

        # crawl 任务（默认）：保持现有逻辑不变
        all_count = 0
        wx = WxGather().Model()
        try:
            token, cookie, user_agent = _resolve_auth(getattr(mp, "owner_id", ""))
            if not token or not cookie:
                status_code = 2
                msg = "授权无效，跳过抓取"
                logs.append(msg)
                logger.error("任务(%s)[%s] %s", str(getattr(task, 'id', '')), str(getattr(mp, 'mp_name', '')), msg)
                return
            log_event(logger, E.FEED_SYNC_START, task_id=str(getattr(task, "id", "")), mp=str(getattr(mp, "mp_name", "")))
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
            logger.error("%s", e)
        finally:
            count = wx.all_count()
            all_count += count
            log_event(logger, E.ARTICLE_FETCH_COMPLETE, mp=str(getattr(mp, "mp_name", "")), count=count)
            from jobs.webhook import MessageWebHook
            tms = MessageWebHook(task=task, feed=mp, articles=wx.articles)
            try:
                log_event(logger, E.WEBHOOK_SEND_START, task_id=str(getattr(task, "id", "")),
                          url=str(getattr(task, "web_hook_url", "") or "")[:80])
                web_hook(tms)
                logs.append("消息通知处理完成")
                log_event(logger, E.WEBHOOK_SEND_COMPLETE, task_id=str(getattr(task, "id", "")))
            except Exception as e:
                status_code = 2
                logs.append(f"消息通知处理异常: {e}")
                log_event(logger, E.WEBHOOK_SEND_FAIL, task_id=str(getattr(task, "id", "")), reason=str(e)[:200])

            if count <= 0:
                logs.append("没有更新到文章")

            auto_msg = _run_auto_compose_sync(task=task, mp=mp)
            if auto_msg:
                logs.append(f"自动创作同步: {auto_msg}")

            csdn_msg = _run_csdn_publish_sync(task=task, mp=mp)
            if csdn_msg:
                logs.append(f"CSDN推送: {csdn_msg}")

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
            # 任务执行完成站内信通知
            try:
                owner_id = str(getattr(task, "owner_id", "") or getattr(mp, "owner_id", "") or "").strip()
                if owner_id:
                    from core.notice_service import create_notice
                    notice_session = db.DB.get_session()
                    try:
                        notice_title = f"任务执行完成：{str(getattr(mp, 'mp_name', '') or '')}（更新{count}条）"
                        notice_content = "\n".join(logs[-5:]) if logs else "任务执行完毕"
                        create_notice(
                            session=notice_session,
                            owner_id=owner_id,
                            title=notice_title[:300],
                            content=notice_content,
                            notice_type="task",
                            ref_id=str(getattr(task, "id", "") or ""),
                        )
                        notice_session.commit()
                    except Exception:
                        pass
                    finally:
                        try:
                            notice_session.close()
                        except Exception:
                            pass
            except Exception:
                pass
            if status_code == 1:
                log_event(logger, E.TASK_EXECUTE_COMPLETE, task_id=str(getattr(task, "id", "")),
                          mp=str(getattr(mp, "mp_name", "")), type="crawl", count=count, duration=f"{duration:.2f}s")
            else:
                log_event(logger, E.TASK_EXECUTE_FAIL, task_id=str(getattr(task, "id", "")),
                          mp=str(getattr(mp, "mp_name", "")), count=count)

from core.queue import TaskQueue
def add_job(feeds:list[Feed]=None,task:MessageTask=None,isTest=False):
    if isTest:
        TaskQueue.clear_queue()
    for feed in feeds:
        TaskQueue.add_task(do_job,feed,task)
        if isTest:
            logger.info("测试任务，%s，加入队列成功", feed.mp_name)
            return
        log_event(logger, E.SYSTEM_JOB_ADD, mp=feed.mp_name, task_id=str(getattr(task, "id", "")))
    logger.info("%s", TaskQueue.get_queue_info())
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
        logger.info("重载全部任务")
        scheduler.clear_all_jobs()
        TaskQueue.clear_queue()
        start_job()
        return

    logger.info("重载用户任务: %s", owner)
    for task_id in _owner_all_task_ids(owner):
        try:
            scheduler.remove_job(task_id)
            log_event(logger, E.TASK_SCHEDULE_REMOVE, task_id=task_id, owner_id=owner)
        except Exception:
            pass
    start_job(owner_id=owner)

def run(job_id:str=None,isTest=False,owner_id: str = None):
    from .taskmsg import get_message_task
    tasks=get_message_task(job_id, owner_id=owner_id)
    if not tasks:
        logger.info("没有任务")
        return None
    for task in tasks:
            #添加测试任务
            logger.warning("%s 添加到队列运行", task.name)
            add_job(get_feeds(task),task,isTest=isTest)
            pass
    return tasks
def start_job(job_id:str=None, owner_id: str = ""):
    from .taskmsg import get_message_task
    tasks=get_message_task(job_id, owner_id=owner_id)
    if not tasks:
        logger.info("没有任务")
        return
    tag="定时采集"
    for task in tasks:
        cron_exp=task.cron_exp
        if not cron_exp:
            logger.error("任务[%s]没有设置cron表达式", task.id)
            continue

        job_id=scheduler.add_cron_job(add_job,cron_expr=cron_exp,args=[get_feeds(task),task],job_id=str(task.id),tag="定时采集")
        log_event(logger, E.TASK_SCHEDULE_ADD, task_id=str(task.id), job_id=str(job_id))
    scheduler.start()
    logger.info("启动任务")
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
