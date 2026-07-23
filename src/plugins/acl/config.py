"""ACL plugin configuration validation."""

from __future__ import annotations

import json
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, Field, model_validator

from .roles import Role


def _strip_inline_comment(raw: str) -> str:
    """Strip unquoted trailing comments from string values."""
    in_str = False
    quote: str | None = None
    for i, ch in enumerate(raw):
        if ch in "\"'" and not in_str:
            in_str = True
            quote = ch
        elif in_str and ch == quote:
            in_str = False
            quote = None
        elif ch == "#" and not in_str:
            return raw[:i].strip()
    return raw.strip()


def _parse_int_list(value: Any) -> list[int]:
    if value is None:
        return []
    if isinstance(value, list):
        return [int(x) for x in value]
    if isinstance(value, (int, float)):
        return [int(value)]
    if isinstance(value, str):
        text = _strip_inline_comment(value)
        if not text or text == "[]":
            return []
        try:
            parsed: Any = json.loads(text)
        except json.JSONDecodeError:
            # allow "1,2,3" without brackets
            parsed = [part.strip() for part in text.split(",") if part.strip()]
        if not isinstance(parsed, list):
            msg = f"expected list of ints, got {parsed!r}"
            raise TypeError(msg)
        return [int(x) for x in parsed]
    msg = f"invalid int list: {value!r}"
    raise TypeError(msg)


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        text = _strip_inline_comment(value).lower()
        if text in {"1", "true", "yes", "on"}:
            return True
        if text in {"0", "false", "no", "off", ""}:
            return False
    msg = f"invalid bool: {value!r}"
    raise TypeError(msg)


def _parse_role(value: Any) -> Role:
    if isinstance(value, Role):
        return value
    if isinstance(value, int):
        return Role(value)
    if isinstance(value, str):
        return Role.parse(_strip_inline_comment(value))
    msg = f"invalid role: {value!r}"
    raise TypeError(msg)


def _parse_nonneg_int(value: Any) -> int:
    if isinstance(value, bool):
        msg = f"invalid int: {value!r}"
        raise TypeError(msg)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        return int(_strip_inline_comment(value))
    msg = f"invalid int: {value!r}"
    raise TypeError(msg)


def _parse_nonneg_float(value: Any) -> float:
    if isinstance(value, bool):
        msg = f"invalid float: {value!r}"
        raise TypeError(msg)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        return float(_strip_inline_comment(value))
    msg = f"invalid float: {value!r}"
    raise TypeError(msg)


IntListField = Annotated[list[int], BeforeValidator(_parse_int_list)]
BoolField = Annotated[bool, BeforeValidator(_parse_bool)]
RoleField = Annotated[Role, BeforeValidator(_parse_role)]
NonNegIntField = Annotated[int, BeforeValidator(_parse_nonneg_int)]
NonNegFloatField = Annotated[float, BeforeValidator(_parse_nonneg_float)]

_ACL_PLUGIN_FIELDS = {
    "jrrp": {"permission"},
    "llm": {"permission", "quota_daily", "rate_limit_per_minute", "cooldown"},
    "draw": {"permission", "quota_daily", "rate_limit_per_minute", "cooldown"},
    "genai": {"permission", "quota_daily", "rate_limit_per_minute", "cooldown"},
    "eh": {"permission", "quota_daily", "rate_limit_per_minute", "cooldown"},
    "imgsearch": {"permission", "quota_daily", "rate_limit_per_minute", "cooldown"},
    "parser": {"permission"},
    "health": {"permission"},
    "auth": {"permission"},
}


class Config(BaseModel):
    """ACL plugin configuration from ``config.yaml``."""

    @model_validator(mode="before")
    @classmethod
    def _flatten_plugin_settings(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value

        values = value.copy()
        plugins = values.pop("plugins", [])
        if not isinstance(plugins, list):
            msg = "acl.plugins must be a list"
            raise TypeError(msg)

        seen: set[str] = set()
        for item in plugins:
            if not isinstance(item, dict):
                msg = "each acl.plugins item must be a mapping"
                raise TypeError(msg)
            name = item.get("name")
            if not isinstance(name, str) or name not in _ACL_PLUGIN_FIELDS:
                msg = f"unknown ACL plugin: {name!r}"
                raise ValueError(msg)
            if name in seen:
                msg = f"duplicate ACL plugin: {name}"
                raise ValueError(msg)
            seen.add(name)

            allowed = {"name", *_ACL_PLUGIN_FIELDS[name]}
            unknown = set(item) - allowed
            if unknown:
                msg = f"unsupported ACL settings for {name}: {sorted(unknown)}"
                raise ValueError(msg)
            for setting, raw in item.items():
                if setting == "name":
                    continue
                field = {
                    "permission": f"acl_perm_{name}",
                    "quota_daily": f"acl_quota_{name}_daily",
                    "rate_limit_per_minute": f"acl_rate_limit_{name}_per_minute",
                    "cooldown": f"acl_cooldown_{name}",
                }[setting]
                values[field] = raw
        return values

    # Scope
    acl_allowed_groups: IntListField = Field(
        default_factory=list,
        description="群白名单；空列表表示不限制群",
    )
    acl_allow_private: BoolField = Field(
        default=False,
        description="是否允许私聊触发业务命令（superuser 始终可）",
    )

    # Static roles from configuration
    acl_admins: IntListField = Field(
        default_factory=list,
        description="管理员 QQ 号列表",
    )
    acl_user_whitelist: IntListField = Field(
        default_factory=list,
        description="用户白名单；非空时仅名单内为 user，其余为 guest",
    )
    acl_blacklist: IntListField = Field(
        default_factory=list,
        description="静态黑名单；运行时 ban 另存 localstore",
    )

    # Min role per command
    acl_perm_jrrp: RoleField = Field(default=Role.GUEST, description="/jrrp 最低角色")
    acl_perm_llm: RoleField = Field(default=Role.USER, description="/llm 最低角色")
    acl_perm_draw: RoleField = Field(default=Role.USER, description="/draw 最低角色")
    acl_perm_genai: RoleField = Field(default=Role.USER, description="/genai 最低角色")
    acl_perm_eh: RoleField = Field(default=Role.ADMIN, description="/eh 最低角色")
    acl_perm_imgsearch: RoleField = Field(
        default=Role.USER,
        description="/imgsearch 最低角色",
    )
    acl_perm_parser: RoleField = Field(
        default=Role.USER,
        description="链接解析与 /bm 最低角色",
    )
    acl_perm_health: RoleField = Field(
        default=Role.SUPERUSER,
        description="/health 最低角色",
    )
    acl_perm_auth: RoleField = Field(
        default=Role.ADMIN,
        description="/auth 管理子命令最低角色",
    )

    # Quotas (0 = unlimited)
    acl_quota_llm_daily: NonNegIntField = Field(
        default=10,
        ge=0,
        description="/llm 日配额",
    )
    acl_quota_draw_daily: NonNegIntField = Field(
        default=5,
        ge=0,
        description="/draw 日配额",
    )
    acl_quota_genai_daily: NonNegIntField = Field(
        default=20,
        ge=0,
        description="/genai 日配额",
    )
    acl_quota_eh_daily: NonNegIntField = Field(
        default=20,
        ge=0,
        description="/eh 日配额",
    )
    acl_quota_imgsearch_daily: NonNegIntField = Field(
        default=20,
        ge=0,
        description="/imgsearch 日配额",
    )
    acl_rate_limit_llm_per_minute: NonNegIntField = Field(
        default=0,
        ge=0,
        description="/llm 滚动每分钟请求上限；0 表示不限制",
    )
    acl_rate_limit_draw_per_minute: NonNegIntField = Field(
        default=0,
        ge=0,
        description="/draw 滚动每分钟请求上限；0 表示不限制",
    )
    acl_rate_limit_genai_per_minute: NonNegIntField = Field(
        default=0,
        ge=0,
        description="/genai 滚动每分钟请求上限；0 表示不限制",
    )
    acl_rate_limit_eh_per_minute: NonNegIntField = Field(
        default=0,
        ge=0,
        description="/eh 滚动每分钟请求上限；0 表示不限制",
    )
    acl_rate_limit_imgsearch_per_minute: NonNegIntField = Field(
        default=0,
        ge=0,
        description="/imgsearch 滚动每分钟请求上限；0 表示不限制",
    )

    # Cooldown seconds (0 = none)
    acl_cooldown_llm: NonNegFloatField = Field(
        default=30.0,
        ge=0,
        description="/llm 冷却秒",
    )
    acl_cooldown_draw: NonNegFloatField = Field(
        default=60.0,
        ge=0,
        description="/draw 冷却秒",
    )
    acl_cooldown_genai: NonNegFloatField = Field(
        default=10.0,
        ge=0,
        description="/genai 冷却秒",
    )
    acl_cooldown_eh: NonNegFloatField = Field(
        default=10.0,
        ge=0,
        description="/eh 冷却秒",
    )
    acl_cooldown_imgsearch: NonNegFloatField = Field(
        default=10.0,
        ge=0,
        description="/imgsearch 冷却秒",
    )
