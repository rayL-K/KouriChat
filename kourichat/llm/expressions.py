"""人设表情包工具：模型获取可用表情列表 + 挑选要随本轮回复发送的表情。

选中的表情写入 per-session 的 holder（session._kouri_expr），由逻辑层在回复
**自然结束**后经 adapter 发送 image 段；若期间被加话/强断打断，逻辑层清空 holder
（本轮表情不发送，见 logic/session 说明）。
"""

from __future__ import annotations

from typing import Any

from elixir.tools import Tool

from ..persona import Expression


class ExpressionListTool(Tool):
    """list_expressions：列出该人设当前可用的表情包（id + 给 AI 的解释）。"""

    name = "list_expressions"
    description = "获取人设当前可用的表情包列表（每个含 id 与适用说明）。"
    parameters: dict[str, Any] = {"type": "object", "properties": {}}

    def __init__(self, expressions: list[Expression]) -> None:
        super().__init__()
        self._exprs = expressions

    async def run(self, **kwargs: Any) -> str:
        if not self._exprs:
            return "（本会话人设暂无表情包）"
        return "\n".join(
            f"{e.id}：{e.description or e.path}" for e in self._exprs)


class ExpressionSendTool(Tool):
    """send_expression：挑选表情，随本轮对话自然结束后发送。"""

    name = "send_expression"
    description = ("选择一个表情随本轮回复发送。先调用 list_expressions 查看可用表情，"
                   "再按 id 选择；若本轮被用户打断则不会发送。")
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {"expression_id": {"type": "string", "description": "表情 id"}},
        "required": ["expression_id"],
    }

    def __init__(self, holder: dict[str, Any],
                 expressions: list[Expression]) -> None:
        super().__init__()
        self._holder = holder
        self._by_id = {e.id: e for e in expressions}

    async def run(self, **kwargs: Any) -> str:
        eid = str(kwargs.get("expression_id", "") or "").strip()
        expr = self._by_id.get(eid)
        if expr is None:
            return f"（无此表情 id：{eid}，可先用 list_expressions 查看）"
        self._holder["expr"] = {
            "id": expr.id,
            "path": expr.abs_path,
            "description": expr.description,
        }
        return f"已选择表情 {expr.id}（{expr.description or expr.path}），将在本轮回复结束后发送。"
