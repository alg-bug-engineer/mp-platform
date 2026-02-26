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
    tags: list = None,
    fans_only: bool = True,
) -> Tuple[bool, str, bool]:
    """
    使用 Playwright storage_state 无头发布文章到 CSDN。

    Args:
        storage_state: context.storage_state() 返回的字典（含 cookies + localStorage）
        title: 文章标题
        content: Markdown 正文
        tags: 文章标签列表，默认 ["人工智能", "大模型", "AI"]
        fans_only: 是否设置为粉丝可见，默认 True

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
            use_tags = tags if tags else DEFAULT_TAGS
            logger.info("[%s] 开始点击发布按钮，标签=%s，粉丝可见=%s", _elapsed(), use_tags, fans_only)
            published, publish_detail = _click_publish_buttons(page, tags=use_tags, fans_only=fans_only)

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


def _close_tag_dropdown(page) -> bool:
    """关闭标签下拉弹窗，点击空白区域"""
    try:
        # 尝试点击弹窗标题或空白区域关闭下拉
        header_selectors = [
            '.el-dialog__header',
            '.modal__header',
            'h3',
            '.modal__title'
        ]
        for sel in header_selectors:
            try:
                header = page.locator(sel).first
                header.wait_for(state='visible', timeout=2000)
                header.click()
                time.sleep(0.3)
                return True
            except Exception:
                continue
        # 回退：按 ESC 键关闭下拉
        page.keyboard.press('Escape')
        time.sleep(0.3)
        return True
    except Exception as e:
        logger.debug("关闭标签下拉失败: %s", e)
        return False


def _click_final_publish(page, used_selector: str) -> tuple:
    """最直接的发布文章点击，多策略回退"""
    detail = ""
    
    # 策略 1: 精确匹配发布文章按钮（橙色按钮）
    try:
        # 通过 class 和文本组合定位
        btn = page.locator('button.btn-b-red:has-text("发布文章"):visible').first
        btn.wait_for(state='visible', timeout=5000)
        btn.scroll_into_view_if_needed()
        btn.click(timeout=5000)
        detail = f"主按钮={used_selector!r}，确认=橙色按钮'发布文章'"
        logger.info("点击橙色'发布文章'按钮成功")
        time.sleep(1)
        return True, detail
    except Exception as e:
        logger.debug("橙色按钮策略失败: %s", e)
    
    # 策略 2: role + name 精确匹配
    try:
        locator = page.get_by_role("button", name="发布文章", exact=True).first
        locator.wait_for(state="visible", timeout=5000)
        locator.scroll_into_view_if_needed()
        locator.click(timeout=5000)
        detail = f"主按钮={used_selector!r}，确认=role+name精确匹配"
        logger.info("精确匹配'发布文章'按钮成功")
        time.sleep(1)
        return True, detail
    except Exception as e:
        logger.debug("role+name精确匹配失败: %s", e)

    # 策略 3: 包含文本匹配
    try:
        locator = page.get_by_role("button", name=re.compile("发布文章")).first
        locator.wait_for(state="visible", timeout=5000)
        locator.scroll_into_view_if_needed()
        locator.click(timeout=5000)
        detail = f"主按钮={used_selector!r}，确认=role+正则匹配"
        logger.info("正则匹配'发布文章'按钮成功")
        time.sleep(1)
        return True, detail
    except Exception as e:
        logger.debug("正则匹配失败: %s", e)

    # 策略 4: JS 直接点击所有按钮中匹配文本的
    try:
        clicked = page.evaluate("""
            () => {
                const buttons = Array.from(document.querySelectorAll('button'));
                for (const btn of buttons) {
                    if (btn.innerText && btn.innerText.trim().includes('发布文章')) {
                        btn.scrollIntoView({ behavior: 'instant', block: 'center' });
                        btn.click();
                        return true;
                    }
                }
                return false;
            }
        """)
        if clicked:
            detail = f"主按钮={used_selector!r}，确认=JS直接点击"
            logger.info("JS直接点击'发布文章'按钮成功")
            time.sleep(1)
            return True, detail
    except Exception as e:
        logger.debug("JS点击失败: %s", e)

    return False, ""


def _click_publish_buttons(page, tags=None, fans_only=True) -> tuple:
    """点击发布按钮和确认弹窗，处理标签和粉丝可见设置，返回 (是否成功, 描述)"""
    import re
    
    publish_selectors = [
        'button.btn.btn-publish',
        'button.btn-publish',
        'button[role="button"][data-report-click]'
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

    time.sleep(1.5)  # 等待弹窗动画

    # ── 处理发布弹窗：标签、粉丝可见、确认发布 ──
    modal_containers = ['.modal__inner-2', '.modal__content', '.el-dialog__wrapper', '.modal', '.el-dialog']
    
    for container in modal_containers:
        try:
            # 检查弹窗是否存在
            modal_locator = page.locator(container).first
            modal_locator.wait_for(state="visible", timeout=5000)
            logger.debug("找到弹窗容器: %r", container)

            # 1. 添加标签（不强制，失败也继续）
            if tags and isinstance(tags, (list, tuple)) and len(tags) > 0:
                try:
                    _ensure_tags_in_modal(page, container, tags)
                    # 添加完标签后关闭下拉弹窗
                    _close_tag_dropdown(page)
                except Exception as e:
                    logger.debug("标签处理失败，继续: %s", e)

            # 2. 设置粉丝可见（不强制，失败也继续）
            if fans_only:
                try:
                    _set_fans_visible_in_modal(page, container)
                except Exception as e:
                    logger.debug("粉丝可见设置失败，继续: %s", e)

            # 3. 直接尝试点击发布文章按钮
            success, detail = _click_final_publish(page, used_selector)
            if success:
                return True, detail

        except Exception as e:
            logger.debug("弹窗容器 %r 处理失败: %s", container, e)
            continue

    # ── 最终兜底：不依赖弹窗检测，直接页面级点击 ──
    logger.info("尝试最终兜底策略：直接点击'发布文章'")
    success, detail = _click_final_publish(page, used_selector)
    if success:
        return True, detail

    screenshot_path = _take_screenshot(page, "csdn_confirm_fail", "?")
    return False, f"所有发布策略均失败，截图: {screenshot_path}"


def _ensure_tags_in_modal(page, container_selector: str, tags: list) -> bool:
    """在发布弹窗中添加标签，优先使用已存在的推荐标签"""
    try:
        # 检查是否已有足够标签（已有标签则不添加）
        tags_locator = page.locator(f'{container_selector} .mark_selection_box .el-tag')
        existing_count = tags_locator.count()
        if existing_count >= 3:
            logger.info("弹窗中已有 %d 个标签，跳过添加", existing_count)
            return True

        # 策略 1: 点击"+ 添加文章标签"按钮，然后从推荐中选择
        try:
            add_btn = page.locator(f'{container_selector} .mark_selection_box:visible').first
            add_btn.wait_for(state='visible', timeout=3000)
            add_btn.click()
            time.sleep(0.5)
            
            # 尝试从已有推荐标签中选择匹配的
            for tag_text in tags[:3]:
                try:
                    # 查找推荐标签中是否有匹配的
                    suggestion = page.locator(f'text={tag_text}').first
                    suggestion.wait_for(state='visible', timeout=2000)
                    suggestion.click()
                    time.sleep(0.3)
                except Exception:
                    # 没有匹配则输入自定义标签
                    try:
                        input_box = page.locator(f'{container_selector} input[placeholder*="标签"]:visible, {container_selector} input.el-input__inner:visible').first
                        input_box.wait_for(state='visible', timeout=2000)
                        input_box.fill(str(tag_text))
                        page.keyboard.press('Enter')
                        time.sleep(0.3)
                    except Exception:
                        continue
            logger.info("已添加标签: %s", tags[:3])
            return True
        except Exception as e:
            logger.debug("策略1添加标签失败: %s", e)

        # 策略 2: 直接在输入框中输入
        input_selectors = [
            f'{container_selector} .mark_selection_box input.el-input__inner',
            f'{container_selector} input.el-input__inner',
            'input[placeholder*="标签"]',
            'input.el-input__inner',
        ]
        
        for inp_sel in input_selectors:
            try:
                iloc = page.locator(inp_sel).first
                iloc.wait_for(state='visible', timeout=2000)
                for tag_text in tags[:3]:
                    iloc.click()
                    iloc.fill(str(tag_text))
                    page.keyboard.press('Enter')
                    time.sleep(0.3)
                logger.info("已添加标签(策略2): %s", tags[:3])
                return True
            except Exception:
                continue

        logger.warning("尝试在弹窗中添加标签失败")
        return False
    except Exception as e:
        logger.error("添加标签出错: %s", e)
        return False


def _set_fans_visible_in_modal(page, container_selector: str) -> bool:
    """在发布弹窗中设置粉丝可见"""
    try:
        # 查找粉丝可见选项
        fans_selectors = [
            f'{container_selector} label[for="needfans"]',
            f'{container_selector} .lab-switch',
            f'{container_selector} label:has-text("粉丝可见")',
            'label[for="needfans"]',
            'label.lab-switch:has-text("粉丝可见")',
            'label:has-text("粉丝可见")'
        ]

        for selector in fans_selectors:
            try:
                locator = page.locator(selector).first
                locator.wait_for(state="visible", timeout=3000)

                # 检查是否已选中
                input_selector = f'{container_selector} input#needfans'
                try:
                    input_locator = page.locator(input_selector).first
                    if input_locator.is_checked():
                        logger.info("'粉丝可见'选项已经被选中")
                        return True
                except Exception:
                    pass

                locator.scroll_into_view_if_needed()
                locator.click(timeout=5000)
                logger.info("已点击'粉丝可见'选项")
                time.sleep(0.5)
                return True
            except Exception as e:
                logger.debug("粉丝可见选择器 %r 失败: %s", selector, e)
                continue

        # JS 回退方式
        try:
            js_result = page.evaluate("""
                () => {
                    const labels = Array.from(document.querySelectorAll('label'));
                    for (const label of labels) {
                        if (label.textContent && label.textContent.includes('粉丝可见')) {
                            const forAttr = label.getAttribute('for');
                            if (forAttr) {
                                const input = document.getElementById(forAttr);
                                if (input && input.type === 'checkbox' && !input.checked) {
                                    label.scrollIntoView();
                                    label.click();
                                    return true;
                                } else if (input && input.checked) {
                                    return 'already_checked';
                                }
                            }
                            label.scrollIntoView();
                            label.click();
                            return true;
                        }
                    }
                    return false;
                }
            """)
            if js_result == True:
                logger.info("已使用JS方式点击'粉丝可见'选项")
                return True
            elif js_result == 'already_checked':
                logger.info("'粉丝可见'选项已经被选中")
                return True
        except Exception as e:
            logger.warning("JS方式点击'粉丝可见'失败: %s", e)

        logger.warning("未能找到或点击'粉丝可见'选项")
        return False
    except Exception as e:
        logger.error("设置粉丝可见出错: %s", e)
        return False


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
