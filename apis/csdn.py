"""
apis/csdn.py — CSDN 扫码登录

参照微信公众号 GetCode() 的非阻塞模式：
  • POST /csdn/auth/qr/start   → 立即返回（fire-and-forget），后台线程启动浏览器
  • GET  /csdn/auth/qr/image   → 前端每 2s 轮询，直到 qr_image 非空
  • GET  /csdn/auth/qr/status  → 前端轮询登录状态 (starting/pending/success/timeout/cancelled)
  • POST /csdn/auth/qr/cancel  → 取消扫码
  • GET  /csdn/auth/status     → 查询 DB 授权状态
  • DELETE /csdn/auth/session  → 清除 DB 授权

技术关键：
  Playwright Sync API 无法在 asyncio loop 内调用，因此整个会话
  （打开浏览器 + 截图 + 轮询登录）运行在一个独立 daemon thread，
  该线程自带 asyncio.new_event_loop()，使用 async_playwright。
  start 接口不再等待浏览器，直接返回 status=starting，
  避免 504 超时。
"""
import asyncio
import base64
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, status

from core.auth import get_current_user
from core.csdn_auth_service import (
    get_csdn_auth,
    mark_csdn_auth_expired,
    serialize_csdn_auth,
    upsert_csdn_auth,
)
from core.db import DB
from core.events import E, log_event
from core.log import get_logger
from .base import error_response, success_response

logger = get_logger(__name__)
router = APIRouter(prefix="/csdn", tags=["CSDN认证"])

# ── 内存会话表 ────────────────────────────────────────────────────────────────
# status: "starting" | "pending" | "success" | "timeout" | "failed" | "cancelled"
_sessions: dict = {}
_sessions_lock = threading.Lock()

SESSION_TIMEOUT = 300  # 秒

_QR_SELECTORS = [
    '.qrcode-box img',
    '.login-qr img',
    '.qr-code img',
    'img[class*="qr"]',
    '[class*="qrcode"] img',
    '#qr-login-code',
]
_QR_TAB_SELECTORS = [
    'a[data-tab="qr"]',
    '.qr-tab',
    'a:has-text("扫码登录")',
    'button:has-text("扫码登录")',
    '[class*="qr-login"]',
]


# ── async 会话核心（在独立线程的 event loop 内运行） ─────────────────────────

async def _capture_qr_async(page) -> str:
    for sel in _QR_SELECTORS:
        try:
            el = await page.query_selector(sel)
            if el:
                data = await el.screenshot()
                return "data:image/png;base64," + base64.b64encode(data).decode()
        except Exception:
            pass
    try:
        data = await page.screenshot()
        return "data:image/png;base64," + base64.b64encode(data).decode()
    except Exception:
        return ""


async def _qr_session_async(owner_id: str) -> None:
    """
    完整 QR 会话：启动浏览器 → 截图 QR → 轮询登录 → 写 DB。
    在独立线程的 event loop 中运行，不阻塞 FastAPI 主 loop。
    """
    from playwright.async_api import async_playwright

    def _sd():
        return _sessions.get(owner_id)

    def _set(key, val):
        with _sessions_lock:
            sd = _sessions.get(owner_id)
            if sd:
                sd[key] = val

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox",
                      "--disable-dev-shm-usage", "--disable-gpu"],
            )
            context = await browser.new_context(
                viewport={"width": 1280, "height": 800},
                locale="zh-CN",
            )
            page = await context.new_page()

            # ── 打开 CSDN 登录页 ──
            logger.info("CSDN QR [%s]: 打开登录页", owner_id)
            await page.goto("https://passport.csdn.net/login", timeout=30000)
            await asyncio.sleep(1)

            # 切换到扫码 tab
            for sel in _QR_TAB_SELECTORS:
                try:
                    el = await page.query_selector(sel)
                    if el:
                        await el.click()
                        await asyncio.sleep(1)
                        break
                except Exception:
                    pass

            # 等待 QR 图片出现（最多 10s）
            for sel in _QR_SELECTORS:
                try:
                    await page.wait_for_selector(sel, timeout=10000)
                    logger.info("CSDN QR [%s]: QR 元素就绪 selector=%s", owner_id, sel)
                    break
                except Exception:
                    pass

            # 截图并更新会话（前端轮询到图后展示给用户）
            qr_image = await _capture_qr_async(page)
            with _sessions_lock:
                sd = _sessions.get(owner_id)
                if sd:
                    sd["status"] = "pending"
                    sd["qr_image"] = qr_image
            logger.info("CSDN QR [%s]: QR 截图完成，等待用户扫码", owner_id)

            # ── 轮询登录状态 ──
            deadline = time.time() + SESSION_TIMEOUT
            last_qr_refresh = time.time()

            while time.time() < deadline:
                with _sessions_lock:
                    cur = _sessions.get(owner_id)
                if not cur or cur.get("status") in ("cancelled", "success", "failed"):
                    break

                # 每 20s 刷新一次 QR 截图缓存
                if time.time() - last_qr_refresh > 20:
                    try:
                        new_img = await _capture_qr_async(page)
                        if new_img:
                            with _sessions_lock:
                                sd2 = _sessions.get(owner_id)
                                if sd2 and sd2.get("status") == "pending":
                                    sd2["qr_image"] = new_img
                    except Exception:
                        pass
                    last_qr_refresh = time.time()

                try:
                    url = page.url or ""
                    # 离开 passport/login 域 = 登录成功
                    if url and "csdn.net" in url and "passport" not in url and "login" not in url:
                        storage_state = await context.storage_state()

                        csdn_username = ""
                        for ck in storage_state.get("cookies", []):
                            if ck.get("name") in ("UserName", "username", "csdn_username",
                                                   "login_name", "nick_name"):
                                csdn_username = ck.get("value", "")
                                break

                        with _sessions_lock:
                            sd = _sessions.get(owner_id)
                            if sd:
                                sd["status"] = "success"
                                sd["storage_state"] = storage_state
                                sd["csdn_username"] = csdn_username

                        # 写 DB
                        try:
                            db_sess = DB.get_session()
                            upsert_csdn_auth(
                                session=db_sess,
                                owner_id=owner_id,
                                storage_state=storage_state,
                                csdn_username=csdn_username,
                                status="valid",
                            )
                            db_sess.close()
                        except Exception as e:
                            logger.error("CSDN QR [%s]: 保存 storage_state 失败: %s", owner_id, e)

                        # 站内信
                        try:
                            db_sess = DB.get_session()
                            from core.notice_service import create_notice
                            create_notice(
                                session=db_sess,
                                owner_id=owner_id,
                                title="CSDN 扫码登录成功",
                                content=f"您已成功登录 CSDN（{csdn_username or '未知用户'}），"
                                        "系统将自动使用此授权推送文章。",
                                notice_type="system",
                            )
                            db_sess.close()
                        except Exception:
                            pass

                        log_event(logger, E.CSDN_AUTH_QR_SUCCESS,
                                  owner_id=owner_id, csdn_username=csdn_username)
                        logger.info("CSDN QR [%s]: 登录成功 user=%s", owner_id, csdn_username)
                        break

                except Exception as e:
                    logger.debug("CSDN QR [%s]: 轮询异常 %s", owner_id, e)

                await asyncio.sleep(2)

            else:
                # while 正常结束 = 超时
                with _sessions_lock:
                    sd = _sessions.get(owner_id)
                    if sd and sd.get("status") == "pending":
                        sd["status"] = "timeout"
                log_event(logger, E.CSDN_AUTH_QR_TIMEOUT, owner_id=owner_id)
                logger.warning("CSDN QR [%s]: 扫码超时", owner_id)

            await browser.close()

    except Exception as e:
        logger.error("CSDN QR [%s]: 会话异常 %s", owner_id, e)
        with _sessions_lock:
            sd = _sessions.get(owner_id)
            if sd and sd.get("status") in ("starting", "pending"):
                sd["status"] = "failed"
                sd["error"] = str(e)


def _qr_session_thread(owner_id: str) -> None:
    """线程入口：创建独立 event loop，运行 async 会话。"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_qr_session_async(owner_id))
    except Exception as e:
        logger.error("CSDN QR thread [%s]: %s", owner_id, e)
    finally:
        loop.close()
        asyncio.set_event_loop(None)


# ── API 端点 ──────────────────────────────────────────────────────────────────

@router.post("/auth/qr/start", summary="启动 CSDN 扫码登录")
async def start_csdn_qr(current_user=Depends(get_current_user)):
    """
    立即返回（不阻塞），后台线程启动浏览器并更新 QR 截图。
    前端收到响应后开始轮询 GET /qr/image 直到图片就绪。
    """
    owner_id = current_user.get("username")

    # 取消旧会话
    with _sessions_lock:
        old = _sessions.get(owner_id)
        if old:
            old["status"] = "cancelled"
        # 立即写入 starting 状态，前端可立刻开始轮询
        _sessions[owner_id] = {
            "status": "starting",
            "qr_image": "",
            "storage_state": None,
            "csdn_username": "",
            "started_at": time.time(),
            "error": "",
        }

    log_event(logger, E.CSDN_AUTH_QR_GENERATE, owner_id=owner_id)

    # 后台线程，fire-and-forget
    threading.Thread(
        target=_qr_session_thread,
        args=(owner_id,),
        daemon=True,
    ).start()

    return success_response({
        "status": "starting",
        "message": "浏览器启动中，请轮询 /qr/image 获取二维码",
        "expires_in": SESSION_TIMEOUT,
    })


@router.get("/auth/qr/image", summary="获取当前 CSDN 二维码截图")
async def get_csdn_qr_image(current_user=Depends(get_current_user)):
    """
    前端每 2s 调用一次，直到 qr_image 非空后展示给用户扫码。
    status 可能为: starting（浏览器启动中）/ pending（等待扫码）/
                  success / timeout / failed / cancelled
    """
    owner_id = current_user.get("username")

    with _sessions_lock:
        sd = _sessions.get(owner_id)

    if not sd:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_response(40401, "无活跃扫码会话，请先调用 /qr/start"),
        )

    return success_response({
        "status": sd.get("status"),
        "qr_image": sd.get("qr_image", ""),
        "error": sd.get("error", ""),
    })


@router.get("/auth/qr/status", summary="查询 CSDN 扫码状态")
async def get_csdn_qr_status(current_user=Depends(get_current_user)):
    """
    轮询登录结果。
    session_status: starting / pending / success / timeout / failed / cancelled / none
    """
    owner_id = current_user.get("username")

    with _sessions_lock:
        sd = _sessions.get(owner_id)

    if sd:
        return success_response({
            "session_status": sd.get("status"),
            "csdn_username": sd.get("csdn_username", ""),
        })

    db_sess = DB.get_session()
    try:
        auth = get_csdn_auth(db_sess, owner_id)
        return success_response({
            "session_status": "none",
            "csdn_auth": serialize_csdn_auth(auth),
        })
    finally:
        try:
            db_sess.close()
        except Exception:
            pass


@router.post("/auth/qr/cancel", summary="取消 CSDN 扫码会话")
async def cancel_csdn_qr(current_user=Depends(get_current_user)):
    owner_id = current_user.get("username")
    with _sessions_lock:
        sd = _sessions.get(owner_id)
        if sd:
            sd["status"] = "cancelled"
    log_event(logger, E.CSDN_AUTH_QR_CANCEL, owner_id=owner_id)
    return success_response(message="扫码会话已取消")


@router.get("/auth/status", summary="查询 CSDN 授权状态")
async def get_csdn_auth_status(current_user=Depends(get_current_user)):
    owner_id = current_user.get("username")
    db_sess = DB.get_session()
    try:
        auth = get_csdn_auth(db_sess, owner_id)
        return success_response(serialize_csdn_auth(auth))
    finally:
        try:
            db_sess.close()
        except Exception:
            pass


@router.delete("/auth/session", summary="清除 CSDN 授权")
async def clear_csdn_auth(current_user=Depends(get_current_user)):
    owner_id = current_user.get("username")
    with _sessions_lock:
        sd = _sessions.get(owner_id)
        if sd:
            sd["status"] = "cancelled"
    db_sess = DB.get_session()
    try:
        mark_csdn_auth_expired(db_sess, owner_id)
        log_event(logger, E.CSDN_AUTH_EXPIRED, owner_id=owner_id, reason="user_clear")
        return success_response(message="CSDN 授权已清除，请重新扫码登录")
    finally:
        try:
            db_sess.close()
        except Exception:
            pass
