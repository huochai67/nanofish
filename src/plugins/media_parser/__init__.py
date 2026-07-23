import asyncio
from re import Pattern
from typing import cast

from nonebot import logger, on_message, require
from nonebot.adapters.onebot.v11 import MessageEvent
from nonebot.matcher import matchers as matcher_registry
from nonebot.plugin import PluginMetadata, inherit_supported_adapters
from nonebot.rule import Rule

require("nonebot_plugin_alconna")
require("nonebot_plugin_uninfo")
require("app")
require("acl")

from ..acl.service import event_allows, perm_for_command, require_command
from .config import Config, pconfig
from .matchers import clear_result_cache
from .matchers.rule import keyword_regex
from .parsers import BaseParser
from .utils import safe_unlink

__plugin_meta__ = PluginMetadata(
    name="链接分享解析 Alconna 版",
    description="支持B站|抖音|快手|微博|小红书|YouTube|TikTok|Twitter|AcFun|NGA",
    usage=(
        "发送支持平台的(BV号/链接/小程序/卡片)即可\n"
        "其他命令:\n"
        "  bm BV号 <分集> (下载B站音频)\n"
        "  ym 链接 (下载油管音频)"
    ),
    type="application",
    homepage="https://github.com/fllesser/nonebot-plugin-parser",
    config=Config,
    supported_adapters=inherit_supported_adapters(
        "nonebot_plugin_alconna",
        "nonebot_plugin_uninfo",
    ),
    extra={
        "author": "fllesser",
        "email": "fllessive@gmail.com",
        "homepage": "https://github.com/fllesser/nonebot-plugin-parser",
    },
)

require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler

_PARSER_PLUGIN = "media_parser"
_PARSER_COMMAND_PRIORITY = 3


def _enabled_patterns() -> list[tuple[str, str | Pattern[str]]]:
    disabled_platforms = set(pconfig.disabled_platforms)
    patterns: list[tuple[str, str | Pattern[str]]] = []
    for parser_cls in BaseParser.get_all_subclass():
        if parser_cls.platform.name not in disabled_platforms:
            patterns.extend(
                cast(
                    "list[tuple[str, str | Pattern[str]]]",
                    parser_cls._key_patterns,
                )
            )
    return patterns


async def _outside_parser_acl(event: MessageEvent) -> bool:
    return not event_allows(event, perm_for_command("parser"))


_parser_guard = on_message(
    rule=Rule(_outside_parser_acl) & keyword_regex(*_enabled_patterns()),
    priority=4,
    block=True,
)

for _registered_matchers in matcher_registry.values():
    for _matcher in _registered_matchers:
        if (
            _matcher.plugin_name == _PARSER_PLUGIN
            and _matcher.module_name == "src.plugins.media_parser.matchers"
            and _matcher.priority == _PARSER_COMMAND_PRIORITY
        ):
            _matcher.permission = require_command("parser")


@_parser_guard.handle()
async def _block_parser() -> None:
    pass


@scheduler.scheduled_job("cron", hour=1, minute=0, id="parser-clean-local-cache")
async def clean_plugin_cache() -> None:
    try:
        files = [f for f in pconfig.cache_dir.iterdir() if f.is_file()]
        if not files:
            logger.info("No cache files to clean")
            return

        # 并发删除文件
        tasks = [safe_unlink(file) for file in files]
        await asyncio.gather(*tasks)

        logger.success(f"Successfully cleaned {len(files)} cache files")
    except Exception:  # noqa: BLE001
        logger.exception("Error while cleaning cache files")

    # 资源清理完毕后，清理 result 缓存
    clear_result_cache()
