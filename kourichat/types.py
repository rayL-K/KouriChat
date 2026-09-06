"""接入层统一数据模型（ticket 06 决策：Segment{type,data} OneBot v11 同构）。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Channel:
    platform: str  # "onebot-v11" | "openclaw" | "cli"
    channel_id: str  # 群号/频道号/会话 id
    channel_type: str = "private"  # "group" | "private" | "channel"


@dataclass
class User:
    user_id: str
    name: str = ""


@dataclass
class Segment:
    type: str  # "text" | "image" | "at" | "face" | ...
    data: dict = field(default_factory=dict)


@dataclass
class Message:
    id: str
    channel: Channel
    sender: User
    segments: list[Segment]
    ts: float
    raw: dict = field(default_factory=dict)


@dataclass
class OutMessage:
    channel: Channel
    segments: list[Segment]


def text_of(segments: list[Segment]) -> str:
    """拼接 text 段文本（消息入向/出向共用的文本提取）。"""
    return "".join(s.data.get("text", "") for s in segments if s.type == "text")
