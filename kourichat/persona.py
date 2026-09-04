"""人设 .krp 装载器：一个 .krp = 一个人设文件夹（不打包，MVP 直接读目录）。

.krp 目录契约（v1）::

    <id>.krp/
        index.toml        # 元数据：id?/name?/intro? + [[commands]]{name,prompt}
        heart.prompt      # 心核人设文本（可选，缺省回落 elixir 内置）
        reason.prompt     # 智核人设文本（可选）
        expressions/      # 表情包（可选）
            index.json    # [{"id","path","description"}]，path 相对本目录
            <图片文件>
        tools/            # elixir Tool 实现（可选，*.py 逐个扫描注册）

人设 id = 目录名去掉 `.krp`。命令在装载人设时注册进命令路由（逻辑层插件做注册，
这里只负责解析出数据结构与 Tool 实例）。
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from elixir.tools import Tool

PROMPT_HEART_FILE = "heart.prompt"
PROMPT_REASON_FILE = "reason.prompt"
EXPRESSIONS_JSON = "index.json"
TOOLS_DIR = "tools"


@dataclass
class PersonaCommand:
    """index.toml 定义的一条人设命令（/name 精准匹配触发，prompt 随行注入轮内）。"""

    name: str
    prompt: str


@dataclass
class Expression:
    """一个表情包资产：id + 相对路径 + 给 AI 的解释。"""

    id: str
    path: str
    description: str
    abs_path: str  # krp 内绝对路径（解析时拼好，供 adapter 发送）


@dataclass
class Persona:
    """一个已装载的人设。"""

    id: str
    root: Path
    name: str
    intro: str
    heart_prompt: str
    reason_prompt: str
    commands: list[PersonaCommand] = field(default_factory=list)
    expressions: list[Expression] = field(default_factory=list)
    tools: list[Tool] = field(default_factory=list)


def scan_personas(personas_dir: str | Path) -> dict[str, Persona]:
    """扫描人设目录下所有 `*.krp` 文件夹 → {persona_id: Persona}。

    目录不存在或为空 → 空注册表（不是错误）；单个 .krp 结构损坏只跳过该人设
    （记 stderr），不拖垮整个注册表。
    """
    base = Path(personas_dir)
    out: dict[str, Persona] = {}
    if not base.is_dir():
        return out
    for entry in sorted(base.iterdir()):
        if entry.is_dir() and entry.name.endswith(".krp"):
            try:
                p = load_persona(entry)
            except Exception as exc:
                print(f"[persona] {entry.name} 装载失败，跳过：{exc}", file=sys.stderr)
                continue
            out[p.id] = p
    return out


def load_persona(krp_dir: str | Path) -> Persona:
    """装载一个 .krp 文件夹为 Persona；结构不合法抛 ValueError。"""
    root = Path(krp_dir)
    if not root.is_dir() or not root.name.endswith(".krp"):
        raise ValueError(f"不是 .krp 人设目录：{root}")
    pid = root.name[: -len(".krp")]
    index_path = root / "index.toml"
    if not index_path.is_file():
        raise ValueError(f"人设 {pid} 缺少 index.toml：{index_path}")
    with open(index_path, "rb") as fh:
        index = tomllib.load(fh)

    def _text(path: Path) -> str:
        if path.is_file():
            return path.read_text(encoding="utf-8").strip()
        return ""

    commands = [
        PersonaCommand(name=str(c["name"]).strip(), prompt=str(c.get("prompt", "")).strip())
        for c in index.get("commands", [])
        if str(c.get("name", "")).strip()
    ]
    exprs = _load_expressions(root, pid)
    tools = _scan_tools(root / TOOLS_DIR, pid)
    return Persona(
        id=pid,
        root=root,
        name=str(index.get("name", "") or pid),
        intro=str(index.get("intro", "") or "").strip(),
        heart_prompt=_text(root / PROMPT_HEART_FILE),
        reason_prompt=_text(root / PROMPT_REASON_FILE),
        commands=commands,
        expressions=exprs,
        tools=tools,
    )


def _load_expressions(root: Path, pid: str) -> list[Expression]:
    """读 expressions/index.json → 表情资产列表（不校验图片真实存在）。"""
    jpath = root / "expressions" / EXPRESSIONS_JSON
    if not jpath.is_file():
        return []
    items: list[dict[str, Any]] = []
    try:
        raw = jpath.read_text(encoding="utf-8")
        loaded = json.loads(raw)
        if isinstance(loaded, list):
            items = [i for i in loaded if isinstance(i, dict)]
    except Exception as exc:  # 人设 JSON 损坏不应拖垮整个实例
        raise ValueError(f"人设 {pid} 表情 json 解析失败：{exc}") from exc
    out: list[Expression] = []
    for i in items:
        eid = str(i.get("id", "")).strip()
        rel = str(i.get("path", "")).strip()
        if not eid or not rel:
            continue
        out.append(Expression(
            id=eid,
            path=rel,
            description=str(i.get("description", "") or "").strip(),
            abs_path=str((root / "expressions" / rel).resolve()),
        ))
    return out


def _scan_tools(tools_dir: Path, pid: str) -> list[Tool]:
    """扫描 tools/*.py：收集继承 elixir Tool 且能无参实例化的实现类。

    单个文件解析/导入失败只跳过该文件（记在返回值之外，由调用方决定日志），
    不因一个人设的坏工具拖垮整个装配。
    """
    if not tools_dir.is_dir():
        return []
    out: list[Tool] = []
    seen_names: set[str] = set()
    for py in sorted(tools_dir.glob("*.py")):
        mod_name = f"_krp_{pid}_{py.stem}"
        spec = importlib.util.spec_from_file_location(mod_name, py)
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = module
        try:
            spec.loader.exec_module(module)
        except Exception as exc:
            sys.modules.pop(mod_name, None)
            print(f"[persona:{pid}] tools/{py.name} 导入失败，跳过：{exc}", file=sys.stderr)
            continue
        for obj in vars(module).values():
            if not (isinstance(obj, type) and issubclass(obj, Tool) and obj is not Tool):
                continue
            name = str(getattr(obj, "name", "") or "").strip()
            if not name or name in seen_names:
                continue
            try:
                inst = obj()
            except Exception as exc:  # 工具需要构造参数/环境 → 跳过并提示
                print(f"[persona:{pid}] tools/{py.name} 的 {name} 实例化失败，跳过：{exc}",
                      file=sys.stderr)
                continue
            seen_names.add(name)
            out.append(inst)
    return out
