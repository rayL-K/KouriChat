"""openclaw 登录管理器（ticket 15）：GET /login 取二维码 → 轮询 /login/token →
过期刷新（≤3 次）→ 成功落 AccountStore。

HTTP 用标准库 urllib（asyncio.to_thread），不新增依赖；webui 的 aiohttp 仅用于
前端服务（决策修订，见 ticket 15 的 Resolution 修订行）。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen

MAX_QR_REFRESH = 3  # 二维码过期强制刷新上限（对应网关内部 3 次语义）


class LoginManager:
    """单一活动登录状态机：start → 后台轮询 → success/failed。"""

    def __init__(self, gateway_url: str, store: Any,
                 poll_interval: float = 2.0, timeout: float = 10.0,
                 access_token: str = "", logger: Any = None,
                 on_success: Any = None) -> None:
        self.base = gateway_url.rstrip("/")
        self.store = store
        self.poll_interval = max(0.2, poll_interval)
        self.timeout = max(1.0, timeout)
        self.access_token = access_token
        self.logger = logger
        self.on_success = on_success  # 可选回调：登录成功（account_id）→ 调用方清 needs_relogin
        self._login: dict[str, Any] | None = None
        self._task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    # —— 状态暴露 ——
    def state(self) -> dict[str, Any] | None:
        return dict(self._login) if self._login else None

    # —— 生命周期 ——
    async def start(self, account_id: str | None = None,
                    force: bool = False) -> dict[str, Any]:
        """发起（或返回进行中的）登录；force=True 中断旧登录换新二维码。"""
        async with self._lock:
            if self._task is not None and not self._task.done():
                if not force:
                    return dict(self._login) if self._login else {}
                self._task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._task
                self._task = None
            try:
                self._login = await self._new(account_id)
            except Exception as exc:
                self._log("openclaw login start failed", error=str(exc))
                self._login = {
                    "uid": "", "qrcodeUrl": "", "accountId": account_id or "",
                    "status": "failed", "message": f"login start failed: {exc}",
                    "refresh_count": 0, "startedAt": time.time(),
                }
                return dict(self._login)
            self._task = asyncio.create_task(self._poll())
            return dict(self._login)

    async def close(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        self._login = None

    # —— 内部 ——
    async def _new(self, account_id: str | None) -> dict[str, Any]:
        path = f"/login?accountId={quote(account_id)}" if account_id else "/login"
        data = await self._http_get_json(path)
        return {
            "uid": str(data.get("id") or ""),
            "qrcodeUrl": str(data.get("qrcodeUrl") or ""),
            "accountId": account_id or "",
            "status": "pending",
            "message": "",
            "refresh_count": 0,
            "startedAt": time.time(),
        }

    async def _poll(self) -> None:
        try:
            while True:
                await asyncio.sleep(self.poll_interval)
                login = self._login
                if login is None:
                    return
                try:
                    data = await self._http_get_json(
                        f"/login/token?id={quote(login['uid'])}")
                except Exception as exc:
                    # 网络/网关瞬时错误：按 wait 重试，不判失败（同网关 pollQRStatus 语义）
                    self._log("openclaw login poll error, retrying",
                              error=str(exc))
                    continue
                status = str(data.get("status") or "pending")
                if status == "success":
                    await self._on_success(data)
                    return
                if status == "failed":
                    if login["refresh_count"] < MAX_QR_REFRESH:
                        await self._refresh()
                        if login["status"] == "failed":
                            return  # 刷新失败 → 终止（状态已置 failed）
                        continue
                    login["status"] = "failed"
                    login["message"] = str(data.get("message")
                                           or "登录失败（二维码多次失效）")
                    return
                # pending → 继续轮询
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if self._login is not None:
                self._login["status"] = "failed"
                self._login["message"] = f"login poll failed: {exc}"
            self._log("openclaw login poll fatal", error=str(exc))
        finally:
            # 任务结束（成功/失败/异常）即释放：下次 start() 发起全新登录
            self._task = None

    async def _on_success(self, data: dict[str, Any]) -> None:
        login = self._login
        assert login is not None
        login["status"] = "success"
        login["accountId"] = str(data.get("accountId") or login["accountId"])
        login["message"] = str(data.get("message") or "login succeeded")
        account = {
            "accountId": login["accountId"],
            "userId": str(data.get("userId") or ""),
            "token": str(data.get("token") or ""),
            "baseUrl": str(data.get("baseUrl") or ""),
            "status": "online",
        }
        await self.store.save(account)
        if self.on_success is not None:
            self.on_success(account["accountId"])
        self._log("openclaw login success", accountId=account["accountId"])

    async def _refresh(self) -> None:
        """二维码过期：GET /login?id=<uid> 强制刷新（uid 不变，网关保持会话）。"""
        login = self._login
        assert login is not None
        try:
            data = await self._http_get_json(f"/login?id={quote(login['uid'])}")
        except Exception as exc:
            login["status"] = "failed"
            login["message"] = f"刷新二维码失败: {exc}"
            self._log("openclaw login refresh failed", error=str(exc))
            return
        login["qrcodeUrl"] = str(data.get("qrcodeUrl") or login["qrcodeUrl"])
        login["status"] = "pending"
        login["refresh_count"] += 1
        self._log("openclaw qr refreshed", count=login["refresh_count"])

    # —— HTTP ——
    def _fetch_json(self, path: str) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.access_token}"} \
            if self.access_token else {}
        with urlopen(Request(self.base + path, headers=headers),
                     timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    async def _http_get_json(self, path: str) -> dict[str, Any]:
        return await asyncio.to_thread(self._fetch_json, path)

    def _log(self, msg: str, **kw: Any) -> None:
        if self.logger is not None:
            self.logger.warn(msg, **kw)
