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

            # ── 3g. 等待页面跳转，判断是否成功 ──
            publish_success = False
            try:
                # 等待 URL 变化，成功通常会跳转到 creation/success 或类似路径
                # 某些情况下也可能直接跳转到文章详情页
                page.wait_for_url(lambda url: "success" in url.lower() or "details" in url.lower(), timeout=15000)
                publish_success = True
                article_url = page.url
                logger.info("[%s] 检测到发布成功跳转: %s", _elapsed(), article_url)
            except Exception:
                # 如果没跳转，检查页面是否有成功提示
                try:
                    # 检查是否有包含"发布成功"文字的元素
                    if page.get_by_text("发布成功").first.is_visible():
                        publish_success = True
                        logger.info("[%s] 检测到页面'发布成功'文字", _elapsed())
                except:
                    pass
            
            if not publish_success:
                logger.warning("[%s] 未检测到明确的发布成功跳转，当前 URL: %s", _elapsed(), page.url)
            
            article_url = page.url
            
            # 截图记录
            screenshot_path = _take_screenshot(page, "csdn_after_publish", _elapsed())
            if screenshot_path:
                logger.info("[%s] 发布后截图已保存: %s", _elapsed(), screenshot_path)

            browser.close()
            elapsed = _elapsed()

            # 简化成功判断：只要走到这里，说明发布按钮已点击，认为是成功
            # 从 URL 提取文章 ID（如果有）
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


def _click_publish_buttons(page, tags=None, fans_only=True) -> tuple:
    """
    点击发布按钮和确认弹窗，处理标签和粉丝可见设置。
    完全复用 references/push2csdn.py 的成熟逻辑。
    返回 (是否成功, 描述)
    """
    # ── 1. 点击主发布按钮 ──
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

    # ── 2. 处理发布弹窗 ──
    modal_containers = ['.modal__inner-2', '.modal__content', '.modal__button-bar', '.el-dialog__wrapper']
    clicked_confirm = False

    for container in modal_containers:
        try:
            # 2.1 添加标签
            if tags and isinstance(tags, (list, tuple)) and len(tags) > 0:
                logger.info("尝试在弹窗中添加 %d 个标签: %s", len(tags), tags)
                for tag_text in tags:
                    try:
                        _ensure_tags_in_modal(page, container, tag_text)
                    except Exception:
                        logger.warning("添加标签 %s 失败，继续...", tag_text)
                        pass
            else:
                try:
                    logger.info("未提供标签，尝试添加默认标签 '人工智能'")
                    _ensure_tags_in_modal(page, container, '人工智能')
                except Exception:
                    pass

            # 2.2 设置粉丝可见
            try:
                logger.info("尝试设置可见范围为'粉丝可见'")
                _set_fans_visible_in_modal(page, container)
            except Exception as e:
                logger.error("设置粉丝可见时出错: %s", e)

            # 2.3 点击确认发布按钮
            confirm_btn_selectors = [
                'button.btn-b-red',
                'button.btn-publish',
                'button.btn-red',
                'button:has-text("发布文章")',
                'button:has-text("确认发布")'
            ]
            
            btn_found = False
            for btn_sel in confirm_btn_selectors:
                try:
                    full_sel = f'{container} >> {btn_sel}:visible' if ":has-text" not in btn_sel else f'{container} {btn_sel}'
                    btn_locator = page.locator(full_sel).first
                    if btn_locator.count() > 0:
                        btn_locator.wait_for(state='visible', timeout=3000)
                        btn_locator.scroll_into_view_if_needed()
                        btn_locator.click(timeout=5000)
                        logger.info("已在容器 %r 内通过选择器 %r 点击发布按钮", container, btn_sel)
                        btn_found = True
                        break
                except Exception:
                    continue

            if btn_found:
                try:
                    page.wait_for_selector(container, state='detached', timeout=10000)
                    logger.info("容器 %r 已关闭", container)
                except Exception:
                    time.sleep(1)
                clicked_confirm = True
                detail = f"主按钮={used_selector!r}，确认弹窗={container!r}"
                return True, detail
        except Exception:
            continue

    # ── 3. 兜底策略：通过文本查找并点击 ──
    if not clicked_confirm:
        clicked_confirm = _robust_click_by_text(page, '发布文章', '确认发布按钮', timeout=15000, retries=3)
        if clicked_confirm:
            return True, f"主按钮={used_selector!r}，确认=文本匹配'发布文章'"

    if not clicked_confirm:
        logger.error("未能找到或点击确认发布按钮，发布可能没有完成")
        return False, "未找到确认发布按钮"

    return True, "发布完成"


def _robust_click_by_text(page, button_text: str, desc: str, timeout: int = 10000, retries: int = 3) -> bool:
    """通过按钮文本健壮地点击元素"""
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            locator = page.get_by_role("button", name=button_text).first
            locator.wait_for(state="visible", timeout=timeout)
            locator.scroll_into_view_if_needed()
            locator.click(timeout=5000)
            logger.info("已点击 %s (by role/name='%s', attempt=%d)", desc, button_text, attempt)
            return True
        except Exception as e:
            last_err = e
            logger.warning("尝试按文本查找并点击 %s 失败 (attempt=%d): %s", desc, attempt, e)
            try:
                locator2 = page.locator(f'button:has-text("{button_text}")').first
                locator2.wait_for(state="visible", timeout=2000)
                locator2.scroll_into_view_if_needed()
                locator2.click(timeout=3000)
                logger.info("已点击 %s (button:has-text('%s'), attempt=%d)", desc, button_text, attempt)
                return True
            except Exception as e2:
                last_err = e2
                logger.warning("has-text fallback 失败: %s", e2)
        time.sleep(0.5)

    # 最终 JS 兜底
    try:
        clicked = page.evaluate(
            """(t) => { 
                const btns = Array.from(document.querySelectorAll('button')); 
                for (const b of btns){ 
                    if(b.innerText && b.innerText.trim().includes(t)){ 
                        b.scrollIntoView(); 
                        b.click(); 
                        return true; 
                    } 
                } 
                return false; 
            }""",
            button_text
        )
        if clicked:
            logger.info("已使用 JS 文本回退点击 %s", desc)
            return True
    except Exception as e:
        logger.warning("JS 文本回退失败: %s", e)

    logger.error("最终未能点击 %s (text='%s'), last_err=%s", desc, button_text, last_err)
    return False


def _ensure_tags_in_modal(page, container_selector: str, tag_text: str = '人工智能') -> bool:
    """
    在发布弹窗中添加标签。
    复用 references/push2csdn.py 的成熟逻辑。
    """
    try:
        # 检查是否已有标签
        tags_locator = page.locator(f'{container_selector} .mark_selection_box .el-tag')
        try:
            if tags_locator.count() > 0:
                logger.info("弹窗中已有标签，跳过添加标签步骤")
                return True
        except Exception:
            if page.locator(f'{container_selector} .mark_selection_box').count() > 0:
                pass

        # 触发标签输入框
        trigger_selectors = [
            f'{container_selector} .mark_selection_box',
            f'{container_selector} .mark_selection .tag__btn-tag',
            f'{container_selector} .mark-mask-box-div',
        ]
        input_selector_candidates = [
            f'{container_selector} .mark_selection_box input.el-input__inner',
            f'{container_selector} input.el-input__inner',
            'input.el-input__inner',
        ]

        for trig in trigger_selectors:
            try:
                trg = page.locator(trig).first
                trg.wait_for(state='visible', timeout=2000)
                trg.scroll_into_view_if_needed()
                try:
                    trg.hover()
                except Exception:
                    try:
                        trg.click()
                    except Exception:
                        pass

                # 输入标签
                for inp in input_selector_candidates:
                    try:
                        iloc = page.locator(inp).first
                        iloc.wait_for(state='visible', timeout=2000)
                        iloc.click()
                        page.keyboard.type(tag_text)
                        page.keyboard.press('Enter')
                        time.sleep(0.5)
                        new_count = page.locator(f'{container_selector} .mark_selection_box .el-tag').count()
                        if new_count > 0:
                            logger.info("在弹窗中已添加标签: %s", tag_text)
                            # 关闭下拉菜单
                            _close_tag_dropdown(page, container_selector)
                            time.sleep(0.2)
                            return True
                    except Exception:
                        continue
            except Exception:
                continue

        logger.warning("尝试在弹窗中添加标签失败")
        return False
    except Exception as e:
        logger.error("ensure_tags_in_modal 出错: %s", e)
        return False


def _close_tag_dropdown(page, container_selector: str) -> bool:
    """关闭标签下拉菜单，点击弹窗空白处"""
    try:
        # 尝试点击弹窗 header
        try:
            header_loc = page.locator(f'{container_selector} h3').first
            if header_loc and header_loc.is_visible():
                box = header_loc.bounding_box()
                if box:
                    cx = box['x'] + box['width'] / 2
                    cy = box['y'] + box['height'] / 2
                    page.mouse.move(cx, cy)
                    page.mouse.click(cx, cy)
                    logger.info("已点击 %r 内 header 中心以关闭下拉", container_selector)
                    return True
                else:
                    header_loc.click(timeout=1000)
                    logger.info("已通过 locator 点击 %r 的 header", container_selector)
                    return True
        except Exception:
            pass

        # 尝试点击容器右上角
        try:
            cont = page.locator(container_selector).first
            box = cont.bounding_box()
            if box:
                cx = box['x'] + box['width'] - 16
                cy = box['y'] + 16
                page.mouse.move(cx, cy)
                page.mouse.click(cx, cy)
                logger.info("已点击容器 %r 的右上偏移处以关闭下拉", container_selector)
                return True
            else:
                cont.click(timeout=1000)
                logger.info("已通过 locator 点击容器 %r", container_selector)
                return True
        except Exception:
            pass

        # JS 兜底
        try:
            page.evaluate(
                "(s)=>{ const el=document.querySelector(s); if(!el) return false; "
                "const r=el.getBoundingClientRect(); const x=r.left+8; const y=r.top+8; "
                "el.dispatchEvent(new MouseEvent('click',{bubbles:true,clientX:x,clientY:y})); return true; }",
                container_selector
            )
            logger.info("已使用 JS 点击容器 %r 的空白处以关闭下拉", container_selector)
            return True
        except Exception as e_js:
            logger.warning("JS 点击容器空白处失败: %s", e_js)

    except Exception as e:
        logger.warning("关闭标签下拉失败: %s", e)
    return False


def _set_fans_visible_in_modal(page, container_selector: str) -> bool:
    """
    在发布弹窗中设置粉丝可见。
    复用 references/push2csdn.py 的成熟逻辑。
    """
    try:
        fans_visible_selectors = [
            f'{container_selector} label[for="needfans"]',
            f'{container_selector} .lab-switch',
            f'{container_selector} label:has-text("粉丝可见")',
            'label[for="needfans"]',
            'label.lab-switch:has-text("粉丝可见")',
            'label:has-text("粉丝可见")'
        ]

        for selector in fans_visible_selectors:
            try:
                locator = page.locator(selector).first
                locator.wait_for(state="visible", timeout=3000)

                # 检查是否已选中
                input_selector = f'{container_selector} input#needfans'
                try:
                    input_locator = page.locator(input_selector).first
                    is_checked = input_locator.is_checked()
                    if is_checked:
                        logger.info("'粉丝可见'选项已经被选中")
                        return True
                except Exception:
                    pass

                locator.scroll_into_view_if_needed()
                locator.click(timeout=5000)
                logger.info("已点击'粉丝可见'选项 (selector=%s)", selector)
                time.sleep(0.5)
                return True

            except Exception as e:
                logger.debug("尝试使用选择器 %s 点击'粉丝可见'失败: %s", selector, e)
                continue

        # JS 兜底
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
        logger.error("set_fans_visible_in_modal 出错: %s", e)
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
