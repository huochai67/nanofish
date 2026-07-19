"""Role hierarchy for ACL."""

from __future__ import annotations

from enum import IntEnum


class Role(IntEnum):
    """Permission levels. Higher value includes lower privileges."""

    GUEST = 0
    USER = 1
    ADMIN = 2
    SUPERUSER = 3

    @classmethod
    def parse(cls, value: str | Role) -> Role:
        if isinstance(value, Role):
            return value
        key = value.strip().lower()
        mapping = {
            "guest": cls.GUEST,
            "user": cls.USER,
            "admin": cls.ADMIN,
            "superuser": cls.SUPERUSER,
            "super": cls.SUPERUSER,
        }
        if key not in mapping:
            msg = f"未知角色: {value}（可选: guest/user/admin/superuser）"
            raise ValueError(msg)
        return mapping[key]

    def label(self) -> str:
        return self.name.lower()


ROLE_ORDER: tuple[Role, ...] = (
    Role.GUEST,
    Role.USER,
    Role.ADMIN,
    Role.SUPERUSER,
)
