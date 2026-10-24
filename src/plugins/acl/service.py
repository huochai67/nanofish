"""Core ACL resolution: scope, role, permission, quota."""

from __future__ import annotations

from functools import cache

from nonebot import get_driver
from nonebot.adapters.onebot.v11 import (
    GroupMessageEvent,
    MessageEvent,
    PrivateMessageEvent,
)
from nonebot.permission import Permission

from src.plugin_config import get_yaml_plugin_config

from .config import Config, PluginPolicy
from .quota import QuotaResult, quota_tracker
from .registry import get_spec
from .roles import Role
from .store import acl_store


@cache
def get_config() -> Config:
    """Parse ACL config lazily, after every plugin has registered its command."""
    return get_yaml_plugin_config(Config, "acl")


def _policy(command: str, config: Config | None) -> PluginPolicy | None:
    cfg = get_config() if config is None else config
    return cfg.plugins.get(command)


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

    config = get_config()
    if user_id in config.acl_admins:
        return Role.ADMIN

    if not config.acl_user_whitelist:
        return Role.USER
    return Role.USER if user_id in config.acl_user_whitelist else Role.GUEST


def is_blacklisted(user_id: int) -> bool:
    if is_superuser(user_id):
        return False
    config = get_config()
    return user_id in config.acl_blacklist or acl_store.is_blacklisted(user_id)


def scope_allows(event: MessageEvent) -> bool:
    if isinstance(event, PrivateMessageEvent):
        return get_config().acl_allow_private

    if not isinstance(event, GroupMessageEvent):
        return False

    group_id = int(event.group_id)
    override = acl_store.group_enabled(group_id)
    if override is not None:
        return override
    allowed = get_config().acl_allowed_groups
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


def perm_for_command(command: str, config: Config | None = None) -> Role:
    """Resolve a command's minimum role from config, falling back to its spec.

    Unknown command names raise instead of silently granting the default user
    role; callers are expected to register their command at import time.
    """
    spec = get_spec(command)
    policy = _policy(command, config)
    if policy is not None and policy.permission is not None:
        return policy.permission
    return spec.default_role


def require_command(command: str) -> Permission:
    get_spec(command)  # fail at import time on typos

    async def _checker(event: MessageEvent) -> bool:
        return event_allows(event, perm_for_command(command))

    return Permission(_checker)


def quota_limits(
    command: str,
    config: Config | None = None,
) -> tuple[int, float, int] | None:
    """Return ``(daily_limit, cooldown_seconds, per_minute_limit)``.

    ``None`` means the command did not declare quota capability; callers treat
    it as unlimited.  Unknown commands still fail closed via ``get_spec``.
    """
    spec = get_spec(command)
    defaults = spec.quota
    if defaults is None:
        return None

    policy = _policy(command, config)
    daily = defaults.daily
    cooldown = defaults.cooldown
    per_minute = defaults.per_minute
    if policy is not None:
        if policy.quota_daily is not None:
            daily = policy.quota_daily
        if policy.cooldown is not None:
            cooldown = policy.cooldown
        if policy.rate_limit_per_minute is not None:
            per_minute = policy.rate_limit_per_minute
    return daily, cooldown, per_minute


def check_quota(
    event: MessageEvent,
    command: str,
    config: Config | None = None,
) -> QuotaResult:
    """Check quota/cooldown without consuming."""
    limits = quota_limits(command, config)
    if limits is None:
        return QuotaResult(allowed=True, used=0, limit=0, remaining=-1)

    daily, cooldown, per_minute = limits
    user_id = get_user_id(event)
    return quota_tracker.check(
        command=command,
        user_id=user_id,
        daily_limit=daily,
        cooldown=cooldown,
        per_minute=per_minute,
        unlimited=is_superuser(user_id),
    )


def consume_quota(
    event: MessageEvent,
    command: str,
    config: Config | None = None,
) -> QuotaResult:
    """Atomically reserve quota before invoking a costly command."""
    limits = quota_limits(command, config)
    if limits is None:
        return QuotaResult(allowed=True, used=0, limit=0, remaining=-1)

    daily, cooldown, per_minute = limits
    user_id = get_user_id(event)
    return quota_tracker.consume(
        command=command,
        user_id=user_id,
        daily_limit=daily,
        cooldown=cooldown,
        per_minute=per_minute,
        unlimited=is_superuser(user_id),
    )


def ensure_quota(
    event: MessageEvent,
    command: str,
    config: Config | None = None,
) -> str | None:
    """
    Check quota; if allowed, consume one use and return None.
    If denied, return user-facing message (do not consume).
    """
    result = consume_quota(event, command, config)
    if not result.allowed:
        return result.message or "额度不足"
    return None
