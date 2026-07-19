from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import httpx
from nonebot import get_bots, get_plugin, get_plugin_config, on_command, require
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata

from .config import Config

require("app")
from ..app import client as app_client
from ..app import config as app_config

__plugin_meta__ = PluginMetadata(
    name="health",
    description="深度健康检查（Bot / Playwright / 前端 / 配置依赖）",
    usage="/health",
    config=Config,
)

config: Config = get_plugin_config(Config)

health = on_command("health", priority=10, block=True, permission=SUPERUSER)


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
            timeout=config.health_http_timeout,
            follow_redirects=True,
        ) as http:
            response = await http.get(base)
        return CheckResult(
            "前端",
            Status.OK if response.is_success else Status.FAIL,
            f"HTTP {response.status_code} ({base})",
        )
    except httpx.TimeoutException:
        return CheckResult("前端", Status.FAIL, f"超时 ({base})")
    except httpx.HTTPError as e:
        return CheckResult("前端", Status.FAIL, f"{type(e).__name__}: {e} ({base})")


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


def check_eh_db() -> CheckResult:
    cfg = _plugin_config("ehsearch")
    if cfg is None:
        return CheckResult("EH DB", Status.SKIP, "插件未加载")
    eh_db = getattr(cfg, "eh_db", None)
    if not eh_db:
        return CheckResult("EH DB", Status.FAIL, "eh_db 未配置")
    path = Path(str(eh_db))
    if not path.is_file():
        return CheckResult("EH DB", Status.FAIL, f"文件不存在 ({path})")
    return CheckResult("EH DB", Status.OK, f"存在 ({path})")


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
async def handle_function() -> None:
    results: list[CheckResult] = [
        check_bots(),
        check_playwright(),
        await check_frontend(),
        check_llm(),
        check_eh_db(),
        check_sightengine(),
    ]
    await health.finish(format_results(results))
