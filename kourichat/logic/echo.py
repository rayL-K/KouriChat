"""echo 任务（默认任务，可开关）：收到 `/echo` 后原样回显下一条消息。

语义移植自 weixin-gateway-test 的 `listen_and_echo`（CLI demo robot）：
- 收到文本 == `/echo` → 武装（armed）；该条消息被拦截（不进命令/大模型）；
- 已武装时收到下一条消息 → 把整段 message（text/媒体段数组）原样发回给发送者，
  随后解除武装；该条消息同样被拦截（不进命令/大模型）；
- 未武装 / 关闭时 → 不干预，消息全部走正常流程（命令 → 大模型）。

注意：
- 装配顺序必须早于 logic.command（TEMPLATE 已把本插件放在 command 之前），
  拦截才生效（dispatcher 串行执行，stop() 截断后续订阅）。
- 网关出向仅支持私聊（一对一）；group 消息不触发回显。
- armed 为全局状态（同测试包语义）；多会话同时活跃时以先到者为准。
"""

from __future__ import annotations

from typing import Any

from ..event import MESSAGE_RECEIVE, on_message, register_module_handlers
from ..types import OutMessage, text_of

ECHO_TRIGGER = "/echo"


async def apply(ctx: Any, config: dict[str, Any] | None = None) -> Any:
    cfg = config or {}
    enabled = bool(cfg.get("enabled", True))
    logger = ctx.get("logger")
    armed = False  # 跨消息保持武装状态（测试包语义）

    @on_message(MESSAGE_RECEIVE)
    async def echo_handler(evt: Any) -> None:
        nonlocal armed
        if not enabled:
            return  # 关闭：全部消息走正常流程
        if evt.channel.channel_type != "private":
            return  # 网关出向仅私聊，群消息不触发
        if text_of(evt.segments).strip() == ECHO_TRIGGER:
            armed = True
            if logger is not None:
                logger.warn("echo_armed", channel=evt.channel.channel_id)
            evt.stop()  # 拦截 `/echo` 本身（不进命令/大模型）
            return
        if armed:
            armed = False
            adapter = ctx.get(f"adapter.{evt.channel.platform}")
            if adapter is not None:
                # 原样回显：整段 message 数组（text/媒体段）发回给发送者
                await adapter.send(OutMessage(channel=evt.channel,
                                              segments=evt.segments))
                if logger is not None:
                    logger.warn("echo_replied", to=evt.channel.channel_id)
            evt.stop()  # 拦截被回显的那条消息（不进命令/大模型）
            return
        # 未武装：不拦截，走正常流程

    return register_module_handlers(ctx, locals())
