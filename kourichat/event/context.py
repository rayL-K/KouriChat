"""可变事件上下文（Q6/Q12/Q16）。

- 可修改：`text` / `segments` / `sender` / `channel` / `state`（前置修饰器加工上下文）。
- 只读原始事实：`event_name` / `message` / `raw`（插件不可赋值；段已深拷贝，改
  `segments` 不污染 message）。`stopped` 只能由 `stop()` 置位。
- 同一条消息的全部事件级（MESSAGE_RECEIVE → COMMAND_RECEIVE → 类型事件）共享同一
  ctx；`event_name` 由调度器按当前派发级维护（处理器读到的是本级的名称）。
"""

from __future__ import annotations

from ..types import Channel, Message, Segment, User, text_of


class EventContext:
    """单次事件派发的共享上下文；处理器直接改字段实现"多一道修饰"。"""

    __slots__ = ("_event_name", "_message", "text", "sender", "channel",
                 "segments", "state", "_stopped")

    def __init__(self, event_name: str, message: Message) -> None:
        self._event_name = event_name
        self._message = message
        self.text = text_of(message.segments)
        self.sender = User(user_id=message.sender.user_id, name=message.sender.name)
        self.channel = Channel(platform=message.channel.platform,
                               channel_id=message.channel.channel_id,
                               channel_type=message.channel.channel_type)
        # 深拷贝段：ctx 上改 segments 不影响 message 的原始事实（Q16）
        self.segments = [Segment(s.type, dict(s.data)) for s in message.segments]
        self.state: dict = {}
        self._stopped = False

    @property
    def event_name(self) -> str:
        return self._event_name

    @property
    def message(self) -> Message:
        return self._message

    @property
    def raw(self) -> dict:
        return self._message.raw

    @property
    def stopped(self) -> bool:
        return self._stopped

    def stop(self) -> None:
        """停止后续订阅（本事件级与后续事件级均不再执行）。"""
        self._stopped = True

    def __repr__(self) -> str:  # 调试友好
        return (f"<EventContext {self._event_name} "
                f"channel={self.channel.platform}:{self.channel.channel_id} "
                f"text={self.text!r} stopped={self._stopped}>")
