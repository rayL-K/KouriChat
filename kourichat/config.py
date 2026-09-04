"""TOML 主配置（ticket 09：TOML；热更用 cordis，骨架先支持重载读取）。"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any


class Config:
    """TOML 主配置：读 `plugins`/`adapters` 清单 + 任意段落。"""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.data: dict[str, Any] = {}

    def load(self) -> "Config":
        with open(self.path, "rb") as f:
            self.data = tomllib.load(f)
        return self

    def reload(self) -> "Config":
        return self.load()

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def plugins(self) -> list[dict[str, Any]]:
        """插件清单：[{name, module, config?}, ...]"""
        return self.get("plugins", [])

    def adapters(self) -> list[dict[str, Any]]:
        """adapter 配置：[{module, config?}, ...]（注册类 wx/qq 等见 ticket 06）"""
        return self.get("adapters", [])
