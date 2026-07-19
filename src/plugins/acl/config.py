from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, Field

from .roles import Role


def _parse_role(value: Any) -> Role:
    if isinstance(value, Role):
        return value
    if isinstance(value, int):
        return Role(value)
    if isinstance(value, str):
        return Role.parse(value)
    msg = f"invalid role: {value!r}"
    raise TypeError(msg)


RoleField = Annotated[Role, BeforeValidator(_parse_role)]


class Config(BaseModel):
    """ACL plugin config (env prefix via field names)."""

    # Scope
    acl_allowed_groups: list[int] = Field(
        default_factory=list,
        description="群白名单；空列表表示不限制群",
    )
    acl_allow_private: bool = Field(
        default=False,
        description="是否允许私聊触发业务命令（superuser 始终可）",
    )

    # Static roles from env
    acl_admins: list[int] = Field(
        default_factory=list,
        description="管理员 QQ 号列表",
    )
    acl_user_whitelist: list[int] = Field(
        default_factory=list,
        description="用户白名单；非空时仅名单内为 user，其余为 guest",
    )
    acl_blacklist: list[int] = Field(
        default_factory=list,
        description="静态黑名单（env）；运行时 ban 另存 localstore",
    )

    # Min role per command
    acl_perm_jrrp: RoleField = Field(default=Role.GUEST, description="/jrrp 最低角色")
    acl_perm_llm: RoleField = Field(default=Role.USER, description="/llm 最低角色")
    acl_perm_genai: RoleField = Field(default=Role.USER, description="/genai 最低角色")
    acl_perm_eh: RoleField = Field(default=Role.ADMIN, description="/eh 最低角色")
    acl_perm_health: RoleField = Field(
        default=Role.SUPERUSER,
        description="/health 最低角色",
    )
    acl_perm_auth: RoleField = Field(
        default=Role.ADMIN,
        description="/auth 管理子命令最低角色",
    )

    # Quotas (0 = unlimited)
    acl_quota_llm_daily: int = Field(default=10, ge=0, description="/llm 日配额")
    acl_quota_genai_daily: int = Field(default=20, ge=0, description="/genai 日配额")
    acl_quota_eh_daily: int = Field(default=20, ge=0, description="/eh 日配额")

    # Cooldown seconds (0 = none)
    acl_cooldown_llm: float = Field(default=30.0, ge=0, description="/llm 冷却秒")
    acl_cooldown_genai: float = Field(default=10.0, ge=0, description="/genai 冷却秒")
    acl_cooldown_eh: float = Field(default=10.0, ge=0, description="/eh 冷却秒")
