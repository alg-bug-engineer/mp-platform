"""
csdn_publish.py

使用 Playwright storage_state（扫码登录后保存的浏览器状态）无头发布到 CSDN。
storage_state 由 apis/csdn.py 扫码流程写入 DB，比 cookie 方式更稳定。
"""
import time
import traceback
from typing import Tuple

from core.log import get_logger
from core.events import log_event, E

logger = get_logger(__name__)

EDITOR_URL = "https://editor.csdn.net/md/?not_checkout=1&spm=1000.2115.3001.5352"
DEFAULT_TAGS = ["人工智能", "大模型", "AI"]


def push_to_csdn(
    storage_state: dict,
    title: str,
    content: str,
) -> Tuple[bool, str, bool]:
    """
    使用 Playwright storage_state 无头发布文章到 CSDN。

    Args:
        storage_state: context.storage_state() 返回的字典（含 cookies + localStorage）
        title: 文章标题
        content: Markdown 正文

    Returns:
        (success, message, needs_reauth)
        - success: 是否发布成功
        - message: 成功时含文章 URL；失败时含错误描述
        - needs_reauth: True 表示登录态已失效，需要重新扫码
    """
    t0 = time.time()

    def _elapsed() -> str:
        return f"{time.time() - t0:.1f}s"

    logger.info("=" * 60)
    log_event(logger, E.CSDN_PUSH_START, title=title[:60], content_len=len(content))

    # ── 1. 校验入参 ──
    if not storage_state or not isinstance(storage_state, dict):
        msg = "storage_state 为空或格式错误，请先扫码登录 CSDN"
        logger.error("%s", msg)
        return False, msg, True

    # ── 2. 导入 Playwright ──
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        msg = "Playwright 未安装，请执行 pip install playwright && playwright install chromium"
        logger.error("依赖缺失: %s", msg)
        return False, msg, False

    # ── 3. 启动浏览器，恢复 storage_state ──
    try:
        with sync_playwright() as p:
            log_event(logger, E.CSDN_PUSH_BROWSER_LAUNCH, elapsed=_elapsed())
            browser = p.chromium.launch(headless=True)
            # 直接用 storage_state 恢复会话，无需手动注入 cookies
            context = browser.new_context(storage_state=storage_state)
            page = context.new_page()

            # ── 3a. 打开编辑器页面 ──
            logger.info("[%s] 正在打开编辑器: %s", _elapsed(), EDITOR_URL)
            try:
                page.goto(EDITOR_URL, timeout=60000)
            except Exception as e:
                _take_screenshot(page, "csdn_goto_fail", _elapsed())
                browser.close()
                msg = f"打开编辑页面失败: {e}"
                logger.error("[%s] %s", _elapsed(), msg)
                return False, msg, False

            current_url = page.url
            logger.info("[%s] 页面跳转后 URL: %s", _elapsed(), current_url)

            # 判断是否被重定向到登录页 → 需要重新扫码
            if "login" in current_url or "passport" in current_url:
                _take_screenshot(page, "csdn_login_redirect", _elapsed())
                browser.close()
                msg = "CSDN 登录态已失效（被重定向到登录页），请重新扫码登录"
                log_event(logger, E.CSDN_PUSH_NEED_REAUTH, elapsed=_elapsed(), url=current_url)
                return False, msg, True

            # ── 3b. 等待编辑器就绪 ──
            editor_selector = 'pre.editor__inner.markdown-highlighting[contenteditable="true"]'
            logger.info("[%s] 等待编辑器元素: %r", _elapsed(), editor_selector)
            try:
                page.wait_for_selector(editor_selector, timeout=20000)
                log_event(logger, E.CSDN_PUSH_EDITOR_READY, elapsed=_elapsed())
            except Exception:
                current_url = page.url
                _take_screenshot(page, "csdn_editor_timeout", _elapsed())
                browser.close()
                if "login" in current_url or "passport" in current_url:
                    msg = "CSDN 登录态已失效（等待编辑器时被重定向），请重新扫码登录"
                    return False, msg, True
                msg = f"编辑器加载超时（20s），当前 URL: {current_url}"
                logger.warning("[%s] %s", _elapsed(), msg)
                return False, msg, False

            # ── 3c. 填充标题 ──
            logger.info("[%s] 开始填充标题: %r", _elapsed(), title[:60])
            title_ok = _fill_title(page, str(title or "")[:100])
            logger.info("[%s] 标题填充%s", _elapsed(), "成功" if title_ok else "失败（未找到标题输入框）")

            # ── 3d. 填充正文 ──
            logger.info("[%s] 开始填充正文（%d 字符）", _elapsed(), len(content))
            fill_ok, fill_method = _fill_editor_with_markdown(page, str(content or ""))
            if not fill_ok:
                _take_screenshot(page, "csdn_fill_fail", _elapsed())
                browser.close()
                msg = "正文填充失败，未找到可用编辑器选择器"
                logger.error("[%s] %s", _elapsed(), msg)
                return False, msg, False
            log_event(logger, E.CSDN_PUSH_CONTENT_FILL, elapsed=_elapsed(), method=fill_method)

            # ── 3e. 验证编辑器内容 ──
            actual_len = _verify_editor_content(page)
            log_event(logger, E.CSDN_PUSH_CONTENT_VERIFY, elapsed=_elapsed(),
                      expected=len(content), actual=actual_len)
            if actual_len < max(10, len(content) // 10):
                _take_screenshot(page, "csdn_content_mismatch", _elapsed())
                browser.close()
                msg = (
                    f"正文写入验证失败：期望 {len(content)} 字符，"
                    f"编辑器实际读回 {actual_len} 字符。"
                    f"CSDN 编辑器可能已更新，请排查选择器兼容性。"
                )
                logger.error("[%s] %s", _elapsed(), msg)
                return False, msg, False

            time.sleep(2)

            # ── 3f. 点击发布按钮 ──
            logger.info("[%s] 开始点击发布按钮", _elapsed())
            published, publish_detail = _click_publish_buttons(page)

            if not published:
                screenshot_path = _take_screenshot(page, "csdn_publish_fail", _elapsed())
                browser.close()
                msg = f"发布流程未完成: {publish_detail}"
                if screenshot_path:
                    msg += f"  截图: {screenshot_path}"
                logger.error("[%s] %s", _elapsed(), msg)
                return False, msg, False

            log_event(logger, E.CSDN_PUSH_PUBLISH_CLICK, elapsed=_elapsed(), detail=publish_detail[:120])

            # ── 3g. 等待页面跳转，获取文章 URL ──
            # CSDN 发布后有两种成功跳转：
            #   1. https://blog.csdn.net/<user>/article/details/<id>  (直接发布)
            #   2. https://mp.csdn.net/mp_blog/creation/success/<id>  (审核中)
            article_url = ""
            url_confirmed = False
            try:
                page.wait_for_url(
                    lambda u: (
                        ("blog.csdn.net" in u and "article/details" in u)
                        or "creation/success" in u
                    ),
                    timeout=15000,
                )
                article_url = page.url
                url_confirmed = True
                logger.info("[%s] 发布后成功跳转: %s", _elapsed(), article_url)
            except Exception:
                article_url = page.url
                logger.warning(
                    "[%s] 发布后 URL 未匹配成功模式，当前 URL: %s",
                    _elapsed(), article_url,
                )

            screenshot_path = _take_screenshot(page, "csdn_after_publish", _elapsed())
            if screenshot_path:
                logger.info("[%s] 发布后截图已保存: %s", _elapsed(), screenshot_path)

            page_title = ""
            page_error = ""
            try:
                page_title = page.title()
                logger.info("[%s] 发布后页面标题: %r", _elapsed(), page_title)
            except Exception:
                pass

            # 页面标题包含"发布成功"也视为成功（兜底）
            if not url_confirmed and "发布成功" in page_title:
                url_confirmed = True
                logger.info("[%s] 通过页面标题确认发布成功", _elapsed())

            try:
                err_el = page.query_selector(".el-message--error, .error-tip, [class*='error']")
                if err_el:
                    page_error = (err_el.inner_text() or "").strip()[:200]
                    logger.warning("[%s] 页面错误提示: %r", _elapsed(), page_error)
            except Exception:
                pass

            browser.close()
            elapsed = _elapsed()

            if url_confirmed:
                # 从 creation/success/<id> 提取文章 ID 以构造直链（可选）
                article_id = ""
                if "creation/success/" in article_url:
                    article_id = article_url.rstrip("/").rsplit("/", 1)[-1]
                display_url = article_url if not article_id else (
                    f"{article_url}  （文章ID: {article_id}，审核通过后可在 CSDN 主页查看）"
                )
                msg = f"CSDN 推送成功（{elapsed}）：{display_url}"
                log_event(logger, E.CSDN_PUSH_COMPLETE, elapsed=elapsed, url=article_url)
                logger.info("=" * 60)
                return True, msg, False
            else:
                hint = "请登录 CSDN 检查草稿箱或审核状态"
                if page_error:
                    hint = f"页面错误: {page_error}"
                msg = (
                    f"CSDN 操作已执行但未确认发布（{elapsed}）："
                    f"跳转后 URL={article_url}，{hint}。"
                    f"截图: {screenshot_path}"
                )
                log_event(logger, E.CSDN_PUSH_FAIL, elapsed=elapsed, url=article_url, reason=hint[:200])
                logger.info("=" * 60)
                return False, msg, False

    except Exception as e:
        tb = traceback.format_exc()
        msg = f"推送异常: {e}"
        log_event(logger, E.CSDN_PUSH_FAIL, elapsed=_elapsed(), reason=str(e)[:200])
        logger.error("[%s] %s\n%s", _elapsed(), msg, tb)
        return False, msg, False


def _fill_title(page, title: str) -> bool:
    title_selectors = [
        'input[placeholder*="标题"]',
        'input[placeholder*="文章标题"]',
        'input.title',
        'input#title',
        'input[name="title"]',
    ]
    for sel in title_selectors:
        el = page.query_selector(sel)
        if el:
            try:
                el.fill(title)
                logger.debug("标题选择器命中: %r", sel)
                return True
            except Exception as e:
                logger.debug("标题选择器 %r fill 失败: %s", sel, e)
                continue
    logger.warning("所有标题选择器均未命中: %s", title_selectors)
    return False


def _fill_editor_with_markdown(page, md: str) -> tuple:
    """填充 Markdown 正文，返回 (是否成功, 使用的方式描述)"""
    # 方式 1：CodeMirror JS API
    try:
        got = page.evaluate("""(text) => {
            try {
                const cm = document.querySelector('.CodeMirror');
                if (cm && cm.CodeMirror) { cm.CodeMirror.setValue(text); return true; }
            } catch(e) {}
            return false;
        }""", md)
        if got:
            logger.debug("正文填充方式: CodeMirror JS API")
            return True, "CodeMirror JS API"
    except Exception as e:
        logger.debug("CodeMirror JS API 尝试失败: %s", e)

    # 方式 2：contenteditable 选择器
    selectors = [
        'pre.editor__inner.markdown-highlighting[contenteditable="true"]',
        'pre.editor__inner[contenteditable="true"]',
        'div[contenteditable="true"]',
    ]
    for sel in selectors:
        try:
            el = page.query_selector(sel)
            if not el:
                logger.debug("编辑器选择器未找到元素: %r", sel)
                continue
            page.eval_on_selector(sel, """(el, value) => {
                el.focus();
                try { el.textContent = value; } catch(e) {}
                el.dispatchEvent(new Event('input', { bubbles: true }));
            }""", md)
            logger.debug("正文填充方式: contenteditable 选择器 %r", sel)
            return True, f"contenteditable selector={sel!r}"
        except Exception as e:
            logger.debug("编辑器选择器 %r 失败: %s", sel, e)
            continue

    return False, "无可用选择器"


def _verify_editor_content(page) -> int:
    """读回编辑器中当前内容的字符数，用于验证写入是否生效。返回 -1 表示无法读取。"""
    try:
        length = page.evaluate("""() => {
            const cm = document.querySelector('.CodeMirror');
            if (cm && cm.CodeMirror) return cm.CodeMirror.getValue().length;
            const ce = document.querySelector(
                'pre.editor__inner[contenteditable="true"], div[contenteditable="true"]'
            );
            if (ce) return (ce.textContent || '').length;
            return -1;
        }""")
        return int(length or 0)
    except Exception as e:
        logger.debug("编辑器内容验证失败: %s", e)
        return -1


def _click_publish_buttons(page) -> tuple:
    """点击发布按钮和确认弹窗，返回 (是否成功, 描述)"""
    publish_selectors = [
        'button.btn.btn-publish',
        'button.btn-publish',
    ]
    clicked_publish = False
    used_selector = ""
    for sel in publish_selectors:
        try:
            locator = page.locator(sel).first
            locator.wait_for(state="visible", timeout=15000)
            locator.click(timeout=5000)
            clicked_publish = True
            used_selector = sel
            logger.info("发布按钮点击成功，选择器: %r", sel)
            break
        except Exception as e:
            logger.debug("发布按钮选择器 %r 失败: %s", sel, e)
            continue

    if not clicked_publish:
        return False, f"未找到发布按钮，尝试了: {publish_selectors}"

    time.sleep(1)

    modal_containers = ['.modal__inner-2', '.modal__content', '.modal__button-bar', '.el-dialog__wrapper']
    for container in modal_containers:
        try:
            btn = page.locator(f'{container} >> button.btn-b-red:visible').first
            btn.wait_for(state='visible', timeout=5000)
            btn.click(timeout=5000)
            time.sleep(1)
            detail = f"一次发布按钮={used_selector!r}，确认弹窗={container!r}"
            logger.info("确认弹窗点击成功，容器: %r", container)
            return True, detail
        except Exception as e:
            logger.debug("确认弹窗容器 %r 失败: %s", container, e)
            continue

    try:
        locator = page.get_by_role("button", name="发布文章").first
        locator.wait_for(state="visible", timeout=10000)
        locator.click(timeout=5000)
        detail = f"一次发布按钮={used_selector!r}，确认按钮=role[button][name=发布文章]"
        logger.info("确认按钮（回退文本匹配）点击成功")
        return True, detail
    except Exception as e:
        logger.warning("确认弹窗所有方式均失败（最后错误: %s）", e)

    screenshot_path = _take_screenshot(page, "csdn_confirm_fail", "?")
    return False, f"未找到确认弹窗按钮（一次发布按钮={used_selector!r}），截图: {screenshot_path}"


def _take_screenshot(page, tag: str, elapsed: str) -> str:
    """截图保存到项目 logs/screenshots/ 目录，返回路径或空字符串。"""
    try:
        import os
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        screenshots_dir = os.path.join(base, "logs", "screenshots")
        os.makedirs(screenshots_dir, exist_ok=True)
        path = os.path.join(screenshots_dir, f"{tag}_{int(time.time())}.png")
        page.screenshot(path=path, full_page=False)
        logger.info("[%s] 截图已保存: %s", elapsed, path)
        return path
    except Exception as e:
        logger.debug("截图失败: %s", e)
        return ""
