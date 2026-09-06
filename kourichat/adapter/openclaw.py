"""OpenClaw 适配器（ticket 13/16）：对接 weixin-gateway 的 OneBot v11 服务面。

- 不改动 `kourichat/adapter/onebot.py`：继承 OneBotV11Adapter 复用
  WS 帧读写、echo 动作匹配、段过滤（register）、发送锁与未决 future 管理；
- 差异（覆盖点）：
  - 恒为 forward 客户端连网关 `ws://host:port/ws`（带 access_token）；
  - **自动重连**（退避 1s/2s/4s…封顶 30s，dispose 才停）；
  - 入向 message → `MESSAGE_RECEIVE`（platform="openclaw"）；
  - notice/meta 事件 → 登录失效/登录成功/生命周期处理（T16）+ `NOTICE_RECEIVE`；
  - 出向 send 的 user_id/group_id 传**字符串**（网关 recipient 只收 string，
    见 onebot-actions.ts:49-51），可选带 account_id；
  - 登录（二维码/轮询/刷新）由 LoginManager（T15）负责，账号镜像由
    AccountStore（T14）持久化；token_expired → 标记 invalid + 手动重登。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
from typing import Any

import websockets

from .onebot import OneBotV11Adapter
from .openclaw_events import handle_meta, handle_notice
from .openclaw_login import LoginManager
from .openclaw_store import AccountStore
from ..event import MESSAGE_RECEIVE
from ..types import Channel, Message, Segment, User

DEFAULT_DATA_DIR = "./data"
RECONNECT_BASE_DELAY = 1.0
RECONNECT_MAX_DELAY = 30.0


class OpenClawAdapter(OneBotV11Adapter):
    """weixin-gateway 适配器：OneBot v11 WS 客户端 + 二维码登录 + 账号镜像。"""

    capabilities = frozenset({"text", "image", "record", "video", "file"})

    def __init__(self, *, gateway_url: str, access_token: str = "",
                 data_dir: str = DEFAULT_DATA_DIR, autologin: bool = True,
                 poll_interval: float = 2.0, register: frozenset[str] | None = None,
                 account_id: str | None = None) -> None:
        self.gateway_url = gateway_url.rstrip("/")
        ws_url = self.gateway_url \
            .replace("http://", "ws://") \
            .replace("https://", "wss://") + "/ws"
        super().__init__(mode="forward", ws_url=ws_url,
                         token=access_token, register=register)
        self.account_id = account_id
        self.autologin = autologin
        self._store = AccountStore(data_dir)
        self._needs_relogin: dict[str, bool] = {}
        self._login = LoginManager(self.gateway_url, self._store,
                                   poll_interval=poll_interval,
                                   access_token=access_token,
                                   on_success=self._on_login_success)
        self._reconnect_task: asyncio.Task | None = None
        self._connected = False
        self._conn_attempt = 0

    # —— 生命周期 ——
    async def start(self, ctx: Any) -> None:
        self._ctx = ctx
        self._login.logger = ctx.get("logger")
        await self._store.start()
        self._reconnect_task = asyncio.create_task(self._run_forever())
        if self.autologin and not await self._store.list_accounts():
            await self.start_login()  # 默认网关无登录数据 → 自动发起扫码
        self._log("openclaw adapter started", url=self.gateway_url)

    async def close(self) -> None:
        if self._reconnect_task is not None:
            self._reconnect_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reconnect_task
            self._reconnect_task = None
        await self._login.close()
        await super().close()
        await self._store.stop()

    # —— WS 连接（forward + 自动重连）——
    async def _run_forever(self) -> None:
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        while True:
            try:
                self._ws = await websockets.connect(
                    self.ws_url, additional_headers=headers)
                self._connected = True
                self._conn_attempt = 0
                self._log("openclaw connected", url=self.ws_url)
                await self._read_conn(self._ws)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._log("openclaw ws error", error=str(exc))
            finally:
                self._connected = False
                if self._ws is not None:
                    with contextlib.suppress(Exception):
                        await self._ws.close()
                    self._ws = None
            self._conn_attempt += 1
            delay = min(RECONNECT_MAX_DELAY,
                        RECONNECT_BASE_DELAY * (2 ** (self._conn_attempt - 1)))
            try:
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                raise

    # —— 帧处理：notice/meta 先于 message/echo ——
    async def _handle_raw(self, raw: Any) -> None:
        try:
            frame = json.loads(raw)
        except json.JSONDecodeError:
            return
        post_type = frame.get("post_type")
        if post_type == "notice":
            await self._on_notice(frame)
            return
        if post_type == "meta_event":
            await self._on_meta(frame)
            return
        await super()._handle_raw(raw)

    # —— 入向 message（平台=openclaw；网关事件无 sender.nickname）——
    async def _on_message(self, frame: dict[str, Any]) -> None:
        segments = [self._seg(s) for s in frame.get("message", [])]
        segments = [s for s in segments if self._keep(s)]
        if not segments:
            return
        channel_type = "group" if frame.get("message_type") == "group" else "private"
        msg = Message(
            id=str(frame.get("message_id", "")),
            channel=Channel(
                platform="openclaw",
                channel_id=str(frame.get("group_id") or frame.get("user_id") or ""),
                channel_type=channel_type,
            ),
            sender=User(user_id=str(frame.get("user_id", "")),
                        name=str(frame.get("sender", {}).get("nickname", ""))),
            segments=segments,
            ts=frame.get("time") or time.time(),
            raw=frame,
        )
        events = self._ctx.get("events")
        await events.emit(MESSAGE_RECEIVE, msg)

    # —— 出向（网关 recipient 只收 string id）——
    async def send(self, out: Any) -> str:
        params: dict[str, Any] = {
            "message": [{"type": s.type, "data": s.data} for s in out.segments]}
        # 网关出向仅支持私聊（一对一微信消息）
        params["user_id"] = str(out.channel.channel_id)
        action = "send_private_msg"
        if self.account_id:
            params["account_id"] = self.account_id
        resp = await self._action(action, params)
        data = resp.get("data") or {}
        if not isinstance(data, dict):
            data = {}
        if str(resp.get("status")) != "ok" and not data:
            self._log("openclaw send failed", action=action,
                      status=resp.get("status"), retcode=resp.get("retcode"),
                      message=resp.get("message"))
        return str(data.get("message_id", ""))

    # —— notice / meta（T16：逻辑在 openclaw_events 模块，本处只分发 + 日志）——
    async def _on_notice(self, frame: dict[str, Any]) -> None:
        self._log("openclaw notice", notice_type=frame.get("notice_type"),
                  sub_type=frame.get("sub_type"),
                  account_id=frame.get("account_id"))
        events = self._ctx.get("events") if self._ctx else None
        await handle_notice(frame, store=self._store,
                            needs_relogin=self._needs_relogin,
                            events=events)

    async def _on_meta(self, frame: dict[str, Any]) -> None:
        await handle_meta(frame, store=self._store)

    def _on_login_success(self, account_id: str) -> None:
        """本地轮询登录成功即清失效标记（不依赖网关异步 notice 到达）。"""
        self._needs_relogin.pop(account_id, None)

    # —— 服务契约（供 webui 使用）——
    async def status(self) -> dict[str, Any]:
        accounts = []
        for acc in await self._store.list_accounts():
            # token 不外泄给前端（本地镜像凭据仅适配器内部/落盘使用）
            accounts.append({k: v for k, v in acc.items() if k != "token"})
        return {
            "connected": self._connected,
            "gateway_url": self.gateway_url,
            "accounts": accounts,
            "login": self._login.state(),
            "needs_relogin": [aid for aid, v in self._needs_relogin.items() if v],
        }

    def login_state(self) -> dict[str, Any] | None:
        return self._login.state()

    async def start_login(self, account_id: str | None = None) -> dict[str, Any]:
        return await self._login.start(account_id=account_id)

    async def relogin(self, account_id: str | None = None) -> dict[str, Any]:
        return await self._login.start(account_id=account_id, force=True)

    async def logout_local(self, account_id: str) -> None:
        await self._store.remove(account_id)
        self._needs_relogin.pop(account_id, None)

    def update_gateway(self, gateway_url: str | None = None,
                       access_token: str | None = None) -> None:
        """热更新网关地址/令牌（引导页或设置页保存后立即生效，无需重启）。

        仅更新内存状态；WS 重连与后续登录轮询会使用新值。
        """
        if gateway_url:
            self.gateway_url = str(gateway_url).rstrip("/")
            self.ws_url = self.gateway_url \
                .replace("http://", "ws://") \
                .replace("https://", "wss://") + "/ws"
            self._login.base = self.gateway_url
        if access_token is not None:
            self.token = str(access_token)
            self._login.access_token = self.token


async def apply(ctx: Any, config: dict[str, Any] | None = None) -> Any:
    """挂载 openclaw 适配器：注册服务 + 启动连接/登录。"""
    cfg = config or {}
    gateway_url = str(cfg.get("gateway_url", "")).rstrip("/")
    if not gateway_url:
        raise ValueError("openclaw adapter 需要 gateway_url"
                         "（weixin-gateway 地址，如 http://127.0.0.1:8765）")
    register = frozenset(cfg["register"]) if cfg.get("register") else None
    adapter = OpenClawAdapter(
        gateway_url=gateway_url,
        access_token=str(cfg.get("access_token", "")),
        data_dir=str(cfg.get("data_dir", DEFAULT_DATA_DIR)),
        autologin=bool(cfg.get("autologin", True)),
        poll_interval=float(cfg.get("poll_interval", 2.0)),
        register=register,
        account_id=str(cfg.get("account_id", "")) or None,
    )
    await adapter.start(ctx)
    ctx.provide("adapter.openclaw", adapter)

    async def dispose() -> None:
        await adapter.close()

    return dispose
