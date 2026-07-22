"""Apply Nanofish ACL policy before third-party parser matchers run."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from re import Pattern

from nonebot import on_message, require
from nonebot.adapters.onebot.v11 import MessageEvent  # noqa: TC002
from nonebot.matcher import matchers
from nonebot.plugin import PluginMetadata
from nonebot.rule import Rule

require("acl")
require("nonebot_plugin_parser")

from nonebot_plugin_parser.config import pconfig
from nonebot_plugin_parser.matchers.rule import keyword_regex
from nonebot_plugin_parser.parsers import BaseParser

from ..acl.service import event_allows, perm_for_command, require_command

__plugin_meta__ = PluginMetadata(
    name="parser_acl",
    description="为链接解析插件应用 Nanofish ACL 范围和角色策略",
    usage="由 nonebot_plugin_parser 自动使用",
)

_PARSER_PLUGIN = "nonebot_plugin_parser"
_PARSER_MATCHER_MODULE = "nonebot_plugin_parser.matchers"
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

for _registered_matchers in matchers.values():
    for _matcher in _registered_matchers:
        if (
            _matcher.plugin_name == _PARSER_PLUGIN
            and _matcher.module_name == _PARSER_MATCHER_MODULE
            and _matcher.priority == _PARSER_COMMAND_PRIORITY
        ):
            _matcher.permission = require_command("parser")


@_parser_guard.handle()
async def _block_parser() -> None:
    pass
