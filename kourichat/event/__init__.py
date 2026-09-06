"""事件层：标准事件常量（字符串，ticket 05 决策）+ 装饰器订阅 API。

事件链（Q8）：
    adapter → MESSAGE_RECEIVE →（前置修饰器）→ command 识别
            → COMMAND_RECEIVE → command 处理器
            → 未 stop() 则续发 MESSAGE_PRIVATE / MESSAGE_GROUP → 会话处理

所有事件订阅一律装饰器形式（@on_message/@on_command/@on_notice/@on_request），
插件 `apply(ctx)` 里调 `register_module_handlers(ctx, namespace)` 统一注册/注销。
"""

from .context import EventContext
from .decorator import (
    on_command,
    on_message,
    on_notice,
    on_request,
    register_module_handlers,
)
from .dispatcher import Dispatcher

MESSAGE_RECEIVE = "message.receive"
COMMAND_RECEIVE = "command.receive"
MESSAGE_PRIVATE = "message.private"
MESSAGE_GROUP = "message.group"
NOTICE_RECEIVE = "notice.receive"
REQUEST_RECEIVE = "request.receive"

__all__ = [
    "EventContext",
    "Dispatcher",
    "on_message",
    "on_command",
    "on_notice",
    "on_request",
    "register_module_handlers",
    "MESSAGE_RECEIVE",
    "COMMAND_RECEIVE",
    "MESSAGE_PRIVATE",
    "MESSAGE_GROUP",
    "NOTICE_RECEIVE",
    "REQUEST_RECEIVE",
]
