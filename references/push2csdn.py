#!/usr/bin/env python3
"""
push2csdn.py

基于 Playwright 的自动化脚本：将本地 Markdown 文件发布到 CSDN 编辑器页面。

支持 YAML Front Matter (--- ... ---) 提取 title 和 tags。
如果 Front Matter 不存在或缺少字段，则回退到解析 ```toc``` 代码块。

注意：脚本不会替你登录。脚本会打开编辑页面并等待你在浏览器中完成登录（默认 2 分钟），登录后会自动填充标题与正文并触发发布。

用法示例:
  python3 push2csdn.py

建议先执行:
  pip install -r requirements.txt
"""
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError, Error as PlaywrightError
import pyperclip
import argparse
import sys
import time
import json
from datetime import datetime
from pathlib import Path
import frontmatter
import re
import random
import logging

# ========== 初始化 ==========
logger = logging.getLogger(__name__)

EDITOR_URL = "https://editor.csdn.net/md/?not_checkout=1&spm=1000.2115.3001.5352"
STATE_FILE = STATE_DIR / "csdn_state.json"
PUBLISH_LOG_FILE = LOGS_DIR / "publish_log.json"
DEFAULT_TAGS = ["人工智能", "大模型", "AI"]


def read_markdown(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Markdown file not found: {path}")
    return path.read_text(encoding="utf-8")


def load_publish_log() -> dict:
    if not PUBLISH_LOG_FILE.exists():
        return {}
    try:
        data = json.loads(PUBLISH_LOG_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    data.pop("__meta__", None)
    return data


def save_publish_log(log: dict) -> None:
    payload = {"__meta__": {"updated_at": datetime.now().isoformat()}}
    payload.update(log)
    PUBLISH_LOG_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def fill_title(page, title: str) -> bool:
    """尝试多个可能的标题选择器，返回是否成功填充"""
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
                logger.info(f"已填充标题 (selector={sel})")
                return True
            except Exception:
                continue
    logger.warning("未找到标题输入框，跳过标题填充（你可以在打开页面后手动填写）")
    return False


def fill_editor_with_markdown(page, md: str) -> bool:
    """向内容可编辑区域写入 markdown 文本。返回是否成功。"""
    selectors = [
        'pre.editor__inner.markdown-highlighting[contenteditable="true"]',
        'pre.editor__inner[contenteditable="true"]',
        'div[contenteditable="true"]',
    ]
    try:
        got = page.evaluate("(text) => {\n            try{\n                const cm = document.querySelector('.CodeMirror');\n                if(cm && cm.CodeMirror){ cm.CodeMirror.setValue(text); return true; }\n                if(window.CodeMirror && window.CodeMirror.runMode){ /* best effort */ }\n                if(window.monaco && window.monaco.editor){ try{ const eds = window.monaco.editor.getModels(); if(eds && eds[0]){ const editors = window.monaco.editor.getEditors ? window.monaco.editor.getEditors() : null; if(editors && editors[0]){ editors[0].setValue(text); return true; } } }catch(e){} }\n            }catch(e){}\n            return false;\n        }", md)
        if got:
            logger.info("已通过编辑器 API 写入内容")
            return True
    except Exception:
        pass

    for sel in selectors:
        try:
            el = page.query_selector(sel)
            if not el:
                continue
            try:
                page.eval_on_selector(sel, '(el, value) => { el.focus(); try{ el.textContent = value; }catch(e){}; try{ const dt = new DataTransfer(); dt.setData("text/plain", value); const evt = new ClipboardEvent("paste", { clipboardData: dt, bubbles: true }); el.dispatchEvent(evt); }catch(e){}; el.dispatchEvent(new Event("input", { bubbles: true })); }', md)
                logger.info(f"已在编辑器中写入内容 (selector={sel})")
                return True
            except Exception as e:
                logger.warning(f"通过 JS 写入选择器 {sel} 失败: {e}")
                continue
        except Exception as e:
            logger.warning(f"尝试使用选择器 {sel} 写入失败: {e}")
            continue

    logger.warning("未找到可写入的编辑器元素，请检查页面是否已正确加载并已登录")

    try:
        pyperclip.copy(md)
    except Exception as e:
        logger.error(f"将内容复制到系统剪贴板失败: {e}")
        return False

    paste_selectors = [
        'div.editor div.cledit-section',
        'div.cledit-section',
        'pre.editor__inner.markdown-highlighting[contenteditable="true"]',
        'div[contenteditable="true"]',
    ]
    for sel in paste_selectors:
        try:
            locator = page.locator(sel).first
            locator.wait_for(state="visible", timeout=5000)
            locator.click()
            mod = 'Meta' if sys.platform == 'darwin' else 'Control'
            page.keyboard.press(f"{mod}+v")
            time.sleep(0.5)
            logger.info(f"已通过剪贴板粘贴到编辑器 (selector={sel})")
            return True
        except Exception as e:
            logger.warning(f"尝试通过剪贴板粘贴到选择器 {sel} 失败: {e}")
            continue

    logger.error("尝试剪贴板粘贴也失败，可能需要手动粘贴或进一步调整选择器")
    return False


def click_publish_buttons(page, tags=None) -> bool:
    """点击发布按钮并在弹出的确认框中点击最终发布按钮。返回是否成功。"""
    def robust_click(selector, desc, timeout=10000, retries=2):
        locator = page.locator(selector).first
        try:
            locator.wait_for(state="visible", timeout=timeout)
        except PlaywrightTimeoutError:
            logger.warning(f"等待元素可见超时: {selector} ({desc})")
            return False

        last_err = None
        for attempt in range(1, retries + 1):
            try:
                locator.scroll_into_view_if_needed()
                locator.click(timeout=5000)
                logger.info(f"已点击 {desc} (selector={selector}, attempt={attempt})")
                return True
            except PlaywrightError as e:
                last_err = e
                logger.warning(f"尝试点击 {desc} 失败 (attempt={attempt}): {e}")
                try:
                    locator.click(force=True, timeout=3000)
                    logger.info(f"已强制点击 {desc} (selector={selector}, attempt={attempt})")
                    return True
                except PlaywrightError as e2:
                    last_err = e2
                    logger.warning(f"强制点击也失败: {e2}")
                    time.sleep(0.5)

        try:
            page.evaluate("(s) => { const el = document.querySelector(s); if(el){ el.scrollIntoView(); el.click(); return true;} return false; }", selector)
            logger.info(f"已使用 JS fallback 点击 {desc} (selector={selector})")
            return True
        except Exception as e:
            logger.error(f"JS fallback 点击 {desc} 失败: {e} (last_err={last_err})")
            return False

    publish_selectors = [
        'button.btn.btn-publish',
        'button.btn-publish',
        'button[role="button"][data-report-click]'
    ]
    clicked = False
    for sel in publish_selectors:
        if robust_click(sel, '主发布按钮', timeout=20000, retries=3):
            clicked = True
            break

    if not clicked:
        logger.error("未能找到或点击主发布按钮，可能页面结构已变化或元素被遮挡")
        return False

    time.sleep(0.5)

    def robust_click_by_text(button_text, desc, timeout=10000, retries=3):
        last_err = None
        for attempt in range(1, retries + 1):
            try:
                locator = page.get_by_role("button", name=button_text).first
                locator.wait_for(state="visible", timeout=timeout)
                locator.scroll_into_view_if_needed()
                locator.click(timeout=5000)
                logger.info(f"已点击 {desc} (by role/name='{button_text}', attempt={attempt})")
                return True
            except Exception as e:
                last_err = e
                logger.warning(f"尝试按文本查找并点击 {desc} 失败 (attempt={attempt}): {e}")
                try:
                    locator2 = page.locator(f'button:has-text("{button_text}")').first
                    locator2.wait_for(state="visible", timeout=2000)
                    locator2.scroll_into_view_if_needed()
                    locator2.click(timeout=3000)
                    logger.info(f"已点击 {desc} (button:has-text('{button_text}'), attempt={attempt})")
                    return True
                except Exception as e2:
                    last_err = e2
                    logger.warning(f"has-text fallback 失败: {e2}")

            time.sleep(0.5)

        modal_containers = ['.modal__button-bar', '.modal', '.el-dialog__footer', '.dialog-footer']
        for container in modal_containers:
            try:
                locator3 = page.locator(f'{container} >> button:has-text("{button_text}")').first
                locator3.wait_for(state="visible", timeout=3000)
                locator3.scroll_into_view_if_needed()
                locator3.click()
                logger.info(f"已在容器 {container} 中点击 {desc} (text='{button_text}')")
                return True
            except Exception as e:
                last_err = e

        try:
            clicked = page.evaluate("(t) => { const btns = Array.from(document.querySelectorAll('button')); for (const b of btns){ if(b.innerText && b.innerText.trim().includes(t)){ b.scrollIntoView(); b.click(); return true; } } return false; }", button_text)
            if clicked:
                logger.info(f"已使用 JS 文本回退点击 {desc} (text='{button_text}')")
                return True
        except Exception as e:
            last_err = e
            logger.warning(f"JS 文本回退出错: {e}")

        logger.error(f"最终未能点击 {desc} (text='{button_text}'), last_err={last_err}")
        return False

    modal_containers = ['.modal__inner-2', '.modal__content', '.modal__button-bar', '.el-dialog__wrapper']
    clicked_confirm = False

    def ensure_tags_in_modal(page, container_selector, tag_text='人工智能'):
        try:
            tags_locator = page.locator(f'{container_selector} .mark_selection_box .el-tag')
            try:
                if tags_locator.count() > 0:
                    logger.info("弹窗中已有标签，跳过添加标签步骤")
                    return True
            except Exception:
                if page.locator(f'{container_selector} .mark_selection_box').count() > 0:
                    pass

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
                                logger.info(f"在弹窗中已添加标签: {tag_text}")
                                try:
                                    try:
                                        header_loc = page.locator(f'{container_selector} h3').first
                                        if header_loc and header_loc.is_visible():
                                            box = header_loc.bounding_box()
                                            if box:
                                                cx = box['x'] + box['width'] / 2
                                                cy = box['y'] + box['height'] / 2
                                                page.mouse.move(cx, cy)
                                                page.mouse.click(cx, cy)
                                                logger.info(f"已点击 {container_selector} 内 header 中心以关闭下拉")
                                            else:
                                                header_loc.click(timeout=1000)
                                                logger.info(f"已通过 locator 点击 {container_selector} 的 header")
                                        else:
                                            raise Exception('header not visible')
                                    except Exception:
                                        try:
                                            cont = page.locator(container_selector).first
                                            box = cont.bounding_box()
                                            if box:
                                                cx = box['x'] + box['width'] - 16
                                                cy = box['y'] + 16
                                                page.mouse.move(cx, cy)
                                                page.mouse.click(cx, cy)
                                                logger.info(f"已点击容器 {container_selector} 的右上偏移处以关闭下拉")
                                            else:
                                                cont.click(timeout=1000)
                                                logger.info(f"已通过 locator 点击容器 {container_selector}")
                                        except Exception:
                                            try:
                                                page.evaluate("(s)=>{ const el=document.querySelector(s); if(!el) return false; const r=el.getBoundingClientRect(); const x=r.left+8; const y=r.top+8; el.dispatchEvent(new MouseEvent('click',{bubbles:true,clientX:x,clientY:y})); return true; }", container_selector)
                                                logger.info(f"已使用 JS 点击容器 {container_selector} 的空白处以关闭下拉")
                                            except Exception as e_js:
                                                logger.warning(f"JS 点击容器空白处失败: {e_js}")
                                except Exception as e:
                                    logger.warning(f"点击弹窗空白区域失败: {e}")

                                time.sleep(0.2)
                                return True
                        except Exception:
                            continue
                except Exception:
                    continue

            logger.warning("尝试在弹窗中添加标签失败")
            return False
        except Exception as e:
            logger.error(f"ensure_tags_in_modal 出错: {e}")
            return False

    def set_fans_visible_in_modal(page, container_selector):
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
                    logger.info(f"已点击'粉丝可见'选项 (selector={selector})")
                    
                    time.sleep(0.5)
                    return True
                    
                except Exception as e:
                    logger.warning(f"尝试使用选择器 {selector} 点击'粉丝可见'失败: {e}")
                    continue
            
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
                logger.warning(f"JS方式点击'粉丝可见'失败: {e}")
            
            logger.warning("未能找到或点击'粉丝可见'选项")
            return False
            
        except Exception as e:
            logger.error(f"set_fans_visible_in_modal 出错: {e}")
            return False
            
    for container in modal_containers:
        try:
            try:
                if tags and isinstance(tags, (list, tuple)) and len(tags) > 0:
                    logger.info(f"尝试在弹窗中添加 {len(tags)} 个标签: {tags}")
                    for t in tags:
                        try:
                            ensure_tags_in_modal(page, container_selector=container, tag_text=t)
                        except Exception:
                            logger.warning(f"添加标签 {t} 失败，继续...")
                            pass
                else:
                    try:
                        logger.info("未提供标签，尝试添加默认标签 '人工智能'")
                        ensure_tags_in_modal(page, container_selector=container, tag_text='人工智能')
                    except Exception:
                        pass
            except Exception as e_tag:
                logger.error(f"添加标签时出错: {e_tag}")

            try:
                logger.info("尝试设置可见范围为'粉丝可见'")
                set_fans_visible_in_modal(page, container_selector=container)
            except Exception as e_visible:
                logger.error(f"设置粉丝可见时出错: {e_visible}")

            btn_locator = page.locator(f'{container} >> button.btn-b-red:visible').first
            if btn_locator:
                try:
                    btn_locator.wait_for(state='visible', timeout=5000)
                    btn_locator.scroll_into_view_if_needed()
                    btn_locator.click(timeout=5000)
                    logger.info(f"已在容器 {container} 内点击发布按钮")
                    try:
                        page.wait_for_selector(container, state='detached', timeout=10000)
                        logger.info(f"容器 {container} 已关闭")
                    except Exception:
                        time.sleep(1)
                    clicked_confirm = True
                    break
                except Exception as e:
                    logger.warning(f"在容器 {container} 内点击发布失败: {e}")
        except Exception:
            continue

    if not clicked_confirm:
        clicked_confirm = robust_click_by_text('发布文章', '确认发布按钮', timeout=15000, retries=3)

    if not clicked_confirm:
        logger.error("未能找到或点击确认发布按钮，发布可能没有完成。请手动检查页面。")
        return False

    return True


def main():
    parser = argparse.ArgumentParser(description="将 history 目录下的今日 Markdown 文件发布到 CSDN。")
    parser.add_argument("--headless", default="false", choices=["true", "false"], help="是否无头模式，默认 false（显示浏览器以便登录）")
    parser.add_argument("--login-timeout", type=int, default=120, help="等待登录时间（秒），默认 120 秒")
    parser.add_argument("--skip-publish", action='store_true', help="只填充标题与正文但不触发发布（调试用）")
    parser.add_argument("--only", nargs="+", help="只处理指定的 history 文件名或路径（支持多个）")
    parser.add_argument("--history-dir", type=str, default=None, help="history 目录（默认使用 constants.HISTORY_DIR）")
    args = parser.parse_args()

    history_dir = Path(args.history_dir).expanduser().resolve() if args.history_dir else HISTORY_DIR

    if not history_dir.exists() or not history_dir.is_dir():
        logger.error(f"未找到 history 目录: {history_dir}")
        sys.exit(2)

    today_str = datetime.now().strftime("%Y%m%d")
    if args.only:
        files_to_process = []
        for item in args.only:
            fp = Path(item)
            if not fp.is_absolute():
                fp = history_dir / item
            if fp.exists() and fp.is_file():
                files_to_process.append(fp)
            else:
                logger.warning(f"指定的 history 文件不存在: {fp}")
    else:
        files_to_process = [p for p in sorted(history_dir.glob(f'{today_str}_*.md'))]

    if not files_to_process:
        logger.info(f"history 目录下未找到任何可处理的 .md 文件，退出")
        sys.exit(0)

    publish_log = load_publish_log()
    headless = True if args.headless.lower() == "true" else False
    storage_file = STATE_FILE

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)

        cookies = get_browser_cookies(".csdn.net")
        if cookies:
            logger.info("从浏览器获取到 Cookie，尝试使用 Cookie 登录")
            context = browser.new_context(storage_state=None)
            context.add_cookies(cookies)
            page = context.new_page()
            logger.info(f"打开编辑页面：{EDITOR_URL}")
            page.goto(EDITOR_URL, timeout=60000)
            try:
                editor_selector = 'pre.editor__inner.markdown-highlighting[contenteditable="true"]'
                page.wait_for_selector(editor_selector, timeout=15000)
                logger.info("使用 Cookie 登录成功")
                context.storage_state(path=str(storage_file))
                logger.info(f"已保存 login storage 到: {storage_file}")
            except PlaywrightTimeoutError:
                logger.warning("使用 Cookie 未能自动登录，请手动操作")

        elif storage_file.exists():
            logger.info(f"加载 storage state: {storage_file}")
            context = browser.new_context(storage_state=str(storage_file))
            page = context.new_page()
        else:
            context = browser.new_context()
            page = context.new_page()

        logger.info(f"打开编辑页面：{EDITOR_URL}")
        page.goto(EDITOR_URL, timeout=60000)

        if not storage_file.exists() and not cookies:
            logger.info(f"等待最多 {args.login_timeout} 秒以完成登录并加载编辑器...")
            try:
                editor_selector = 'pre.editor__inner.markdown-highlighting[contenteditable="true"]'
                page.wait_for_selector(editor_selector, timeout=args.login_timeout * 1000)
                try:
                    context.storage_state(path=str(storage_file))
                    logger.info(f"已保存 login storage 到: {storage_file}")
                except Exception as e:
                    logger.error(f"保存 storage_state 失败: {e}")
            except PlaywrightTimeoutError:
                logger.warning("等待编辑器元素超时，尝试继续（可能需要你手动登录或手动打开编辑器）")
        
        for idx, fp in enumerate(files_to_process, start=1):
            if publish_log.get(fp.name, {}).get("csdn", {}).get("published"):
                logger.info(f"跳过已在 CSDN 发布过的: {fp.name}")
                continue

            logger.info(f"===== 处理 {idx}/{len(files_to_process)}: {fp} =====")
            try:
                full_md_text = read_markdown(fp)
            except Exception as e:
                logger.error(f"读取 {fp} 失败: {e}, 跳过")
                publish_log.setdefault(fp.name, {})['csdn'] = {
                    "published": False,
                    "error": f"read_failed: {e}",
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
                save_publish_log(publish_log)
                continue

            try:
                post = frontmatter.loads(full_md_text)
                if isinstance(post.metadata.get("title"), str) and post.metadata["title"].strip():
                    use_title = post.metadata["title"].strip()
                else:
                    use_title = fp.stem
                    use_title = re.sub(r"^\d{8}_", "", use_title)
                
                if len(use_title) > 20:
                    use_title = use_title[:20]
                
                logger.info(f"使用标题: {use_title}")
                logger.info(f"使用标签: {DEFAULT_TAGS}")

                try:
                    page.goto(EDITOR_URL, timeout=60000)
                except Exception as e:
                    logger.error(f"跳转到编辑器失败: {e}")

                if use_title:
                    fill_title(page, use_title)

                ok = fill_editor_with_markdown(page, post.content)
                if not ok:
                    logger.error("未能自动填充正文，跳过自动发布。")
                    publish_log.setdefault(fp.name, {})['csdn'] = {
                        "published": False,
                        "error": "fill_editor_failed",
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    }
                    save_publish_log(publish_log)
                    continue

                time.sleep(2)

                if args.skip_publish:
                    logger.info("--skip-publish 启用，已填充但未触发发布。")
                    continue

                use_tags = DEFAULT_TAGS
                published = click_publish_buttons(page, tags=use_tags)
                if published:
                    logger.info(f"已触发发布请求: {fp.name}")
                    publish_log.setdefault(fp.name, {})['csdn'] = {
                        "published": True,
                        "title": use_title,
                        "tags": use_tags,
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    }
                    save_publish_log(publish_log)
                else:
                    logger.error(f"{fp.name} 的发布步骤未完全成功，请手动检查页面。")
                    publish_log.setdefault(fp.name, {})['csdn'] = {
                        "published": False,
                        "error": "publish_flow_incomplete",
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    }
                    save_publish_log(publish_log)

                time.sleep(30 + random.randint(5, 15))
            except Exception as exc:
                logger.error(f"处理 {fp} 时出现异常: {exc}", exc_info=True)
                publish_log.setdefault(fp.name, {})['csdn'] = {
                    "published": False,
                    "error": str(exc),
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
                save_publish_log(publish_log)


if __name__ == '__main__':
    main()
