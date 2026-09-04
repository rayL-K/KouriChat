"""适配器契约（ticket 06）：入向发 MESSAGE_RECEIVE，出向 send/recall 服务调用。"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..types import OutMessage


class Adapter(ABC):
    """平台适配器基类：能力位 frozenset[str] + 出向 send/recall。

    入向由各实现自行建立（stdin/WS），收到平台消息后统一：
        dispatcher.emit(MESSAGE_RECEIVE, msg)
    类型级事件（MESSAGE_PRIVATE/GROUP）由逻辑层 relay，适配器不重复发（Fix 1）。
    """

    capabilities: frozenset[str] = frozenset()

    @abstractmethod
    async def send(self, out: OutMessage) -> str:
        """发送出向消息，返回平台消息 id。"""

    @abstractmethod
    async def recall(self, msg_id: str) -> None:
        """撤回平台消息；无能力则 no-op。"""

    async def close(self) -> None:
        """释放连接/任务；默认无操作。"""
