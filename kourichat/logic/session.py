"""会话处理（ticket 07/08 + 本轮）：MESSAGE_PRIVATE/GROUP → elixir Session → 流式回送。

本轮变化（打断接入）：
- **turn 任务化**：空闲消息由 handler 快速建后台任务跑 `start_turn` 逐句 → adapter.send，
  事件链不再整轮阻塞 → 适配器可在机器人说话期间继续收新消息；
- **打断**：session 忙时新消息走 `session.interject(text)`（elixir 语义：合成中切流、
  加话起新一轮），`stop_word`（默认 /stop）→ `session.force_stop()`；
  elixir 单 active 轮约束由 busy 检查兜底：无 interject 接口的替身对象忙时丢弃
  新消息（防 ActiveTurnError）；turn 尚未 active 的启动窗口消息先排队、结束后补跑；
- **表情**：人设 send_expression 选中的表情写入 session._kouri_expr holder，仅当整轮
  自然结束才发送 image 段；期间被打断/强断 → holder 清空（该表情不发送）。

session key 语义不变（channel 级收敛）；人设隔离由 llm/factory 在持久化 id 上追加
`|<persona.id>` 完成，本模块无感知。
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

from ..event import (
    EventContext,
    MESSAGE_GROUP,
    MESSAGE_PRIVATE,
    on_message,
    register_module_handlers,
)
from ..types import Channel, OutMessage, Segment, User

DEFAULT_STOP_WORD = "/stop"


def session_key(channel: Channel, sender: User) -> str:
    """按已修饰的 ctx 生成 key，保证会话归属与回复目标一致。"""
    if channel.channel_type == "group":
        return f"{channel.platform}:group:{channel.channel_id}"
    return f"{channel.platform}:private:{channel.channel_id}:{sender.user_id}"


def _expr_holder(session: Any) -> dict[str, Any] | None:
    return getattr(session, "_kouri_expr", None)


def _clear_pending_expr(session: Any) -> None:
    holder = _expr_holder(session)
    if holder:
        holder.pop("expr", None)


async def apply(ctx: Any, config: dict[str, Any] | None = None) -> Any:
    cfg = config or {}
    stop_word = str(cfg.get("stop_word", DEFAULT_STOP_WORD))
    logger = ctx.get("logger")
    turns: dict[int, asyncio.Task] = {}  # id(session) → 正在跑的 turn 任务
    pending: dict[int, list[tuple[Any, str]]] = {}  # id(session) → 等待的 (channel, text)

    def _start(session: Any, channel: Any, text: str) -> None:
        adapter = ctx.get(f"adapter.{channel.platform}")
        task = asyncio.create_task(_drive(ctx, session, adapter, channel, text))
        turns[id(session)] = task

    def is_busy(session: Any) -> bool:
        task = turns.get(id(session))
        if task is not None and not task.done():
            return True
        return bool(getattr(session, "active", False))

    async def _drive(ctx: Any, session: Any, adapter: Any,
                     channel: Channel, text: str) -> None:
        """跑一轮 start_turn：逐句文本回送；自然结束才发选中表情。"""
        try:
            async for sentence in session.start_turn(text):
                if adapter is not None:
                    await adapter.send(OutMessage(
                        channel=channel,
                        segments=[Segment("text", {"text": sentence})],
                    ))
            await _send_pending_expr(adapter, channel, session)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if logger is not None:
                logger.error("turn_error", error=repr(exc), session=session.id)
        finally:
            sid = id(session)
            cancelled = asyncio.current_task().cancelling() if asyncio.current_task() else 0
            if turns.get(sid) is asyncio.current_task():
                turns.pop(sid, None)
                # 启动窗口期排队的消息，在本任务结束后补跑（被取消则不补）
                if not cancelled:
                    queued = pending.get(sid)
                    if queued:
                        channel, text = queued.pop(0)
                        if not queued:
                            pending.pop(sid, None)
                        _start(session, channel, text)

    async def _handle(ctx: Any, evt: EventContext) -> None:
        full = evt.text.strip()
        if not full:
            return
        session = _session_of(ctx, evt)
        if session is None:
            return
        # 群聊：整条带上说话人（ticket 07：群级收敛但消息带人）
        text = f"[{evt.sender.name or evt.sender.user_id}] {full}" \
            if evt.channel.channel_type == "group" else full
        if full == stop_word:
            # 停止词：忙则强断（正在说的话算数，未说的丢弃），空闲则纯消费
            if is_busy(session):
                _clear_pending_expr(session)
                session.force_stop()
            return
        if is_busy(session):
            active = bool(getattr(session, "active", False))
            if hasattr(session, "interject") and active:
                # 说话期间收到新消息 → 加话打断；本轮已选表情作废（不发送）
                _clear_pending_expr(session)
                session.interject(text)
            elif active:
                # 忙但无打断接口的替身：不重复启轮（防 ActiveTurnError）
                if logger is not None:
                    logger.warn("session_busy_dropped", text=text, session=session.id)
            else:
                # turn 已创建但尚未 active（启动窗口）→ 排队，本任务结束后补跑
                pending.setdefault(id(session), []).append((evt.channel, text))
            return
        _start(session, evt.channel, text)

    def _session_of(ctx: Any, evt: EventContext) -> Any:
        factory = ctx.get("llm.factory")
        if factory is None:
            return None
        return factory(session_key(evt.channel, evt.sender))

    @on_message(MESSAGE_PRIVATE)
    async def on_private(evt: EventContext) -> None:
        await _handle(ctx, evt)

    @on_message(MESSAGE_GROUP)
    async def on_group(evt: EventContext) -> None:
        await _handle(ctx, evt)

    base_dispose = register_module_handlers(ctx, locals())

    async def dispose() -> None:
        # 注销订阅 + 取消在跑 turn（shutdown 不残留后台任务）
        await base_dispose()
        for task in list(turns.values()):
            if not task.done():
                task.cancel()
        for task in list(turns.values()):
            with contextlib.suppress(asyncio.CancelledError):
                await task
        turns.clear()
        pending.clear()

    return dispose


async def _send_pending_expr(adapter: Any, channel: Channel, session: Any) -> None:
    """整轮自然结束后：若本轮选中了表情则补发 image 段（holder 已由打断路径清空）。"""
    holder = _expr_holder(session)
    if adapter is None or holder is None:
        return
    expr = holder.pop("expr", None)
    if expr is None:
        return
    await adapter.send(OutMessage(
        channel=channel,
        segments=[Segment("image", {"file": expr.get("path", "")})],
    ))
