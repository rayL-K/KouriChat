"""事件调度器（Q7/Q20）：按注册顺序串行执行，stop() 停止后续订阅。

- 订阅注册表按"注册调用"成组（Q11：插件级注册表，插件卸载时注销）。
- 同一插件内按装饰器出现顺序；跨插件按插件装配顺序。
- `dispatch` 派发时临时切换 `event_name`（嵌套事件级共享同一 ctx，结束后还原）。
- COMMAND_RECEIVE 特例：只执行命令名/别名匹配的订阅（@on_command）。
"""

from __future__ import annotations

import inspect
from typing import Any, Callable

from .context import EventContext

Handler = Callable[[EventContext], Any]


class _Sub:
    """一条订阅：事件名 + 处理器 + 命令元数据（仅 COMMAND_RECEIVE 用）。"""

    __slots__ = ("event", "handler", "command", "aliases")

    def __init__(self, event: str, handler: Handler,
                 command: str | None = None, aliases: tuple[str, ...] = ()) -> None:
        self.event = event
        self.handler = handler
        self.command = command
        self.aliases = aliases


class Dispatcher:
    """事件调度器：`emit` 起新链（新 ctx），`relay` 复用 ctx 派发下一级事件。"""

    def __init__(self) -> None:
        self._subs: list[_Sub] = []

    def subscribe(self, event: str, handler: Handler, *,
                  command: str | None = None,
                  aliases: tuple[str, ...] = ()) -> _Sub:
        sub = _Sub(event, handler, command, aliases)
        self._subs.append(sub)
        return sub

    def unsubscribe(self, sub: _Sub) -> None:
        if sub in self._subs:
            self._subs.remove(sub)

    async def emit(self, event: str, message: Any) -> EventContext:
        """起新事件链：包装 message 为 EventContext 后派发。"""
        ctx = EventContext(event, message)
        await self.dispatch(ctx, event)
        return ctx

    async def relay(self, ctx: EventContext, event: str) -> bool:
        """同一 ctx 续发下一级事件（上下文修饰贯通全链）。返回是否有订阅执行。"""
        return await self.dispatch(ctx, event)

    async def dispatch(self, ctx: EventContext, event: str) -> bool:
        """串行执行订阅；返回是否至少执行了一个处理器。"""
        from . import COMMAND_RECEIVE  # 延迟导入避免循环（常量定义于 event/__init__）

        subs = [s for s in self._subs if s.event == event]
        if event == COMMAND_RECEIVE:  # 仅命令名/别名匹配的订阅执行
            name = ctx.state.get("command")
            subs = [s for s in subs if name is not None
                    and (s.command == name or name in s.aliases)]
        ran = False
        prev = ctx.event_name
        ctx._event_name = event  # 派发期切事件名，结束还原（插件不改它）
        try:
            for sub in subs:
                if ctx.stopped:
                    break
                result = sub.handler(ctx)
                if inspect.isawaitable(result):
                    await result
                ran = True
        finally:
            ctx._event_name = prev
        return ran
