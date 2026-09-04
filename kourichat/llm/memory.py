"""KouriChat 记忆器（实现 elixir Memory ABC，注入 elixir Session 使用）。

三个记忆器，持久化全部走 elixir Store（jsonl DataSourceProvider）：

- EmotionMemory   情感**日志**：每次情绪变化记一条（关键词/情感值 0-10/事件原因/
                  日期/变化轮 id）。每条用户输入至多记一条，轮结束钩子把待写条目落盘
                  （带上本轮 round_id）。工具：note_emotion(心核)、emotion_latest、
                  emotion_older。
- LongTermMemory  长期记忆：Live 未归档轮数达 max_count(M) 时，把比最近 keep_count(K)
                  轮更早的轮经「概要人设」压缩成摘要，写入**隔离的 summary Store 文件**
                  （摘要携带其覆盖的全部 round_ids）；原文保留于主 store 可查。
                  工具：summary_search / view_rounds / search_rounds / round_window。
- DiaryMemory     日记记忆：AI 自主决定写入绝不遗忘的关键事实（生日、丧亲等），
                  只追加不修改。工具：diary_write(content) / diary_read()（全内容）。

记忆按 elixir Store 的 session_id 命名空间隔离；llm/factory 以 `<会话key>|<人设id>`
作为 session id → 同会话不同人设记忆天然分开。
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any

from elixir.memory import Memory
from elixir.types import Message, RoleId, ToolSchema, roles_for

if TYPE_CHECKING:
    from elixir.session import Session
    from elixir.store import Store

DEFAULT_SUMMARY_PROMPT = (
    "你是概要人设：把给出的历史对话压缩成一段简洁、客观的第三人称概要，"
    "保留重要事实、约定与情绪脉络，不要复述逐句原文。"
)


def _schema(name: str, description: str, parameters: dict[str, Any],
            allowed: frozenset[RoleId] | None = None) -> ToolSchema:
    return ToolSchema(name=name, description=description,
                      parameters=parameters, allowed_in=allowed)


def _last_round_id(session: "Session") -> str:
    """取刚完结轮（on_round_completed 时已 add_round）的 round_id。"""
    latest = session.context.recent_rounds(1)
    return str(latest[0].id) if latest else ""


def _fmt_round(rec: dict[str, Any]) -> str:
    return f"轮 {rec.get('id')}：\n用户：{rec.get('user', '')}\n助手：{rec.get('ai', '')}"


# ---------------------------------------------------------------------------
# 情感记忆：日志式、顺写
# ---------------------------------------------------------------------------

class EmotionMemory(Memory):
    """情绪变更事件流水。note_emotion 只在当前轮内首次调用落待写，轮完结后带
    round_id 写 Store；与上一条关键词+情感值相同视为未变化不写。"""

    def __init__(self, session: "Session") -> None:
        super().__init__(session)
        self._turn_written = False  # 本活动轮是否已记过（防同轮反复精修标签）
        self._pending: dict[str, Any] | None = None

    # —— 钩子 ——
    async def on_round_completed(self, session: "Session") -> None:
        if self._pending is not None:
            rid = _last_round_id(session)
            if rid:
                await session.store.append(
                    session.id, "emotion", {**self._pending, "round_id": rid})
            self._pending = None
        self._turn_written = False

    async def boot_context(self) -> str:
        lines = self._page_lines(0)
        if not lines:
            return ""
        return "【最近情绪】\n" + "\n".join(lines)

    def _count(self) -> int:
        return max(1, int(getattr(self.session.settings, "emotion_boot_count", 10) or 10))

    def _page_lines(self, offset: int) -> list[str]:
        rows = self.session.store.query(self.session.id, "emotion",
                                        order="desc", limit=self._count(),
                                        offset=offset)
        return [self._fmt(r) for r in rows]

    # —— 工具 ——
    def function_pack(self, role: RoleId) -> list[ToolSchema]:
        note = _schema(
            "note_emotion",
            "记录一次情绪变化（每条用户输入至多记录一条；若与上一条情绪相同则不重复写）。"
            "仅在情绪发生变化时调用。",
            {"type": "object",
             "properties": {
                 "keyword": {"type": "string", "description": "情感关键词，如 开心/难过/平静"},
                 "value": {"type": "integer", "description": "情感值 0~10，越大越积极"},
                 "reason": {"type": "string",
                            "description": "情绪变化的原因（事件关键词摘要）"}},
             "required": ["keyword", "value", "reason"]},
            allowed=frozenset({"heart"}),
        )
        latest = _schema(
            "emotion_latest",
            f"获取最近的 {self._count()} 条情绪记忆（用于把握用户当前情绪状态）。",
            {"type": "object", "properties": {}},
        )
        older = _schema(
            "emotion_older",
            f"获取最近 {self._count()} 条之前更早的 {self._count()} 条情绪记忆（向前翻页）。",
            {"type": "object", "properties": {}},
        )
        return [s for s in (note, latest, older) if role in roles_for(s.allowed_in)]

    # —— 执行 ——
    async def run_tool(self, name: str, role: RoleId, **kwargs: Any) -> str | None:
        if name == "note_emotion":
            return await self._note(kwargs)
        if name == "emotion_latest":
            return await self._page(0)
        if name == "emotion_older":
            return await self._page(self._count())
        return None

    async def _note(self, args: dict[str, Any]) -> str:
        keyword = str(args.get("keyword", "") or "").strip()
        reason = str(args.get("reason", "") or "").strip()
        try:
            value = max(0, min(10, int(args.get("value", 0))))
        except (TypeError, ValueError):
            value = 0
        if not keyword:
            return "（缺少情感关键词，未记录）"
        if self.session.active and self._turn_written:
            return "（本轮已记录过情绪，每条用户输入只记一条）"
        last = self.session.store.query(self.session.id, "emotion",
                                        order="desc", limit=1)
        if last and str(last[0].get("keyword", "")) == keyword \
                and int(last[0].get("value", 0)) == value:
            return "情绪未变化（与上一条相同），不重复记录。"
        self._pending = {
            "keyword": keyword,
            "value": value,
            "reason": reason,
            "date": date.today().isoformat(),
        }
        self._turn_written = True
        return f"已记录情绪变化：{keyword}（{value}/10）。"

    async def _page(self, offset: int) -> str:
        lines = self._page_lines(offset)
        if not lines:
            return "（无更多情绪记录）"
        return "\n".join(lines)

    @staticmethod
    def _fmt(rec: dict[str, Any]) -> str:
        rid = rec.get("round_id")
        tail = f"（轮 {rid}）" if rid else ""
        return (f"「{rec.get('keyword', '')}」{rec.get('value', '?')}/10 "
                f"{rec.get('date', '')}：{rec.get('reason', '')}{tail}")


# ---------------------------------------------------------------------------
# 长期记忆：轮压缩 → 隔离 summary Store
# ---------------------------------------------------------------------------

class LongTermMemory(Memory):
    """对话长期记忆：K/M 窗口压缩 + 摘要检索 + 原文（按轮 id）回溯。

    摘要写入 `summary_store`（llm/factory 提供的隔离 Store，目录独立于主数据文件）；
    未提供时回退写 session.store（集合 summary），保证单测/无工厂环境可工作。
    """

    _OVERVIEW_COUNT = 3

    def __init__(self, session: "Session", *,
                 summary_store: "Store | None" = None,
                 summary_prompt: str = DEFAULT_SUMMARY_PROMPT) -> None:
        super().__init__(session)
        self._store = summary_store
        self._prompt = summary_prompt or DEFAULT_SUMMARY_PROMPT

    def _target(self) -> Any:
        return self._store or self.session.store

    # —— 钩子 ——
    async def on_round_completed(self, session: "Session") -> None:
        await self._maybe_compact(session)

    async def boot_context(self) -> str:
        rows = self._target().query(self.session.id, "summary",
                                    order="desc", limit=self._OVERVIEW_COUNT)
        if not rows:
            return ""
        lines = ["【过往概要】"]
        for d in reversed(rows):  # 最老在前
            lines.append(f"- {d.get('narrative', '')}（覆盖轮 {self._span_of(d)}）")
        return "\n".join(lines)

    @staticmethod
    def _span_of(d: dict[str, Any]) -> str:
        ids = d.get("round_ids") or []
        if len(ids) == 1:
            return str(ids[0])
        if len(ids) > 1:
            return f"{ids[0]}~{ids[-1]}"
        return f"{d.get('from_round', '')}~{d.get('to_round', '')}"

    async def _maybe_compact(self, session: "Session") -> None:
        """Live 未归档轮数 ≥ max_count(M) 时压缩：保留最新 keep_count(K) 轮全文，
        更早的全部折进摘要并移出 Live（原文仍在主 store，可 view_rounds 回溯）。"""
        keep = int(getattr(session.settings, "keep_count", 20) or 20)
        maximum = int(getattr(session.settings, "max_count", 60) or 60)
        count = session.context.count()
        if count < maximum or count <= keep:
            return
        evict = session.context.oldest_rounds(count - keep)
        if not evict:
            return
        entry = await self._compact(evict)
        await self._target().append(session.id, "summary", entry)
        session.context.drop_oldest_rounds(len(evict))

    async def _compact(self, evicted: list[Any]) -> dict[str, Any]:
        transcript = "\n".join(
            f"轮 {r.id} 用户：{r.user}\n  助手：{r.ai}" for r in evicted)
        msg = Message(role="user",
                      content=f"请把以下对话压缩为一段概要：\n\n{transcript}")
        result = await self.session.llm.complete(
            role="memory", system=self._prompt, messages=[msg])
        narrative = (result.content or "").strip()
        ids = [str(r.id) for r in evicted]
        return {"round_ids": ids,
                "from_round": ids[0], "to_round": ids[-1],
                "narrative": narrative or f"（自动概要，覆盖轮 {ids[0]}~{ids[-1]}）"}

    # —— 工具 ——
    def function_pack(self, role: RoleId) -> list[ToolSchema]:
        tools = [
            _schema(
                "summary_search",
                "按关键词在长期记忆的摘要里查找历史概要。",
                {"type": "object",
                 "properties": {"query": {"type": "string", "description": "检索关键词"}},
                 "required": ["query"]}),
            _schema(
                "view_rounds",
                "按 round_id 查看一或多轮对话完整原文（一次可传多个 id）。",
                {"type": "object",
                 "properties": {"round_ids": {"type": "array",
                                              "items": {"type": "string"},
                                              "description": "目标轮 id 列表"}},
                 "required": ["round_ids"]}),
            _schema(
                "search_rounds",
                "关键词在全部对话原文中做全量检索（按轮返回命中）。",
                {"type": "object",
                 "properties": {"query": {"type": "string", "description": "检索关键词"}},
                 "required": ["query"]}),
            _schema(
                "round_window",
                "按一个 round_id 取它前后各 1 轮（含自己共 3 轮）的对话原文，"
                "用于看清一件事的上下文。",
                {"type": "object",
                 "properties": {"round_id": {"type": "string", "description": "目标轮 id"}},
                 "required": ["round_id"]}),
        ]
        return tools  # 双核均可用（角色扮演需要随时回忆旧事）

    async def run_tool(self, name: str, role: RoleId, **kwargs: Any) -> str | None:
        if name == "summary_search":
            return await self._summary_search(kwargs)
        if name == "view_rounds":
            return await self._view_rounds(kwargs)
        if name == "search_rounds":
            return await self._search_rounds(kwargs)
        if name == "round_window":
            return await self._round_window(kwargs)
        return None

    async def _summary_search(self, args: dict[str, Any]) -> str:
        q = str(args.get("query", "") or "").strip().lower()
        rows = self._target().query(self.session.id, "summary", order="desc", limit=100)
        hits = [d for d in rows
                if not q or q in str(d.get("narrative", "")).lower()]
        if not hits:
            return "（摘要中无匹配）"
        lines = []
        for d in hits:
            lines.append(f"{d.get('narrative', '')}（覆盖轮 {self._span_of(d)}）")
        return "\n".join(lines)

    async def _view_rounds(self, args: dict[str, Any]) -> str:
        ids = args.get("round_ids") or []
        if isinstance(ids, str):
            ids = [ids]
        if not ids:
            return "（未提供 round_id）"
        out = []
        for rid in ids:
            rec = self.session.store.read(self.session.id, "rounds", str(rid))
            out.append(_fmt_round(rec) if rec else f"（未找到轮 {rid}）")
        return "\n\n".join(out)

    async def _search_rounds(self, args: dict[str, Any]) -> str:
        q = str(args.get("query", "") or "").strip().lower()
        if not q:
            return "（缺少检索关键词）"
        rows = self.session.store.query(self.session.id, "rounds", order="asc")
        hits = [r for r in rows
                if q in str(r.get("user", "")).lower()
                or q in str(r.get("ai", "")).lower()]
        if not hits:
            return "（原文中无匹配）"
        return "\n\n".join(_fmt_round(r) for r in hits[-20:])

    async def _round_window(self, args: dict[str, Any]) -> str:
        rid = str(args.get("round_id", "") or "")
        rows = self.session.store.query(self.session.id, "rounds", order="asc")
        idx = next((i for i, r in enumerate(rows) if str(r.get("id")) == rid), None)
        if idx is None:
            return f"（未找到轮 {rid}）"
        window = rows[max(0, idx - 1): idx + 2]
        return "\n\n".join(_fmt_round(r) for r in window)


# ---------------------------------------------------------------------------
# 日记记忆：只追加，AI 自主写入不可遗忘的关键事实
# ---------------------------------------------------------------------------

class DiaryMemory(Memory):
    """「绝不能忘记」的日记：由 AI 判断何时写（工具描述带例子），只追加不覆盖。

    diary_write **即写**（进 elixir Store 内存，随定时 flush 落盘）——不依赖轮完成
    钩子，因此分析中被强断/出错的轮也不丢已确认写入的日记（「绝不遗忘」契约）。
    """

    def function_pack(self, role: RoleId) -> list[ToolSchema]:
        write = _schema(
            "diary_write",
            "把绝不能忘记的重要信息写入永久日记（只追加、不可覆盖删除）。"
            "只在出现必须长期记住的事实/约定时调用，例如：用户告知『我的生日是5月20日』→ "
            "diary_write('用户的生日是5月20日')；用户提到『父母已经去世，那天是2023年11月2日』→ "
            "diary_write('用户父母于2023年11月2日去世，忌日需要陪伴安抚')。不要写入闲聊内容。",
            {"type": "object",
             "properties": {"content": {"type": "string",
                                        "description": "要永久记住的事实（一句话）"}},
             "required": ["content"]},
        )
        read = _schema(
            "diary_read",
            "读取日记的全部内容（查询所有永久记住的关键事实）。",
            {"type": "object", "properties": {}},
        )
        return [write, read]

    async def run_tool(self, name: str, role: RoleId, **kwargs: Any) -> str | None:
        if name == "diary_write":
            content = str(kwargs.get("content", "") or "").strip()
            if not content:
                return "（日记内容为空，未写入）"
            await self.session.store.append(self.session.id, "diary", {
                "content": content,
                "date": date.today().isoformat(),
            })
            return "已永久记入日记。"
        if name == "diary_read":
            rows = self.session.store.query(self.session.id, "diary", order="asc")
            if not rows:
                return "（日记暂无内容）"
            out = []
            for d in rows:
                tag = f"，轮 {d['round_id']}" if d.get("round_id") else ""
                out.append(f"- {d.get('content', '')}（{d.get('date', '')}{tag}）")
            return "\n".join(out)
        return None
