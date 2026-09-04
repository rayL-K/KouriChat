"""适配层（ticket 06）：平台适配器统一经 Adapter ABC，入向发 MESSAGE_RECEIVE。"""

from .base import Adapter
from .cli import CliAdapter
from .onebot import OneBotV11Adapter

__all__ = ["Adapter", "CliAdapter", "OneBotV11Adapter"]
