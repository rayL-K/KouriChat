"""装饰器订阅 API（Q5B/Q9/Q18/Q19）：装饰器只标记，插件 apply 里统一注册。

用法：

    from kourichat.event import on_message, on_command, register_module_handlers

    @on_command("help", aliases=("h",))
    async def help_cmd(ctx: EventContext) -> None: ...

    @on_message()                     # 默认 MESSAGE_RECEIVE
    async def decorate(ctx: EventContext) -> None: ...

    async def apply(ctx, config):
        return register_module_handlers(ctx, globals())   # 返回统一 dispose

处理器签名统一 `async def handler(ctx: EventContext)`（Q19）；
同插件内按装饰器出现顺序执行（Q11）。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Callable

MARK = "__kouri_events__"  # 标记属性：[(event_name, meta), ...]


def on_message(event: str | None = None) -> Callable:
    """订阅消息事件；默认 MESSAGE_RECEIVE，也可指定 MESSAGE_PRIVATE/GROUP。"""
    from . import MESSAGE_RECEIVE  # 常量定义于 event/__init__（延迟导入避循环）
    return _mark_fn(event or MESSAGE_RECEIVE)


def on_command(name: str, *, aliases: tuple[str, ...] = ()) -> Callable:
    """注册命令处理器（COMMAND_RECEIVE，按命令名/别名匹配执行）。"""
    from . import COMMAND_RECEIVE
    return _mark_fn(COMMAND_RECEIVE, command=name, aliases=tuple(aliases))


def on_notice() -> Callable:
    """订阅 NOTICE_RECEIVE（平台通知事件，预留）。"""
    from . import NOTICE_RECEIVE
    return _mark_fn(NOTICE_RECEIVE)


def on_request() -> Callable:
    """订阅 REQUEST_RECEIVE（平台请求事件，预留）。"""
    from . import REQUEST_RECEIVE
    return _mark_fn(REQUEST_RECEIVE)


def _mark_fn(event: str, **meta: Any) -> Callable[[Any], Any]:
    """只标记不注册（Q18）：标记在函数 `__kouri_events__`，注册交给 register。"""

    def deco(fn: Any) -> Any:
        marks = getattr(fn, MARK, None)
        if marks is None:
            marks = []
            setattr(fn, MARK, marks)
        marks.append((event, meta))
        return fn

    return deco


def register_module_handlers(ctx: Any, namespace: Mapping[str, Any]) -> Callable:
    """扫描 namespace 中带标记的可调用对象，注册到 ctx 的 events 调度器。

    返回统一 dispose：插件卸载时注销本插件全部订阅（Q11 插件级注册表）。
    """
    dispatcher = ctx.get("events")
    if dispatcher is None:
        raise RuntimeError("register_module_handlers 需要 ctx 提供 'events' 服务（Dispatcher）")
    subs = []
    for obj in namespace.values():
        for event, meta in getattr(obj, MARK, ()):
            subs.append(dispatcher.subscribe(
                event, obj,
                command=meta.get("command"),
                aliases=meta.get("aliases", ()),
            ))

    async def dispose() -> None:
        for sub in subs:
            dispatcher.unsubscribe(sub)

    return dispose
