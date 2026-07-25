from unittest.mock import patch

import nonebot
from nonebot import get_plugin

nonebot.init()


class _GroupEvent:
    def __init__(self, user_id: int, group_id: int) -> None:
        self.user_id = user_id
        self.group_id = group_id


class _PrivateEvent:
    def __init__(self, user_id: int) -> None:
        self.user_id = user_id


def _load_acl() -> None:
    if get_plugin("acl") is None:
        nonebot.load_plugins("src/plugins")


def test_superuser_must_be_in_allowed_group() -> None:
    _load_acl()
    from src.plugins.acl import service
    from src.plugins.acl.config import Config

    config = Config.model_construct(acl_allow_private=False, acl_allowed_groups=[100])
    with (
        patch.object(service, "config", config),
        patch.object(service, "GroupMessageEvent", _GroupEvent),
        patch.object(service, "PrivateMessageEvent", _PrivateEvent),
        patch.object(service, "is_superuser", return_value=True),
        patch.object(service.acl_store, "group_enabled", return_value=None),
    ):
        assert not service.scope_allows(_GroupEvent(1, 200))
        assert service.scope_allows(_GroupEvent(1, 100))


def test_superuser_cannot_bypass_private_or_auth_scope() -> None:
    _load_acl()
    from src.plugins.acl import commands, service
    from src.plugins.acl.config import Config
    from src.plugins.acl.roles import Role

    config = Config.model_construct(
        acl_allow_private=False,
        acl_allowed_groups=[100],
        acl_perm_auth=Role.ADMIN,
    )
    with (
        patch.object(service, "config", config),
        patch.object(service, "GroupMessageEvent", _GroupEvent),
        patch.object(service, "PrivateMessageEvent", _PrivateEvent),
        patch.object(service, "is_superuser", return_value=True),
        patch.object(service.acl_store, "group_enabled", return_value=None),
    ):
        assert not service.scope_allows(_PrivateEvent(1))
        assert not commands.can_manage(_GroupEvent(1, 200), config)
