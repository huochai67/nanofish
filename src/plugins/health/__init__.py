from dataclasses import dataclass
from enum import StrEnum

import httpx
from nonebot import get_bots, get_plugin, on_command, require
from nonebot.adapters.onebot.v11 import Bot, MessageEvent
from nonebot.exception import FinishedException
from nonebot.plugin import PluginMetadata

from src.plugin_config import get_yaml_plugin_config
from src.proxy import get_http_proxy_for_url

from .config import Config

require("acl")
require("app")
require("utils")
from ..acl import require_command
from ..app import client as app_client
from ..app import config as app_config
from ..utils import (
    finish_processing_reply,
    get_globalconfig,
    http_error_message,
    log_http_trace,
    request_error_message,
    send_processing_reply,
)

__plugin_meta__ = PluginMetadata(
    name="health",
    description="深度健康检查（Bot / Playwright / 前端 / 配置依赖）",
    usage="/health",
    config=Config,
)

config: Config = get_yaml_plugin_config(Config, "health")

health = on_command(
    "health",
    priority=10,
    block=True,
    permission=require_command("health"),
)


class Status(StrEnum):
    OK = "ok"
    FAIL = "fail"
    SKIP = "skip"


@dataclass(frozen=True, slots=True)
class CheckResult:
    name: str
    status: Status
    detail: str


def _mark(status: Status) -> str:
    if status is Status.OK:
        return "✓"
    if status is Status.FAIL:
        return "✗"
    return "—"


def check_bots() -> CheckResult:
    bots = get_bots()
    if not bots:
        return CheckResult("Bot", Status.FAIL, "无已连接实例")
    ids = ", ".join(str(bot_id) for bot_id in bots)
    return CheckResult("Bot", Status.OK, f"{len(bots)} 个连接 ({ids})")


def check_playwright() -> CheckResult:
    browser = app_client.browser
    context = app_client.context
    if browser is None or context is None:
        return CheckResult("Playwright", Status.FAIL, "browser/context 未初始化")
    try:
        connected = browser.is_connected()
    except Exception as e:  # noqa: BLE001
        return CheckResult("Playwright", Status.FAIL, f"无法查询连接状态: {e}")
    if not connected:
        return CheckResult("Playwright", Status.FAIL, "browser 未连接")
    return CheckResult("Playwright", Status.OK, "browser 已连接")


async def check_frontend() -> CheckResult:
    base = app_config.app_api_base.rstrip("/")
    if not base:
        return CheckResult("前端", Status.FAIL, "APP_API_BASE 未配置")
    try:
        async with httpx.AsyncClient(
            proxy=get_http_proxy_for_url(base),
            timeout=config.health_http_timeout,
            follow_redirects=True,
        ) as http:
            response = await http.get(base)
        if get_globalconfig().http_trace:
            log_http_trace("health", response)
        return CheckResult(
            "前端",
            Status.OK if response.is_success else Status.FAIL,
            (
                f"HTTP {response.status_code} ({base})"
                if response.is_success
                else request_error_message(status=response.status_code)
            ),
        )
    except httpx.HTTPError as e:
        return CheckResult("前端", Status.FAIL, http_error_message(e))


def _plugin_config(
    plugin_id: str,
    attr: str = "config",
) -> object | None:
    plugin = get_plugin(plugin_id)
    if plugin is None or plugin.module is None:
        return None
    return getattr(plugin.module, attr, None)


def check_llm() -> CheckResult:
    cfg = _plugin_config("llm")
    if cfg is None:
        return CheckResult("LLM", Status.SKIP, "插件未加载")
    model = getattr(cfg, "model", None)
    api_key = getattr(cfg, "openai_api_key", None)
    api_base = getattr(cfg, "openai_api_base", None)
    missing: list[str] = []
    if not model:
        missing.append("model")
    if not api_key:
        missing.append("openai_api_key")
    if not api_base:
        missing.append("openai_api_base")
    if missing:
        return CheckResult("LLM", Status.FAIL, f"缺少配置: {', '.join(missing)}")
    return CheckResult("LLM", Status.OK, f"已配置 model={model}")


_MIN_EHTAG_DICT_BYTES = 1024


async def check_eh_tags() -> CheckResult:
    """Tag dict is served by the Next frontend (public/ehtag-dict.json)."""
    base = app_config.app_api_base.rstrip("/")
    if not base:
        return CheckResult("EH 标签表", Status.FAIL, "APP_API_BASE 未配置")
    url = f"{base}/ehtag-dict.json"
    try:
        async with httpx.AsyncClient(
            proxy=get_http_proxy_for_url(url),
            timeout=config.health_http_timeout,
            follow_redirects=True,
        ) as http:
            response = await http.get(url)
        if get_globalconfig().http_trace:
            log_http_trace("health", response)
        if not response.is_success:
            return CheckResult(
                "EH 标签表",
                Status.FAIL,
                request_error_message(status=response.status_code),
            )
        # lightweight sanity check without full parse cost on huge body
        size = len(response.content)
        if size < _MIN_EHTAG_DICT_BYTES:
            return CheckResult("EH 标签表", Status.FAIL, f"响应过短 ({size} B)")
        return CheckResult("EH 标签表", Status.OK, f"可用 ({size // 1024} KB)")
    except httpx.HTTPError as e:
        return CheckResult("EH 标签表", Status.FAIL, http_error_message(e))


def check_sightengine() -> CheckResult:
    cfg = _plugin_config("genai_detect")
    if cfg is None:
        return CheckResult("Sightengine", Status.SKIP, "插件未加载")
    user = getattr(cfg, "sightengine_api_user", None)
    secret = getattr(cfg, "sightengine_api_secret", None)
    missing: list[str] = []
    if not user:
        missing.append("sightengine_api_user")
    if not secret:
        missing.append("sightengine_api_secret")
    if missing:
        return CheckResult(
            "Sightengine",
            Status.FAIL,
            f"缺少配置: {', '.join(missing)}",
        )
    return CheckResult("Sightengine", Status.OK, "已配置")


def format_results(results: list[CheckResult]) -> str:
    lines = ["健康检查"]
    lines.extend(f"{_mark(item.status)} {item.name}: {item.detail}" for item in results)
    return "\n".join(lines)


@health.handle()
async def handle_function(bot: Bot, event: MessageEvent) -> None:
    processing = await send_processing_reply(health, bot, event, "正在检查，请稍候…")
    try:
        results: list[CheckResult] = [
            check_bots(),
            check_playwright(),
            await check_frontend(),
            check_llm(),
            await check_eh_tags(),
            check_sightengine(),
        ]
        await finish_processing_reply(
            health, processing, event, format_results(results)
        )
    except FinishedException:
        raise
    except Exception as e:  # noqa: BLE001
        await finish_processing_reply(
            health,
            processing,
            event,
            f"健康检查失败: {type(e).__name__}: {e}",
        )
