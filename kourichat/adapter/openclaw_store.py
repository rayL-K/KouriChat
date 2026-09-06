"""openclaw 账号本地持久化：elixir Store + JsonlDataSource 薄封装（ticket 14）。

设计：
- 独立数据目录 `<data_dir>/openclaw-accounts`，不污染 llm/factory 的会话 store；
- 固定 session_id "openclaw.accounts"，集合用 elixir 默认集合 "rounds"
  （Store.hydrate 只回放 DEFAULT_COLLECTIONS，见 elixir/store.py:23,56-59，
  因此必须用 rounds 才能跨重启读回）；
- append-only：每次状态变化追加一条新记录，读取时按 accountId 取最新
  （记录自带 id/ts，由 Store.append 注入）。
"""

from __future__ import annotations

import os
import time
from typing import Any

from elixir import Settings
from elixir.datasources.jsonl import JsonlDataSource
from elixir.store import Store

ACCOUNTS_SESSION = "openclaw.accounts"
COLLECTION = "rounds"  # 复用 elixir 默认集合（可跨重启回放）

STATUS_ONLINE = "online"
STATUS_INVALID = "invalid"
STATUS_OFFLINE = "offline"
STATUS_REMOVED = "removed"


class AccountStore:
    """openclaw 已登录账号镜像（accountId/userId/token/baseUrl/status）。"""

    def __init__(self, data_dir: str, flush_interval: float = 5.0) -> None:
        self._dir = os.path.join(data_dir, "openclaw-accounts")
        self._store = Store(
            JsonlDataSource(self._dir),
            Settings(flush_interval=flush_interval),
        )
        self._started = False

    @property
    def started(self) -> bool:
        return self._started

    async def start(self) -> None:
        if self._started:
            return
        await self._store.start()
        self._started = True

    async def stop(self) -> None:
        if not self._started:
            return
        await self._store.stop()
        self._started = False

    async def save(self, account: dict[str, Any]) -> None:
        """追加一条账号快照（新状态=新记录）。"""
        await self._store.append(ACCOUNTS_SESSION, COLLECTION, {
            "accountId": str(account["accountId"]),
            "userId": str(account.get("userId") or ""),
            "token": str(account.get("token") or ""),
            "baseUrl": str(account.get("baseUrl") or ""),
            "status": str(account.get("status") or STATUS_ONLINE),
            "savedAt": time.time(),
        })

    async def list_accounts(self) -> list[dict[str, Any]]:
        """全部账号的最新快照（removed 除外），按最新记录倒序。"""
        rows = self._store.query(ACCOUNTS_SESSION, COLLECTION,
                                 limit=10_000, order="desc")
        latest: dict[str, dict[str, Any]] = {}
        for row in rows:
            aid = str(row.get("accountId") or "")
            if aid and aid not in latest:
                latest[aid] = row
        return [a for a in latest.values()
                if a.get("status") != STATUS_REMOVED]

    async def get(self, account_id: str) -> dict[str, Any] | None:
        for acc in await self.list_accounts():
            if acc["accountId"] == account_id:
                return acc
        return None

    async def mark_invalid(self, account_id: str) -> None:
        """登录失效：保留凭据快照，仅追加 status=invalid（T16）。"""
        cur = await self.get(account_id)
        if cur is None:
            return
        await self.save({**cur, "status": STATUS_INVALID})

    async def remove(self, account_id: str) -> None:
        """本地登出：追加 removed 记录（append-only，list 过滤）。"""
        cur = await self.get(account_id)
        await self.save({**cur, "accountId": account_id,
                         "status": STATUS_REMOVED} if cur else
                        {"accountId": account_id, "status": STATUS_REMOVED})
