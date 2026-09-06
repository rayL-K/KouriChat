"""command 路由（Q8/Q10）：MESSAGE_RECEIVE 里的命令识别 → COMMAND_RECEIVE → 续发类型事件。

事件链：/cmd args → @on_command 处理器（可改 ctx；stop() 则终止全链）
        → 未停止（含未知命令、普通消息）→ MESSAGE_PRIVATE / MESSAGE_GROUP。
"""

from __future__ import annotations

import shlex
from typing import Any

from ..event import (
    COMMAND_RECEIVE,
    MESSAGE_GROUP,
    MESSAGE_PRIVATE,
    MESSAGE_RECEIVE,
    EventContext,
    on_message,
    register_module_handlers,
)

DEFAULT_PREFIX = "/"


async def apply(ctx: Any, config: dict[str, Any] | None = None) -> Any:
    cfg = config or {}
    prefix = str(cfg.get("prefix", DEFAULT_PREFIX))
    dispatcher = ctx.get("events")

    @on_message(MESSAGE_RECEIVE)
    async def route(ctx: EventContext) -> None:
        """命令识别：命中前缀则派发 COMMAND_RECEIVE；未停止则续发类型事件。"""
        text = ctx.text.strip()
        if text.startswith(prefix):
            try:
                parts = shlex.split(text[len(prefix):])
            except ValueError:
                parts = []  # 畸形引号按普通消息透发，不杀死 adapter 读循环
            if parts:
                ctx.state["command"] = parts[0]
                ctx.state["args"] = parts[1:]
                await dispatcher.relay(ctx, COMMAND_RECEIVE)
        if not ctx.stopped:  # 未停止（含命令未命中）→ 按消息类型续发
            event = MESSAGE_GROUP if ctx.channel.channel_type == "group" else MESSAGE_PRIVATE
            await dispatcher.relay(ctx, event)

    return register_module_handlers(ctx, locals())
