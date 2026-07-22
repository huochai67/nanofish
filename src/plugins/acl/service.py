"""Core ACL resolution: scope, role, permission, quota."""

from __future__ import annotations

from nonebot import get_driver, get_plugin_config
from nonebot.adapters.onebot.v11 import (
    GroupMessageEvent,
    MessageEvent,
    PrivateMessageEvent,
)
from nonebot.permission import Permission

from .config import Config
from .quota import QuotaResult, quota_tracker
from .roles import Role
from .store import acl_store

config: Config = get_plugin_config(Config)

_QUOTA_COMMANDS: dict[str, tuple[str, str]] = {
    "llm": ("acl_quota_llm_daily", "acl_cooldown_llm"),
    "draw": ("acl_quota_draw_daily", "acl_cooldown_draw"),
    "genai": ("acl_quota_genai_daily", "acl_cooldown_genai"),
    "eh": ("acl_quota_eh_daily", "acl_cooldown_eh"),
}


def _superusers() -> set[str]:
    return {str(u) for u in get_driver().config.superusers}


def is_superuser(user_id: int) -> bool:
    return str(user_id) in _superusers()


def get_user_id(event: MessageEvent) -> int:
    return int(event.user_id)


def get_group_id(event: MessageEvent) -> int | None:
    if isinstance(event, GroupMessageEvent):
        return int(event.group_id)
    return None


def resolve_role(user_id: int) -> Role:
    if is_superuser(user_id):
        return Role.SUPERUSER

    stored = acl_store.get_user_role(user_id)
    if stored is not None:
        # cannot grant superuser via store
        return Role.ADMIN if stored is Role.SUPERUSER else stored

    if user_id in config.acl_admins:
        return Role.ADMIN

    if not config.acl_user_whitelist:
        return Role.USER
    return Role.USER if user_id in config.acl_user_whitelist else Role.GUEST


def is_blacklisted(user_id: int) -> bool:
    if is_superuser(user_id):
        return False
    return user_id in config.acl_blacklist or acl_store.is_blacklisted(user_id)


def scope_allows(event: MessageEvent, *, bypass_for_superuser: bool = True) -> bool:
    user_id = get_user_id(event)
    if bypass_for_superuser and is_superuser(user_id):
        return True

    if isinstance(event, PrivateMessageEvent):
        return config.acl_allow_private

    if not isinstance(event, GroupMessageEvent):
        return False

    group_id = int(event.group_id)
    override = acl_store.group_enabled(group_id)
    if override is not None:
        return override
    allowed = config.acl_allowed_groups
    return (not allowed) or (group_id in allowed)


def role_allows(user_id: int, min_role: Role) -> bool:
    if is_blacklisted(user_id):
        return False
    return resolve_role(user_id) >= min_role


def event_allows(event: MessageEvent, min_role: Role) -> bool:
    return scope_allows(event) and role_allows(get_user_id(event), min_role)


def require_level(min_role: Role | str) -> Permission:
    """NoneBot Permission: silent deny when role/scope insufficient."""
    needed = Role.parse(min_role) if isinstance(min_role, str) else min_role

    async def _checker(event: MessageEvent) -> bool:
        return event_allows(event, needed)

    return Permission(_checker)


def perm_for_command(command: str) -> Role:
    mapping = {
        "jrrp": config.acl_perm_jrrp,
        "llm": config.acl_perm_llm,
        "draw": config.acl_perm_draw,
        "genai": config.acl_perm_genai,
        "eh": config.acl_perm_eh,
        "parser": config.acl_perm_parser,
        "health": config.acl_perm_health,
        "auth": config.acl_perm_auth,
    }
    return mapping.get(command, Role.USER)


def require_command(command: str) -> Permission:
    return require_level(perm_for_command(command))


def check_quota(event: MessageEvent, command: str) -> QuotaResult:
    """Check quota/cooldown without consuming."""
    user_id = get_user_id(event)
    if is_superuser(user_id):
        return QuotaResult(allowed=True, used=0, limit=0, remaining=-1)

    specs = _QUOTA_COMMANDS.get(command)
    if specs is None:
        return QuotaResult(allowed=True, used=0, limit=0, remaining=-1)

    daily_attr, cd_attr = specs
    return quota_tracker.check(
        command=command,
        user_id=user_id,
        daily_limit=int(getattr(config, daily_attr)),
        cooldown=float(getattr(config, cd_attr)),
        unlimited=False,
    )


def consume_quota(event: MessageEvent, command: str) -> None:
    user_id = get_user_id(event)
    if is_superuser(user_id) or command not in _QUOTA_COMMANDS:
        return
    quota_tracker.consume(command=command, user_id=user_id, unlimited=False)


def ensure_quota(event: MessageEvent, command: str) -> str | None:
    """
    Check quota; if allowed, consume one use and return None.
    If denied, return user-facing message (do not consume).
    """
    result = check_quota(event, command)
    if not result.allowed:
        return result.message or "额度不足"
    consume_quota(event, command)
    return None
