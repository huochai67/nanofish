"""/auth subcommand handlers."""

from __future__ import annotations

import re

from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageEvent
from nonebot.matcher import Matcher

from .config import Config
from .roles import Role
from .service import (
    check_quota,
    event_allows,
    get_group_id,
    get_user_id,
    is_blacklisted,
    is_superuser,
    perm_for_command,
    resolve_role,
    scope_allows,
)
from .store import acl_store

_AT_RE = re.compile(r"\[CQ:at,qq=(\d+)\]")
_VALID_SET_ROLES = (Role.GUEST, Role.USER, Role.ADMIN)
_SET_ARGS_MIN = 2
_GROUP_ARGS_WITH_ID = 2


def parse_target_uid(raw: str) -> int | None:
    text = raw.strip()
    if not text:
        return None
    at_m = _AT_RE.search(text)
    if at_m:
        return int(at_m.group(1))
    if text.isdigit():
        return int(text)
    for part in text.replace(",", " ").split():
        if part.isdigit():
            return int(part)
    return None


def can_manage(event: MessageEvent, config: Config) -> bool:
    uid = get_user_id(event)
    return event_allows(event, config.acl_perm_auth) or is_superuser(uid)


def role_summary(user_id: int) -> str:
    role = resolve_role(user_id)
    parts = [f"角色={role.label()}"]
    if is_blacklisted(user_id):
        parts.append("已拉黑")
    stored = acl_store.get_user_role(user_id)
    if stored is not None:
        parts.append(f"覆盖={stored.label()}")
    return "，".join(parts)


async def cmd_whoami(matcher: Matcher, event: MessageEvent) -> None:
    uid = get_user_id(event)
    gid = get_group_id(event)
    scope_ok = scope_allows(event)
    lines = [
        f"QQ: {uid}",
        role_summary(uid),
        f"范围: {'允许' if scope_ok else '拒绝'}"
        + (f"（群 {gid}）" if gid is not None else "（私聊）"),
    ]
    for cmd in ("llm", "draw", "genai", "eh", "imgsearch"):
        q = check_quota(event, cmd)
        if q.limit > 0:
            lines.append(f"/{cmd} 今日 {q.used}/{q.limit}")
        elif is_superuser(uid):
            lines.append(f"/{cmd} 无限制")
    await matcher.finish("\n".join(lines))


async def cmd_quota(matcher: Matcher, event: MessageEvent, rest: list[str]) -> None:
    cmd = rest[0].lower() if rest else "llm"
    if cmd not in {"llm", "draw", "genai", "eh", "imgsearch"}:
        await matcher.finish("用法: /auth quota [llm|draw|genai|eh|imgsearch]")
        return
    q = check_quota(event, cmd)
    if is_superuser(get_user_id(event)):
        await matcher.finish(f"/{cmd}: superuser 无限制")
        return
    if q.limit <= 0:
        await matcher.finish(f"/{cmd}: 未设置日配额")
        return
    await matcher.finish(f"/{cmd} 今日已用 {q.used}/{q.limit}")


async def cmd_help(matcher: Matcher) -> None:
    await matcher.finish(
        "用法:\n"
        "/auth whoami\n"
        "/auth quota [llm|draw|genai|eh|imgsearch]\n"
        "/auth list\n"
        "/auth set <qq|@> <guest|user|admin>\n"
        "/auth unset <qq|@>\n"
        "/auth ban|unban <qq|@>\n"
        "/auth group enable|disable|reset [群号]"
    )


async def cmd_list(matcher: Matcher, config: Config) -> None:
    lines = ["ACL 状态"]
    if config.acl_admins:
        lines.append("env admins: " + ", ".join(str(x) for x in config.acl_admins))
    if config.acl_user_whitelist:
        lines.append(
            "env user whitelist: "
            + ", ".join(str(x) for x in config.acl_user_whitelist)
        )
    if config.acl_blacklist:
        lines.append(
            "env blacklist: " + ", ".join(str(x) for x in config.acl_blacklist)
        )
    state = acl_store.state
    if state.users:
        lines.append("用户覆盖:")
        for uid, ov in sorted(state.users.items()):
            if ov.role is not None:
                lines.append(f"  {uid}: {ov.role.label()}")
    if state.blacklist:
        banned = ", ".join(str(x) for x in sorted(state.blacklist))
        lines.append(f"运行时黑名单: {banned}")
    if state.groups:
        lines.append("群覆盖:")
        for gid, ov in sorted(state.groups.items()):
            if ov.enabled is not None:
                flag = "enable" if ov.enabled else "disable"
                lines.append(f"  {gid}: {flag}")
    if config.acl_allowed_groups:
        lines.append(
            "群白名单: " + ", ".join(str(x) for x in config.acl_allowed_groups)
        )
    else:
        lines.append("群白名单: （不限制）")
    lines.append(f"私聊: {'允许' if config.acl_allow_private else '拒绝'}")
    rate_limits = ", ".join(
        f"{command}={getattr(config, f'acl_rate_limit_{command}_per_minute')}/分钟"
        for command in ("llm", "draw", "genai", "eh", "imgsearch")
    )
    lines.append(f"高成本命令每分钟限流: {rate_limits}")
    perms = ", ".join(
        f"{c}={perm_for_command(c).label()}"
        for c in (
            "jrrp",
            "llm",
            "draw",
            "genai",
            "eh",
            "imgsearch",
            "health",
            "auth",
        )
    )
    lines.append(f"命令门槛: {perms}")
    await matcher.finish("\n".join(lines))


async def cmd_set(
    matcher: Matcher,
    event: MessageEvent,
    rest: list[str],
) -> None:
    if len(rest) < _SET_ARGS_MIN:
        await matcher.finish("用法: /auth set <qq|@> <guest|user|admin>")
        return
    uid = parse_target_uid(rest[0])
    if uid is None:
        await matcher.finish("无法解析目标 QQ")
        return
    try:
        role = Role.parse(rest[1])
    except ValueError as e:
        await matcher.finish(str(e))
        return
    if role not in _VALID_SET_ROLES:
        await matcher.finish(
            "只能设置 guest/user/admin（superuser 请用 .env SUPERUSERS）"
        )
        return
    actor = get_user_id(event)
    if is_superuser(uid) and not is_superuser(actor):
        await matcher.finish("不能修改 superuser")
        return
    if not is_superuser(actor) and role is Role.ADMIN:
        await matcher.finish("只有 superuser 可授予 admin")
        return
    acl_store.set_user_role(uid, role)
    await matcher.finish(f"已设置 {uid} -> {role.label()}")


async def cmd_unset(matcher: Matcher, rest: list[str]) -> None:
    if not rest:
        await matcher.finish("用法: /auth unset <qq|@>")
        return
    uid = parse_target_uid(rest[0])
    if uid is None:
        await matcher.finish("无法解析目标 QQ")
        return
    acl_store.set_user_role(uid, None)
    await matcher.finish(f"已清除 {uid} 的角色覆盖")


async def cmd_ban(matcher: Matcher, rest: list[str]) -> None:
    if not rest:
        await matcher.finish("用法: /auth ban <qq|@>")
        return
    uid = parse_target_uid(rest[0])
    if uid is None:
        await matcher.finish("无法解析目标 QQ")
        return
    if is_superuser(uid):
        await matcher.finish("不能拉黑 superuser")
        return
    acl_store.ban(uid)
    await matcher.finish(f"已拉黑 {uid}")


async def cmd_unban(matcher: Matcher, rest: list[str]) -> None:
    if not rest:
        await matcher.finish("用法: /auth unban <qq|@>")
        return
    uid = parse_target_uid(rest[0])
    if uid is None:
        await matcher.finish("无法解析目标 QQ")
        return
    acl_store.unban(uid)
    await matcher.finish(f"已解除拉黑 {uid}")


async def cmd_group(
    matcher: Matcher,
    event: MessageEvent,
    rest: list[str],
) -> None:
    if not rest:
        await matcher.finish("用法: /auth group enable|disable|reset [群号]")
        return
    action = rest[0].lower()
    if action not in {"enable", "disable", "reset"}:
        await matcher.finish("用法: /auth group enable|disable|reset [群号]")
        return
    gid: int | None = None
    if len(rest) >= _GROUP_ARGS_WITH_ID and rest[1].isdigit():
        gid = int(rest[1])
    elif isinstance(event, GroupMessageEvent):
        gid = int(event.group_id)
    if gid is None:
        await matcher.finish("请指定群号，或在群内执行")
        return
    if action == "enable":
        acl_store.set_group_enabled(gid, enabled=True)
        await matcher.finish(f"群 {gid} 已启用（覆盖）")
        return
    if action == "disable":
        acl_store.set_group_enabled(gid, enabled=False)
        await matcher.finish(f"群 {gid} 已禁用")
        return
    acl_store.set_group_enabled(gid, enabled=None)
    await matcher.finish(f"群 {gid} 已恢复全局策略")
