"""
core/print.py — 彩色终端输出（兼容层）

已迁移的模块请改用 core.log.get_logger(__name__)。
本模块保留彩色输出，同时将所有调用路由至统一日志系统。
"""

import sys
import os
from colorama import init, Fore, Back, Style

if os.name == 'posix':
    os.environ['TERM'] = 'xterm-256color'
init()


class ColorPrinter:
    """带颜色输出的打印工具类"""

    def __init__(self):
        self._fore_color = ''
        self._back_color = ''
        self._style = ''

    def _reset(self):
        self._fore_color = ''
        self._back_color = ''
        self._style = ''
        return self

    def red(self):      self._fore_color = Fore.RED;     return self
    def green(self):    self._fore_color = Fore.GREEN;   return self
    def yellow(self):   self._fore_color = Fore.YELLOW;  return self
    def blue(self):     self._fore_color = Fore.BLUE;    return self
    def magenta(self):  self._fore_color = Fore.MAGENTA; return self
    def cyan(self):     self._fore_color = Fore.CYAN;    return self
    def white(self):    self._fore_color = Fore.WHITE;   return self
    def black(self):    self._fore_color = Fore.BLACK;   return self
    def bg_red(self):   self._back_color = Back.RED;     return self
    def bg_green(self): self._back_color = Back.GREEN;   return self
    def bold(self):     self._style = Style.BRIGHT;      return self
    def dim(self):      self._style = Style.DIM;         return self
    def normal(self):   self._style = Style.NORMAL;      return self

    def print(self, text, end='\n', file=sys.stdout):
        formatted = f"{self._style}{self._back_color}{self._fore_color}{text}{Style.RESET_ALL}"
        print(formatted, end=end, file=file)
        self._reset()
        return self

    def print_red(self, text, **kwargs):     self.red().print(text, **kwargs)
    def print_green(self, text, **kwargs):   self.green().print(text, **kwargs)
    def print_yellow(self, text, **kwargs):  self.yellow().print(text, **kwargs)
    def print_blue(self, text, **kwargs):    self.blue().print(text, **kwargs)
    def print_magenta(self, text, **kwargs): self.magenta().print(text, **kwargs)
    def print_cyan(self, text, **kwargs):    self.cyan().print(text, **kwargs)
    def print_error(self, text, **kwargs):   self.red().bold().print(text, **kwargs)
    def print_warning(self, text, **kwargs): self.yellow().bold().print(text, **kwargs)
    def print_success(self, text, **kwargs): self.green().bold().print(text, **kwargs)
    def print_info(self, text, **kwargs):    self.blue().print(text, **kwargs)


printer = ColorPrinter()


def _log(level: str, text: str) -> None:
    """将 print_* 调用路由至统一日志系统（stacklevel=4 显示真实调用方）。"""
    import logging
    # 移除首尾空白
    msg = str(text).strip()
    if not msg:
        return
        
    logging.getLogger("legacy.print").log(
        getattr(logging, level.upper()),
        msg,
        stacklevel=4,
    )


def print_error(text, **kwargs):
    # 如果在终端环境，依然输出彩色文本到 stderr
    if sys.stdout.isatty():
        printer.print_error(text, **kwargs)
    _log("error", text)


def print_info(text, **kwargs):
    if sys.stdout.isatty():
        printer.print_info(text, **kwargs)
    _log("info", text)


def print_warning(text, **kwargs):
    if sys.stdout.isatty():
        printer.print_warning(text, **kwargs)
    _log("warning", text)


def print_success(text, **kwargs):
    if sys.stdout.isatty():
        printer.print_success(text, **kwargs)
    _log("info", text)
