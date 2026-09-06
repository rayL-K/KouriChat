"""WebUI 控制台插件（ticket 17）：aiohttp 静态服务 + 控制台 JSON API。

- 随 `kourichat run` 以插件形式启动（kourichat.toml `[[plugins]] module="kourichat.webui"`）；
- 静态托管 Vue 控制台（`static_dir`，缺省 ./frontend/dist；未构建时返回占位说明）；
- JSON API 对接 `adapter.openclaw` 服务（T13 契约）：
  status / login / relogin / logout（本地标记）/ chat send+mock / logs / config；
- 日志环形缓冲：loguru sink 捕获（本插件装配后追加，不替换既有 handler）。
"""

from __future__ import annotations

import collections
import json
import threading
import time
import tomllib
from pathlib import Path
from typing import Any

try:
    from loguru import logger as _loguru
except ImportError:  # pragma: no cover
    _loguru = None

try:
    from aiohttp import web
except ImportError:  # pragma: no cover
    web = None  # type: ignore[assignment]

from ..event import MESSAGE_RECEIVE
from ..types import Channel, Message, Segment, User

# 静态目录：优先包内 static/（wheel 打包时由 build 脚本填充 frontend/dist 产物），
# 也允许用户用 static_dir 配置覆盖为任意目录。
DEFAULT_STATIC_DIR = str(Path(__file__).resolve().parent / "static")
DEFAULT_LOG_LINES = 500

_LOG_LEVELS = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3}


def _require_aiohttp() -> None:
    if web is None:
        raise RuntimeError(
            "webui 插件需要 aiohttp：请先安装依赖（uv sync 或 pip install aiohttp）")


class LogBuffer:
    """loguru sink 环形缓冲：供 /api/logs 轮询。"""

    def __init__(self, max_lines: int = DEFAULT_LOG_LINES) -> None:
        self._buf: collections.deque[dict[str, Any]] = collections.deque(
            maxlen=max(10, max_lines))
        self._lock = threading.Lock()

    def sink(self, message: Any) -> None:
        rec = message.record
        with self._lock:
            self._buf.append({
                "time": rec["time"].isoformat(),
                "level": rec["level"].name,
                "line": str(message),
            })

    def snapshot(self, limit: int = 100, level: str = "DEBUG",
                 skip: int = 0) -> list[dict[str, Any]]:
        """按级别过滤后返回日志（新→旧）；skip 跳过最新 skip 条（懒加载更早）。"""
        min_level = _LOG_LEVELS.get(str(level).upper(), 0)
        with self._lock:
            rows = [r for r in self._buf
                    if _LOG_LEVELS.get(r["level"], 0) >= min_level]
        all_rows = list(reversed(rows))
        return all_rows[skip: skip + max(1, limit)]


# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------

def _json(data: Any, status: int = 200) -> web.Response:
    return web.json_response(data, status=status)


def _adapter(ctx: Any) -> Any:
    adapter = ctx.get("adapter.openclaw")
    if adapter is None:
        raise web.HTTPBadRequest(
            text=json.dumps({"ok": False,
                             "error": "adapter.openclaw not loaded"}),
            content_type="application/json")
    return adapter


async def _read_body(request: web.Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except Exception:
        raise web.HTTPBadRequest(
            text=json.dumps({"ok": False, "error": "body must be JSON"}),
            content_type="application/json")
    if not isinstance(body, dict):
        raise web.HTTPBadRequest(
            text=json.dumps({"ok": False, "error": "body must be a JSON object"}),
            content_type="application/json")
    return body


async def api_status(request: web.Request) -> web.Response:
    return _json(await _adapter(request.app["ctx"]).status())


async def api_login(request: web.Request) -> web.Response:
    body = await _read_body(request)
    account_id = str(body.get("accountId") or "") or None
    return _json(await _adapter(request.app["ctx"]).start_login(account_id))


async def api_relogin(request: web.Request) -> web.Response:
    body = await _read_body(request)
    account_id = str(body.get("accountId") or "")
    if not account_id:
        return _json({"ok": False, "error": "accountId is required"}, 400)
    return _json(await _adapter(request.app["ctx"]).relogin(account_id))


async def api_logout(request: web.Request) -> web.Response:
    body = await _read_body(request)
    account_id = str(body.get("accountId") or "")
    if not account_id:
        return _json({"ok": False, "error": "accountId is required"}, 400)
    await _adapter(request.app["ctx"]).logout_local(account_id)
    return _json({"ok": True, "note":
                  "已本地标记登出；网关侧凭据请用 weixin-gateway logout <id> 清理"})


async def api_chat_send(request: web.Request) -> web.Response:
    body = await _read_body(request)
    channel_id = str(body.get("channel_id") or "")
    text = str(body.get("text") or "")
    if not channel_id or not text:
        return _json({"ok": False, "error": "channel_id and text are required"}, 400)
    # 网关仅支持私聊（一对一微信消息）；群聊发送未落地，只接受 private
    adapter = _adapter(request.app["ctx"])
    from ..types import OutMessage
    mid = await adapter.send(OutMessage(
        channel=Channel(platform="openclaw", channel_id=channel_id,
                        channel_type="private"),
        segments=[Segment("text", {"text": text})]))
    if not mid:
        return _json({"ok": False,
                      "error": "发送失败（网关未返回 message_id）——请确认目标 user_id 是"\
                               "真实微信用户（微信 ret=-3 invalid arguments）"}, 400)
    return _json({"ok": True, "message_id": mid})


async def api_chat_mock(request: web.Request) -> web.Response:
    """注入一条假消息进事件链（走完整逻辑链；无 llm.factory 时仅日志）。"""
    body = await _read_body(request)
    text = str(body.get("text") or "")
    if not text:
        return _json({"ok": False, "error": "text is required"}, 400)
    # 网关仅私聊；注入统一走 private
    ctx = request.app["ctx"]
    events = ctx.get("events")
    msg = Message(
        id=f"webui-mock-{time.time_ns()}",
        channel=Channel(platform="openclaw", channel_id="webui-mock",
                        channel_type="private"),
        sender=User(user_id="webui", name="webui"),
        segments=[Segment("text", {"text": text})],
        ts=time.time(),
        raw={"mock": True},
    )
    await events.emit(MESSAGE_RECEIVE, msg)
    return _json({"ok": True, "emitted": True})


async def api_logs(request: web.Request) -> web.Response:
    limit = int(request.query.get("limit", "100") or 100)
    level = str(request.query.get("level", "DEBUG") or "DEBUG")
    skip = int(request.query.get("skip", "0") or 0)
    buf = request.app["logbuf"]
    return _json({"logs": buf.snapshot(limit=limit, level=level, skip=skip)})


def _config_service(ctx: Any) -> Any:
    cfg = ctx.get("config")
    if cfg is None:
        raise web.HTTPBadRequest(
            text=json.dumps({"ok": False,
                             "error": "config service not loaded"}),
            content_type="application/json")
    return cfg


# ---------------------------------------------------------------------------
# 结构化配置（表单 + 即时保存）、dashboard、首次运行判定
# ---------------------------------------------------------------------------

OPENCLAW_MODULE = "kourichat.adapter.openclaw"
LLM_MODULE = "kourichat.llm.factory"
WEBUI_MODULE = "kourichat.webui"
PERSONA_MODULE = "kourichat.logic.persona"
ECHO_MODULE = "kourichat.logic.echo"

# 表单可编辑字段：section -> {key: 默认值}（仅暴露这些，其余字段在文件中保持不变）
SETTINGS_FIELDS: dict[str, dict[str, Any]] = {
    "core": {"log_level": "INFO"},
    "openclaw": {"gateway_url": "http://127.0.0.1:8765",
                 "access_token": "", "data_dir": "./data",
                 "autologin": True, "poll_interval": 2.0},
    "llm": {"base_url": "https://api.openai.com/v1", "api_key": "",
            "model": "gpt-4o-mini", "data_dir": "./data"},
    "webui": {"host": "127.0.0.1", "port": 8080},
    "persona": {"personas_dir": "./personas", "enable": ""},
    "echo": {"enabled": True},
}


def _fmt_toml(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{s}"'


def _emit_scalar(lines: list[str], key: str, val: Any) -> None:
    if isinstance(val, dict):  # 单层内联表（如 role_prompt_overrides）
        inner = ", ".join(f"{k} = {_fmt_toml(v)}" for k, v in val.items())
        lines.append(f"{key} = {{ {inner} }}")
    else:
        lines.append(f"{key} = {_fmt_toml(val)}")


def _toml_dump(data: dict[str, Any]) -> str:
    """按 kourichat 配置形态序列化：顶层 scalar 段 + 数组表(带 config 子表/内联表)。"""
    lines: list[str] = []
    for key, val in data.items():
        if isinstance(val, dict):
            lines.append(f"[{key}]")
            for k, v in val.items():
                _emit_scalar(lines, k, v)
            lines.append("")
        elif isinstance(val, list):
            for item in val:
                if not isinstance(item, dict):
                    continue
                lines.append(f"[[{key}]]")
                for k, v in item.items():
                    if isinstance(v, dict):  # config 子表
                        lines.append(f"[{key}.{k}]")
                        for kk, vv in v.items():
                            _emit_scalar(lines, kk, vv)
                        lines.append("")
                    else:
                        _emit_scalar(lines, k, v)
                lines.append("")
        else:
            _emit_scalar(lines, key, val)
    return "\n".join(lines).rstrip("\n") + "\n"


def _load_config_data(cfg: Any) -> dict[str, Any]:
    path = Path(cfg.path)
    if not path.exists():
        return {}
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def _is_first_run(cfg: Any) -> bool:
    """首启判定：config 文件内容与内置模板完全一致。"""
    path = Path(cfg.path)
    if not path.exists():
        return True
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return True
    try:
        from ..main import TEMPLATE
    except Exception:
        return False
    return text == TEMPLATE.strip()


def _entry_by_module(data: dict[str, Any], list_key: str,
                     module: str) -> dict[str, Any] | None:
    for it in data.get(list_key, []):
        if isinstance(it, dict) and it.get("module") == module:
            return it
    return None


def _upsert_config(data: dict[str, Any], list_key: str, module: str,
                   cfg: dict[str, Any]) -> None:
    if not cfg:
        return
    entry = _entry_by_module(data, list_key, module)
    if entry is None:
        entry = {"module": module, "config": {}}
        data.setdefault(list_key, []).append(entry)
    entry.setdefault("config", {})
    for k, v in cfg.items():
        entry["config"][k] = v


def _project_settings(data: dict[str, Any]) -> dict[str, Any]:
    core = data.get("core") or {}
    def proj(section: str, list_key: str, module: str,
             defaults: dict[str, Any]) -> dict[str, Any]:
        entry = _entry_by_module(data, list_key, module)
        cfg = (entry or {}).get("config") or {}
        return {k: cfg.get(k, d) for k, d in defaults.items()}
    return {
        "core": {k: core.get(k, d) for k, d in SETTINGS_FIELDS["core"].items()},
        "openclaw": proj("openclaw", "adapters", OPENCLAW_MODULE,
                         SETTINGS_FIELDS["openclaw"]),
        "llm": proj("llm", "plugins", LLM_MODULE, SETTINGS_FIELDS["llm"]),
        "webui": proj("webui", "plugins", WEBUI_MODULE, SETTINGS_FIELDS["webui"]),
        "persona": proj("persona", "plugins", PERSONA_MODULE,
                        SETTINGS_FIELDS["persona"]),
        "echo": proj("echo", "plugins", ECHO_MODULE, SETTINGS_FIELDS["echo"]),
    }


def _apply_settings(data: dict[str, Any], fields: dict[str, Any]) -> None:
    core = data.setdefault("core", {})
    for k, v in (fields.get("core") or {}).items():
        core[k] = v
    _upsert_config(data, "adapters", OPENCLAW_MODULE, fields.get("openclaw"))
    _upsert_config(data, "plugins", LLM_MODULE, fields.get("llm"))
    _upsert_config(data, "plugins", WEBUI_MODULE, fields.get("webui"))
    _upsert_config(data, "plugins", PERSONA_MODULE, fields.get("persona"))
    _upsert_config(data, "plugins", ECHO_MODULE, fields.get("echo"))


async def api_settings_get(request: web.Request) -> web.Response:
    cfg = _config_service(request.app["ctx"])
    return _json({"ok": True, "fields": _project_settings(
        _load_config_data(cfg))})


async def _reload_llm_factory(ctx: Any, llm_cfg: dict[str, Any]) -> bool:
    """运行时重启 llm.factory 组件（dispose 旧 fiber → 新配置重新 plugin）。

    会话记忆经 elixir Store 持久化，重载后新 Session 从磁盘恢复，不丢记忆。
    """
    import importlib
    fiber = None
    for entry in ctx.root._services.values():
        if getattr(entry, "name", None) == "llm.factory":
            fiber = entry.provider
            break
    old = dict(fiber.config or {}) if fiber is not None else {}
    new_cfg = {**old, **(llm_cfg or {})}
    if fiber is not None:
        await fiber.dispose()
    module = importlib.import_module("kourichat.llm.factory")
    apply = getattr(module, "apply", None)
    if apply is None:
        return False
    new_fiber = ctx.plugin(apply, new_cfg)
    await new_fiber.wait()
    return True


async def api_settings_post(request: web.Request) -> web.Response:
    cfg = _config_service(request.app["ctx"])
    body = await _read_body(request)
    fields = body.get("fields")
    if not isinstance(fields, dict):
        return _json({"ok": False, "error": "fields is required"}, 400)
    data = _load_config_data(cfg)
    _apply_settings(data, fields)
    content = _toml_dump(data)
    try:
        tomllib.loads(content)
    except tomllib.TOMLDecodeError as exc:
        return _json({"ok": False, "error": f"TOML 校验失败: {exc}"}, 400)
    path = Path(cfg.path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)
    # 热更新运行中的 openclaw 适配器（引导页/设置页保存后立即生效，无需重启）
    adapter = request.app["ctx"].get("adapter.openclaw")
    oc = fields.get("openclaw") or {}
    if adapter is not None:
        try:
            adapter.update_gateway(gateway_url=oc.get("gateway_url"),
                                   access_token=oc.get("access_token"))
        except Exception:
            pass  # 适配器无此方法时忽略（旧版本）
    # LLM 配置变更 → 运行时重启 llm.factory 组件（新 key/model 立即生效）
    notes: list[str] = ["已保存"]
    if fields.get("llm"):
        try:
            if await _reload_llm_factory(request.app["ctx"], fields["llm"]):
                notes.append("LLM 组件已热重载")
            else:
                notes.append("llm.factory 未装配，跳过热重载")
        except Exception as exc:
            notes.append(f"LLM 热重载失败: {exc}")
    return _json({"ok": True, "note": "；".join(notes)})


async def api_llm_reload(request: web.Request) -> web.Response:
    """显式热重载 llm.factory：用当前配置文件里的 LLM 设置重启组件。"""
    ctx = request.app["ctx"]
    cfg = ctx.get("config")
    llm: dict[str, Any] = {}
    if cfg is not None:
        llm = _project_settings(_load_config_data(cfg))["llm"]
    try:
        if await _reload_llm_factory(ctx, llm):
            return _json({"ok": True, "note": "LLM 组件已热重载（新配置已生效）"})
        return _json({"ok": False, "error": "llm.factory 未装配，无法重载"}, 400)
    except Exception as exc:
        return _json({"ok": False, "error": f"LLM 热重载失败: {exc}"}, 400)


async def api_llm_test(request: web.Request) -> web.Response:
    """用当前 LLM 配置发一条最小 chat 请求，验证连通性。"""
    import urllib.error
    import urllib.request

    body = await _read_body(request)
    cfg = request.app["ctx"].get("config")
    llm = body.get("llm") or {}
    if cfg is not None:
        cur = _project_settings(_load_config_data(cfg))["llm"]
        llm = {k: llm.get(k, cur.get(k)) for k in cur}
    base_url = str(llm.get("base_url") or "").rstrip("/")
    api_key = str(llm.get("api_key") or "")
    model = str(llm.get("model") or "")
    if not base_url or not api_key or not model:
        return _json({"ok": False, "error": "请先填写 base_url / api_key / model"}, 400)
    url = base_url + "/chat/completions"
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 4,
    }).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {api_key}"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        text = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
        return _json({"ok": True, "reply": text, "model": model,
                      "note": "LLM 连通正常"})
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        return _json({"ok": False, "error": f"HTTP {exc.code}: {detail}"}, 400)
    except Exception as exc:
        return _json({"ok": False, "error": f"连接失败: {exc}"}, 400)


async def api_setup_status(request: web.Request) -> web.Response:
    cfg = request.app["ctx"].get("config")
    first_run = _is_first_run(cfg) if cfg is not None else True
    return _json({"ok": True, "first_run": first_run})


async def api_dashboard(request: web.Request) -> web.Response:
    ctx = request.app["ctx"]
    adapter = ctx.get("adapter.openclaw")
    connected = False
    accounts: list[dict[str, Any]] = []
    login = None
    if adapter is not None:
        st = await adapter.status()
        connected = st["connected"]
        accounts = st["accounts"]
        login = st["login"]
    registry = ctx.get("persona.registry") or {}
    active = ctx.get("persona.active")
    cfg = ctx.get("config")
    return _json({
        "connected": connected,
        "accounts": accounts,
        "login": login,
        "personas": {"count": len(registry),
                     "active": getattr(active, "id", None) if active else None},
        "first_run": _is_first_run(cfg) if cfg is not None else True,
    })


async def _serve_static(request: web.Request) -> web.Response:
    root = Path(request.app["static_dir"])
    if not (root / "index.html").exists():
        return web.Response(
            text="前端未构建：请在仓库 frontend/ 目录执行 npm run build"
                 "（或配置 static_dir 指向构建产物）",
            content_type="text/plain", charset="utf-8")
    tail = request.match_info.get("tail", "")
    target = (root / tail).resolve() if tail else root / "index.html"
    # 防目录穿越：目标必须位于 static_dir 内
    if root.resolve() not in target.parents and target != root.resolve():
        target = root / "index.html"
    if tail and target.is_file():
        return web.FileResponse(target)
    return web.FileResponse(root / "index.html")


# ---------------------------------------------------------------------------
# 插件入口
# ---------------------------------------------------------------------------

async def build_app(ctx: Any, config: dict[str, Any] | None = None) -> Any:
    """构造 aiohttp app（不启动）；供 apply 与测试复用。"""
    _require_aiohttp()
    cfg = config or {}
    app = web.Application()
    app["ctx"] = ctx
    app["static_dir"] = str(cfg.get("static_dir", DEFAULT_STATIC_DIR))
    app["logbuf"] = LogBuffer(int(cfg.get("log_lines", DEFAULT_LOG_LINES)))

    # API 路由必须先注册，避免被静态 catch-all 吞掉
    app.router.add_get("/api/openclaw/status", api_status)
    app.router.add_post("/api/openclaw/login", api_login)
    app.router.add_post("/api/openclaw/relogin", api_relogin)
    app.router.add_post("/api/openclaw/logout", api_logout)
    app.router.add_post("/api/chat/send", api_chat_send)
    app.router.add_post("/api/chat/mock", api_chat_mock)
    app.router.add_get("/api/logs", api_logs)
    app.router.add_get("/api/settings", api_settings_get)
    app.router.add_post("/api/settings", api_settings_post)
    app.router.add_post("/api/llm/test", api_llm_test)
    app.router.add_post("/api/llm/reload", api_llm_reload)
    app.router.add_get("/api/setup/status", api_setup_status)
    app.router.add_get("/api/dashboard", api_dashboard)
    app.router.add_get("/", _serve_static)
    app.router.add_get("/{tail:.*}", _serve_static)
    return app


async def apply(ctx: Any, config: dict[str, Any] | None = None) -> Any:
    """挂载 webui 插件：启动 aiohttp 站点 + 日志 sink；返回 dispose。"""
    _require_aiohttp()
    cfg = config or {}
    host = str(cfg.get("host", "127.0.0.1"))
    port = int(cfg.get("port", 8080))
    app = await build_app(ctx, config)
    if _loguru is not None:
        sink_id = _loguru.add(app["logbuf"].sink, level="DEBUG")
    else:
        sink_id = None

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    ctx.provide("webui.app", app)
    logger = ctx.get("logger")
    if logger is not None:
        logger.info("webui started", host=host, port=port)

    async def dispose() -> None:
        if sink_id is not None and _loguru is not None:
            _loguru.remove(sink_id)
        await runner.cleanup()

    return dispose
