"""主程序核心：插件注册接口 + 装配 + 退出（ticket 05/09 决策）。

- 主程序=核心：bus 之上的 events 调度器由 cli 提供；核心只管插件加载/装配/卸载。
- 插件入口 `async def apply(ctx, config)`，经 ctx.plugin 挂载（cordis 拓扑排序）。
"""

from __future__ import annotations

import importlib
from typing import Any

from cordis_py import Context

from .config import Config

__all__ = ["Config", "load_plugin", "assemble", "shutdown"]


async def load_plugin(ctx: Context, spec: dict[str, Any]) -> Any:
    """按模块路径导入插件模块，取其 `apply` 挂载到 ctx。

    spec: {module: "kourichat.adapter.cli", config: {...}}
    插件模块须暴露 `async def apply(ctx, config)`。
    """
    module = importlib.import_module(spec["module"])
    apply = getattr(module, "apply", None)
    if apply is None:
        raise TypeError(f"plugin module {spec['module']!r} has no apply(ctx, config)")
    fiber = ctx.plugin(apply, spec.get("config", {}))
    await fiber  # 等待加载完成；apply 抛错/依赖未满足时在此暴露（Fix 2）
    return fiber


async def assemble(ctx: Context, cfg: Config) -> list[Any]:
    """装配顺序（ticket 09）：adapter 插件 → logic/llm 插件（由清单顺序保证）。

    每个插件 await 其加载完成，任一 apply 失败立即抛出，不静默常驻。
    """
    fibers: list[Any] = []
    for spec in cfg.adapters() + cfg.plugins():
        fibers.append(await load_plugin(ctx, spec))
    return fibers


async def shutdown(ctx: Context) -> None:
    """优雅退出：反序卸载插件（cordis dispose_all 处理副作用/事件回收）。"""
    await ctx.dispose_all()
