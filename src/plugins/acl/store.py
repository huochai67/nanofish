"""Runtime ACL state persisted via localstore."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from nonebot import logger, require

require("nonebot_plugin_localstore")
import nonebot_plugin_localstore as store

from .roles import Role

if TYPE_CHECKING:
    from pathlib import Path

_USERS_FILE = "users.json"
_STATE_FILE = "state.json"


@dataclass
class UserOverride:
    role: Role | None = None


@dataclass
class GroupOverride:
    enabled: bool | None = None  # None = inherit global


@dataclass
class AclState:
    users: dict[int, UserOverride] = field(default_factory=dict)
    blacklist: set[int] = field(default_factory=set)
    groups: dict[int, GroupOverride] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "users": {
                str(uid): ({"role": ov.role.label()} if ov.role is not None else {})
                for uid, ov in self.users.items()
                if ov.role is not None
            },
            "blacklist": sorted(self.blacklist),
            "groups": {
                str(gid): ({"enabled": ov.enabled} if ov.enabled is not None else {})
                for gid, ov in self.groups.items()
                if ov.enabled is not None
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AclState:
        state = cls()
        for uid_s, raw in (data.get("users") or {}).items():
            try:
                uid = int(uid_s)
            except (TypeError, ValueError):
                continue
            role_s = (raw or {}).get("role")
            if role_s:
                try:
                    state.users[uid] = UserOverride(role=Role.parse(str(role_s)))
                except ValueError:
                    logger.warning(f"[acl] skip invalid role for user {uid}: {role_s}")
        for item in data.get("blacklist") or []:
            try:
                state.blacklist.add(int(item))
            except (TypeError, ValueError):
                continue
        for gid_s, raw in (data.get("groups") or {}).items():
            try:
                gid = int(gid_s)
            except (TypeError, ValueError):
                continue
            enabled = (raw or {}).get("enabled")
            if isinstance(enabled, bool):
                state.groups[gid] = GroupOverride(enabled=enabled)
        return state


class AclStore:
    def __init__(self) -> None:
        self._state = AclState()
        self._path: Path | None = None
        self._loaded = False

    def _file(self) -> Path:
        if self._path is None:
            self._path = store.get_plugin_data_file(_STATE_FILE)
        return self._path

    def load(self) -> None:
        path = self._file()
        if not path.is_file():
            legacy = store.get_plugin_data_file(_USERS_FILE)
            if legacy.is_file():
                try:
                    data = json.loads(legacy.read_text(encoding="utf-8"))
                    self._state = AclState.from_dict(
                        data if isinstance(data, dict) else {}
                    )
                    self.save()
                    logger.info("[acl] migrated legacy users.json -> state.json")
                except (OSError, json.JSONDecodeError) as e:
                    logger.warning(f"[acl] failed to migrate legacy store: {e}")
            self._loaded = True
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self._state = AclState.from_dict(data if isinstance(data, dict) else {})
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"[acl] failed to load state, using empty: {e}")
            self._state = AclState()
        self._loaded = True

    def ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    def save(self) -> None:
        self.ensure_loaded()
        path = self._file()
        path.write_text(
            json.dumps(self._state.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    @property
    def state(self) -> AclState:
        self.ensure_loaded()
        return self._state

    def get_user_role(self, user_id: int) -> Role | None:
        self.ensure_loaded()
        ov = self._state.users.get(user_id)
        return ov.role if ov else None

    def set_user_role(self, user_id: int, role: Role | None) -> None:
        self.ensure_loaded()
        if role is None:
            self._state.users.pop(user_id, None)
        else:
            self._state.users[user_id] = UserOverride(role=role)
        self.save()

    def is_blacklisted(self, user_id: int) -> bool:
        self.ensure_loaded()
        return user_id in self._state.blacklist

    def ban(self, user_id: int) -> None:
        self.ensure_loaded()
        self._state.blacklist.add(user_id)
        self.save()

    def unban(self, user_id: int) -> None:
        self.ensure_loaded()
        self._state.blacklist.discard(user_id)
        self.save()

    def group_enabled(self, group_id: int) -> bool | None:
        """None = inherit global whitelist rules."""
        self.ensure_loaded()
        ov = self._state.groups.get(group_id)
        return ov.enabled if ov else None

    def set_group_enabled(self, group_id: int, *, enabled: bool | None) -> None:
        self.ensure_loaded()
        if enabled is None:
            self._state.groups.pop(group_id, None)
        else:
            self._state.groups[group_id] = GroupOverride(enabled=enabled)
        self.save()


acl_store = AclStore()
