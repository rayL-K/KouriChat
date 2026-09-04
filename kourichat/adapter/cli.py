"""CLI 适配器（ticket 06 首闭环）：stdin 每行 → MESSAGE_RECEIVE。"""

from __future__ import annotations

import asyncio
import contextlib
import sys
import time
from typing import Any

from .base import Adapter
from ..event import MESSAGE_RECEIVE
from ..types import Channel, Message, OutMessage, Segment, User, text_of


class CliAdapter(Adapter):
    """CLI 平台适配器：文本收发，能力位 {text}。"""

    capabilities = frozenset({"text"})

    def __init__(self) -> None:
        self._seq = 0

    async def send(self, out: OutMessage) -> str:
        self._seq += 1
        print(f"[cli:{self._seq}] {text_of(out.segments)}", flush=True)
        return f"cli-{self._seq}"

    async def recall(self, msg_id: str) -> None:
        pass  # CLI 无撤回能力


async def apply(ctx: Any, config: dict[str, Any] | None = None) -> Any:
    """挂载 CLI 适配器：注册服务 + 启动 stdin 读取循环。"""
    config = config or {}
    adapter = CliAdapter()
    events = ctx.get("events")
    ctx.provide("adapter.cli", adapter)
    stop_event: asyncio.Event = ctx.get("stop_event")

    async def read_loop() -> None:
        loop = asyncio.get_running_loop()
        while True:
            line = await loop.run_in_executor(None, sys.stdin.readline)
            if not line:  # EOF → 优雅退出
                stop_event.set()
                return
            text = line.rstrip("\n")
            if not text:
                continue
            await events.emit(MESSAGE_RECEIVE, Message(
                id=f"cli-{time.time_ns()}",
                channel=Channel(platform="cli", channel_id="stdin", channel_type="private"),
                sender=User(user_id="local", name="local"),
                segments=[Segment("text", {"text": text})],
                ts=time.time(),
            ))

    task = asyncio.create_task(read_loop())

    async def dispose() -> None:
        # 先关 stdin：让仍阻塞在 readline 的 executor 线程以 EOF 返回，
        # 避免 asyncio.run 退出时 shutdown_default_executor 挂起（Fix 3）。
        with contextlib.suppress(Exception):
            sys.stdin.close()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    return dispose
