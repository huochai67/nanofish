"""ACL plugin configuration validation."""

from __future__ import annotations

import json
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

from .registry import lookup, registered_commands
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

_PERMISSION_KEYS = frozenset({"permission"})
_QUOTA_KEYS = frozenset({"quota_daily", "rate_limit_per_minute", "cooldown"})


class PluginPolicy(BaseModel):
    """Per-command overrides for the defaults declared in the registry."""

    model_config = ConfigDict(extra="forbid")

    permission: RoleField | None = None
    quota_daily: NonNegIntField | None = None
    rate_limit_per_minute: NonNegIntField | None = None
    cooldown: NonNegFloatField | None = None


class Config(BaseModel):
    """ACL plugin configuration from ``config.yaml``."""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _collect_plugin_policies(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value

        values = value.copy()
        plugins = values.pop("plugins", [])
        if plugins is None:
            plugins = []
        if not isinstance(plugins, list):
            msg = "acl.plugins must be a list"
            raise TypeError(msg)

        collected: dict[str, dict[str, Any]] = {}
        for item in plugins:
            if not isinstance(item, dict):
                msg = "each acl.plugins item must be a mapping"
                raise TypeError(msg)
            name = item.get("name")
            if not isinstance(name, str) or not name:
                msg = f"invalid ACL plugin name: {name!r}"
                raise ValueError(msg)
            if name in collected:
                msg = f"duplicate ACL plugin: {name}"
                raise ValueError(msg)

            spec = lookup(name)
            if spec is None:
                names = ", ".join(sorted(s.name for s in registered_commands()))
                msg = f"unknown ACL plugin: {name!r}; registered: {names or '(none)'}"
                raise ValueError(msg)

            payload = {key: raw for key, raw in item.items() if key != "name"}
            allowed = _PERMISSION_KEYS | (
                _QUOTA_KEYS if spec.quota is not None else frozenset()
            )
            unknown = set(payload) - allowed
            if unknown:
                msg = f"unsupported ACL settings for {name}: {sorted(unknown)}"
                raise ValueError(msg)
            collected[name] = payload

        values["plugins"] = collected
        return values

    # Scope
    acl_allowed_groups: IntListField = Field(
        default_factory=list,
        description="群白名单；空列表表示不限制群",
    )
    acl_allow_private: BoolField = Field(
        default=False,
        description="是否允许私聊触发业务命令",
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

    # Per-command overrides; defaults and capability live with each plugin.
    plugins: dict[str, PluginPolicy] = Field(
        default_factory=dict,
        description="命令级权限/配额覆盖；未列出的命令使用插件声明的默认值",
    )
