"""ACL: roles, scope, quota, and /auth management."""

from __future__ import annotations

from nonebot import get_plugin_config, logger, on_command, require
from nonebot.adapters.onebot.v11 import Message, MessageEvent
from nonebot.matcher import Matcher
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata

require("nonebot_plugin_localstore")

from . import commands as auth_cmds
from .config import Config
from .quota import quota_tracker
from .roles import ROLE_ORDER, Role
from .service import (
    check_quota,
    consume_quota,
    ensure_quota,
    event_allows,
    get_group_id,
    get_user_id,
    is_blacklisted,
    is_superuser,
    perm_for_command,
    require_command,
    require_level,
    resolve_role,
    scope_allows,
)
from .store import acl_store

__plugin_meta__ = PluginMetadata(
    name="acl",
    description="角色权限 / 群范围 / 配额限流 / 运行时授权",
    usage=(
        "/auth whoami | list | set <qq> <role> | unset <qq> | "
        "ban <qq> | unban <qq> | group enable|disable|reset [群号] | quota [cmd]"
    ),
    config=Config,
)

config: Config = get_plugin_config(Config)

acl_store.load()
quota_tracker.load()
logger.info(
    "[acl] loaded "
    f"(admins={len(config.acl_admins)}, "
    f"groups_whitelist={len(config.acl_allowed_groups) or 'all'}, "
    f"private={config.acl_allow_private})"
)

auth = on_command("auth", priority=5, block=True)


async def _dispatch_auth(
    matcher: Matcher,
    event: MessageEvent,
    sub: str,
    rest: list[str],
) -> None:
    if sub in {"whoami", "me", "i"}:
        await auth_cmds.cmd_whoami(matcher, event)
        return
    if sub == "quota":
        await auth_cmds.cmd_quota(matcher, event, rest)
        return
    if sub == "help":
        await auth_cmds.cmd_help(matcher)
        return

    if not auth_cmds.can_manage(event, config):
        if scope_allows(event):
            await matcher.finish("权限不足")
        await matcher.finish()
        return

    managed = {
        "list": lambda: auth_cmds.cmd_list(matcher, config),
        "set": lambda: auth_cmds.cmd_set(matcher, event, rest),
        "unset": lambda: auth_cmds.cmd_unset(matcher, rest),
        "ban": lambda: auth_cmds.cmd_ban(matcher, rest),
        "unban": lambda: auth_cmds.cmd_unban(matcher, rest),
        "group": lambda: auth_cmds.cmd_group(matcher, event, rest),
    }
    handler = managed.get(sub)
    if handler is None:
        await matcher.finish("未知子命令，发送 /auth help")
        return
    await handler()


@auth.handle()
async def handle_auth(
    matcher: Matcher,
    event: MessageEvent,
    args: Message = CommandArg(),
) -> None:
    parts = args.extract_plain_text().strip().split()
    sub = parts[0].lower() if parts else "whoami"
    await _dispatch_auth(matcher, event, sub, parts[1:])


__all__ = [
    "ROLE_ORDER",
    "Role",
    "check_quota",
    "config",
    "consume_quota",
    "ensure_quota",
    "event_allows",
    "get_group_id",
    "get_user_id",
    "is_blacklisted",
    "is_superuser",
    "perm_for_command",
    "require_command",
    "require_level",
    "resolve_role",
    "scope_allows",
]
