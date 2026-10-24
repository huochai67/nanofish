from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError

from src.plugins.acl import registry, service
from src.plugins.acl.config import Config
from src.plugins.acl.roles import Role

if TYPE_CHECKING:
    from collections.abc import Iterator

_EXPECTED_COMMANDS = {
    "auth",
    "jrrp",
    "health",
    "genai",
    "eh",
    "imgsearch",
    "agent",
    "parser",
}


@pytest.fixture
def temp_command() -> Iterator[str]:
    name = "__test_acl_command__"
    registry._REGISTRY.pop(name, None)
    try:
        yield name
    finally:
        registry._REGISTRY.pop(name, None)


def _config(plugins: list[dict[str, object]] | None = None) -> Config:
    return Config.model_validate({"plugins": plugins or []})


def test_expected_commands_are_registered() -> None:
    names = {spec.name for spec in registry.registered_commands()}
    assert names >= _EXPECTED_COMMANDS
    assert set(registry.quota_commands()) == {"genai", "eh", "imgsearch", "agent"}


def test_example_config_matches_registry() -> None:
    config = service.get_config()
    registered = {spec.name for spec in registry.registered_commands()}
    assert set(config.plugins) <= registered


def test_plugin_defaults_and_overrides() -> None:
    default = _config()
    assert service.perm_for_command("eh", default) is Role.ADMIN
    assert service.quota_limits("eh", default) == (20, 10.0, 0)
    assert service.quota_limits("jrrp", default) is None

    overridden = _config(
        [
            {
                "name": "eh",
                "permission": "guest",
                "quota_daily": 0,
                "rate_limit_per_minute": 3,
                "cooldown": 0,
            },
        ]
    )
    assert service.perm_for_command("eh", overridden) is Role.GUEST
    assert service.quota_limits("eh", overridden) == (0, 0.0, 3)


def test_unknown_command_fails_closed() -> None:
    with pytest.raises(ValueError, match="not registered"):
        service.perm_for_command("__missing__")
    with pytest.raises(ValueError, match="not registered"):
        service.quota_limits("__missing__")
    with pytest.raises(ValueError, match="not registered"):
        service.require_command("__missing__")


def test_config_rejects_unknown_plugin() -> None:
    with pytest.raises(ValidationError, match="unknown ACL plugin"):
        _config([{"name": "__missing__", "permission": "user"}])


def test_config_rejects_quota_settings_without_capability() -> None:
    with pytest.raises(ValidationError, match="unsupported ACL settings"):
        _config([{"name": "jrrp", "cooldown": 5}])


def test_config_rejects_duplicate_plugin_entries() -> None:
    with pytest.raises(ValidationError, match="duplicate ACL plugin"):
        _config([{"name": "jrrp"}, {"name": "jrrp"}])


def test_config_rejects_legacy_flat_keys() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        Config.model_validate({"acl_perm_eh": "admin"})


def test_registration_conflict_is_rejected(temp_command: str) -> None:
    registry.register_command(temp_command, default_role=Role.USER)
    registry.register_command(temp_command, default_role=Role.USER)
    with pytest.raises(ValueError, match="already registered"):
        registry.register_command(temp_command, default_role=Role.ADMIN)
