"""日志：loguru 实现 elixir.Logger 接口，框架与 elixir 共用（ticket 09 + 本轮）。

- 默认给一个可读的控制台格式（颜色分 component），可用 config 覆盖；
- `configure_logging()`：可配 console 等级/格式、文件落盘（log_dir + rotation）；
- 全局兜底：未捕获异常（sys.excepthook + asyncio task 异常）也进同一日志链，
  保证「报错有日志捕捉」；
- LoguruLogger 仍是薄包装（debug/info/warn/error，**ctx 结构化），消费方无感。
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

from loguru import logger as _logger

DEFAULT_CONSOLE_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
    "<level>{message}</level>"
)
DEFAULT_FILE_FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
    "{name}:{function}:{line} - {message}"
)

_configured = False
_prev_excepthook = sys.excepthook  # 链式保留先前 hook（faulthandler/sentry 等）


def configure_logging(
        *,
        log_level: str = "INFO",
        console_format: str | None = None,
        log_dir: str | None = None,
        rotation: str = "1 day",
) -> None:
    """装配日志：console（必开，颜色）+ 可选文件 sink；并把全局异常接入日志。

    无 log_dir → 只控制台。重复调用会先清掉 loguru 既有 handler 再重建
    （本框架独占 loguru 链；若别处直接 add 过 sink 会被本次清掉——已知取舍）。
    """
    global _configured, _prev_excepthook
    level = str(log_level or "INFO").upper()
    _logger.remove()
    _logger.add(
        sys.stderr,
        level=level,
        format=console_format or DEFAULT_CONSOLE_FORMAT,
        colorize=True,
        backtrace=True,
        diagnose=False,
    )
    if log_dir:
        path = Path(log_dir)
        path.mkdir(parents=True, exist_ok=True)
        _logger.add(
            path / "kourichat_{time:YYYY-MM-DD}.log",
            level=level,
            format=DEFAULT_FILE_FORMAT,
            rotation=rotation or "1 day",
            retention="30 days",
            encoding="utf-8",
        )
    if not _configured:
        _prev_excepthook = sys.excepthook
        sys.excepthook = _unhandled_hook  # 进程级未捕获异常
        _configured = True


def _unhandled_hook(exc_type: Any, exc: BaseException, tb: Any) -> None:
    _logger.opt(exception=(exc_type, exc, tb)).error("unhandled exception")
    _prev_excepthook(exc_type, exc, tb)  # 链式：保留先前 hook 行为


def loop_exception_handler(logger: Any):
    """给 asyncio 事件循环装的异常处理器：后台 task 抛错不再只吞进 stderr。"""

    def _handler(_loop: asyncio.AbstractEventLoop, context: dict[str, Any]) -> None:
        exc = context.get("exception")
        if exc is not None:
            logger.error("unhandled task exception", error=repr(exc))
        else:
            logger.error("asyncio error", message=str(context.get("message", "")))

    return _handler


class LoguruLogger:
    """实现 elixir.logger.Logger 的四方法接口（debug/info/warn/error，**ctx 结构化）。

    调用方（elixir Session / 框架插件）无需感知底层是 loguru。
    """

    def debug(self, msg: str, **ctx: Any) -> None:
        _logger.debug(self._line(msg, ctx))

    def info(self, msg: str, **ctx: Any) -> None:
        _logger.info(self._line(msg, ctx))

    def warn(self, msg: str, **ctx: Any) -> None:
        _logger.warning(self._line(msg, ctx))

    def error(self, msg: str, **ctx: Any) -> None:
        _logger.error(self._line(msg, ctx))

    @staticmethod
    def _line(msg: str, ctx: dict[str, Any]) -> str:
        if not ctx:
            return msg
        return f"{msg}  ({', '.join(f'{k}={v}' for k, v in ctx.items())})"
