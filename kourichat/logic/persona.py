"""人设插件（逻辑层装配位）：装载 .krp 注册表 + 启用一个人设 + 注册其命令。

服务：
- `persona.registry` → {persona_id: Persona}（该目录全部 .krp，可随时切用）
- `persona.active`   → 当前启用的人设（config.enable 指定；缺省取第一个）

命令语义：`/name ...` 前缀路由精准匹配到人设命令后（沿用 command 插件），把
「命令 prompt + 用户完整输入」一起合成文本并**续发类型事件**（不 stop）——
会话插件把这段文本作为当前轮喂给 Session，人设命令即自然对话一轮。
"""

from __future__ import annotations

from typing import Any

from ..event import COMMAND_RECEIVE, EventContext
from ..persona import Persona, PersonaCommand, scan_personas

PERSONA_REGISTRY = "persona.registry"
PERSONA_ACTIVE = "persona.active"


def _command_handler(cmd: PersonaCommand):
    async def handler(evt: EventContext) -> None:
        if evt.state.get("command") != cmd.name:
            return
        if cmd.prompt:
            # 命令 prompt + 用户完整输入一起成为本轮的对话内容
            evt.text = f"{cmd.prompt}\n\n用户输入：{evt.text}"

    return handler


async def apply(ctx: Any, config: dict[str, Any] | None = None) -> Any:
    cfg = config or {}
    personas_dir = str(cfg.get("personas_dir", "./personas"))
    enable = str(cfg.get("enable", "") or "").strip()
    logger = ctx.get("logger")

    registry = scan_personas(personas_dir)
    if not registry:
        if logger is not None:
            logger.warn("personas_empty", dir=personas_dir)
        ctx.provide(PERSONA_REGISTRY, {})
        ctx.provide(PERSONA_ACTIVE, None)
        return None

    active: Persona | None
    if enable and enable in registry:
        active = registry[enable]
    else:
        active = registry[sorted(registry)[0]]
        if enable and logger is not None:
            logger.warn("persona_not_found", enable=enable, fallback=active.id)

    ctx.provide(PERSONA_REGISTRY, registry)
    ctx.provide(PERSONA_ACTIVE, active)

    dispatcher = ctx.get("events")
    if dispatcher is None:
        raise RuntimeError("persona 插件需要 ctx 提供 'events' 服务（Dispatcher）")
    subs = []
    for cmd in active.commands:
        subs.append(dispatcher.subscribe(
            COMMAND_RECEIVE, _command_handler(cmd), command=cmd.name))

    async def dispose() -> None:
        for sub in subs:
            dispatcher.unsubscribe(sub)

    return dispose
