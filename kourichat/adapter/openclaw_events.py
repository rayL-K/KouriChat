"""网关 notice/meta 事件策略（工单 16）。

纯逻辑模块：不持有 ctx/连接，依赖注入 store / events / needs_relogin；
由工单 13 的 OpenClawAdapter._handle_raw 分发调用。

用户决策：登录失效（offline/token_expired）= 标记 invalid + NOTICE_RECEIVE 通知 +
needs_relogin 置位 + **手动重登**（本模块绝不发起登录）。
"""

from __future__ import annotations

import time
from typing import Any

from ..event import NOTICE_RECEIVE
from ..types import Channel, Message, Segment, User
from .openclaw_store import STATUS_ONLINE, STATUS_OFFLINE


async def handle_notice(frame: dict[str, Any], *,
                        store: Any,
                        needs_relogin: dict[str, bool],
                        events: Any = None) -> None:
    """处理一条 notice 帧；未知类型不 emit 不抛错（日志由调用方负责）。"""
    notice_type = str(frame.get("notice_type") or "")
    sub_type = str(frame.get("sub_type") or "")
    account_id = str(frame.get("account_id") or "")
    if notice_type == "offline" and sub_type == "token_expired":
        # 登录失效：标记 invalid + 通知 + 手动重登（不自动）
        if account_id:
            await store.mark_invalid(account_id)
            needs_relogin[account_id] = True
    elif notice_type == "offline":
        if account_id:
            await _mark_status(store, account_id, STATUS_OFFLINE)
    elif notice_type == "login" and sub_type == "login_success":
        if account_id:
            existing = await store.get(account_id)
            if existing is not None:
                await store.save({**existing, "status": STATUS_ONLINE})
            needs_relogin.pop(account_id, None)
    else:
        return
    await _emit_notice(events, frame)


async def handle_meta(frame: dict[str, Any], *, store: Any) -> None:
    """处理一条 meta_event 帧：lifecycle connect/disable → 本地状态（仅已有账号）。"""
    if str(frame.get("meta_event_type") or "") != "lifecycle":
        return
    account_id = str(frame.get("account_id") or "")
    sub_type = str(frame.get("sub_type") or "")
    if account_id:
        await _mark_status(
            store, account_id,
            STATUS_ONLINE if sub_type == "connect" else STATUS_OFFLINE)


async def _mark_status(store: Any, account_id: str, status: str) -> None:
    existing = await store.get(account_id)
    if existing is not None and existing.get("status") != status:
        await store.save({**existing, "status": status})


async def _emit_notice(events: Any, frame: dict[str, Any]) -> None:
    """NOTICE_RECEIVE 事件：payload 放 Message.raw（原始帧），供订阅方取用。"""
    if events is None:
        return
    account_id = str(frame.get("account_id") or "")
    msg = Message(
        id=f"notice-{time.time_ns()}",
        channel=Channel(platform="openclaw", channel_id=account_id,
                        channel_type="private"),
        sender=User(user_id="", name=""),
        segments=[Segment("text", {"text": "{} {}".format(
            frame.get("notice_type", ""), frame.get("sub_type", ""))})],
        ts=frame.get("time") or time.time(),
        raw=frame,
    )
    await events.emit(NOTICE_RECEIVE, msg)
