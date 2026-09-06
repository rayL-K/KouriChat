"""LLM 层：会话工厂（Q15）。只做 key → Elixir Session，不定义新的 LLM 抽象。"""

from .factory import apply

__all__ = ["apply"]
