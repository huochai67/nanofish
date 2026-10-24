"""ACL command registry.

Each plugin declares its ACL metadata (default role and optional quota
capability) while importing.  The ACL plugin only supplies enforcement and
configuration overrides; it does not keep a list of plugin names.
"""

from __future__ import annotations

from dataclasses import dataclass

from .roles import Role


@dataclass(frozen=True, slots=True)
class QuotaDefaults:
    """Default quota values for a command; config entries may override them."""

    daily: int = 20
    per_minute: int = 0
    cooldown: float = 10.0

    def __post_init__(self) -> None:
        if self.daily < 0 or self.per_minute < 0 or self.cooldown < 0:
            msg = f"quota defaults must be non-negative: {self!r}"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class CommandSpec:
    """ACL metadata declared by the plugin that owns the command."""

    name: str
    default_role: Role
    quota: QuotaDefaults | None = None


_REGISTRY: dict[str, CommandSpec] = {}


def register_command(
    name: str,
    *,
    default_role: Role,
    quota: QuotaDefaults | None = None,
) -> CommandSpec:
    """Register command metadata.  Re-registering an identical spec is a no-op."""
    if not name or not name.strip():
        msg = "ACL command name must be a non-empty string"
        raise ValueError(msg)

    spec = CommandSpec(name=name, default_role=default_role, quota=quota)
    existing = _REGISTRY.get(name)
    if existing is not None and existing != spec:
        msg = f"ACL command {name!r} already registered as {existing!r}"
        raise ValueError(msg)
    _REGISTRY[name] = spec
    return spec


def lookup(name: str) -> CommandSpec | None:
    return _REGISTRY.get(name)


def get_spec(name: str) -> CommandSpec:
    spec = _REGISTRY.get(name)
    if spec is None:
        registered = ", ".join(sorted(_REGISTRY)) or "(none)"
        msg = f"ACL command {name!r} is not registered; registered: {registered}"
        raise ValueError(msg)
    return spec


def registered_commands() -> tuple[CommandSpec, ...]:
    return tuple(_REGISTRY.values())


def quota_commands() -> tuple[str, ...]:
    return tuple(name for name, spec in _REGISTRY.items() if spec.quota is not None)
