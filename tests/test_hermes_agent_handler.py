import asyncio
from contextlib import suppress
from pathlib import Path
from typing import Any

from nonebot.adapters.onebot.v11 import Message
from nonebot.exception import FinishedException
from nonebot.matcher import current_bot, current_event, current_matcher
from pytest import MonkeyPatch

import src.plugins.hermes_agent as agent_plugin
from src.plugins.acl.quota import QuotaResult
from src.plugins.hermes_agent import reference as reference_module
from src.plugins.hermes_agent.client import (
    ChatResult,
    HermesAuthError,
    HermesError,
    HermesMissingKeyError,
)
from src.plugins.hermes_agent.store import AgentStore


class _FakeBot:
    self_id = "1"

    def __init__(
        self,
        replies: dict[int, dict[str, Any]] | None = None,
        *,
        start_id: int = 1000,
    ) -> None:
        self.replies = replies or {}
        self.sent: list[Any] = []
        self.deleted: list[int] = []
        self._next_id = start_id

    async def send(
        self,
        *,
        event: Any,  # noqa: ARG002
        message: Any,
        **_kwargs: Any,
    ) -> Any:
        self.sent.append(message)
        self._next_id += 1
        return {"message_id": self._next_id}

    async def call_api(self, api: str, **kwargs: Any) -> Any:
        if api == "delete_msg":
            self.deleted.append(int(kwargs["message_id"]))
            return None
        if api == "get_msg":
            return self.replies.get(int(kwargs["message_id"]))
        raise AssertionError(api)


class _FakeEvent:
    def __init__(
        self,
        message_id: int,
        original_message: Message,
        user_id: int = 42,
    ) -> None:
        self.message_id = message_id
        self.original_message = original_message
        self.user_id = user_id


class _FakeClient:
    def __init__(self) -> None:
        self.sessions: list[dict[str, Any]] = []
        self.chats: list[dict[str, Any]] = []

    async def create_session(self, profile: str, title: str | None = None) -> str:
        session_id = f"s{len(self.sessions) + 1}"
        self.sessions.append(
            {"id": session_id, "profile": profile, "title": title},
        )
        return session_id

    async def chat(
        self,
        *,
        profile: str,
        session_id: str,
        message: str | list[dict[str, Any]],
    ) -> ChatResult:
        self.chats.append(
            {"profile": profile, "session_id": session_id, "message": message},
        )
        return ChatResult(session_id, "final answer", "completed")


class _TitleConflictClient(_FakeClient):
    async def create_session(self, profile: str, title: str | None = None) -> str:
        if title is not None:
            msg = "title already in use"
            raise HermesError(msg, code="invalid_title")
        return await super().create_session(profile, None)


async def _invoke(
    bot: _FakeBot,
    event: _FakeEvent,
    arg: Message | None = None,
) -> None:
    bot_token = current_bot.set(bot)
    event_token = current_event.set(event)
    matcher = agent_plugin.agent if arg is not None else agent_plugin.agent_reply
    matcher_token = current_matcher.set(matcher)
    try:
        with suppress(FinishedException):
            if arg is None:
                await agent_plugin.handle_agent_reply(bot, event)
            else:
                await agent_plugin.handle_agent(bot, event, arg)
    finally:
        current_bot.reset(bot_token)
        current_event.reset(event_token)
        current_matcher.reset(matcher_token)


_PNG = b"\x89PNG\r\n\x1a\npayload"


def _patch_download(
    monkeypatch: MonkeyPatch,
    url: str = "https://cdn.example.com/a.png",
) -> None:
    async def fake_download(requested: str, max_bytes: int) -> tuple[bytes, str]:
        assert requested == url
        assert max_bytes > 0
        return _PNG, "image/png"

    monkeypatch.setattr(reference_module, "_download", fake_download)


def _patch(
    monkeypatch: MonkeyPatch,
    store: AgentStore,
    client: _FakeClient,
    rendered_calls: list[dict[str, Any]] | None = None,
) -> None:
    monkeypatch.setattr(agent_plugin, "agent_store", store)
    monkeypatch.setattr(agent_plugin, "hermes_client", client)
    monkeypatch.setattr(
        agent_plugin,
        "config",
        agent_plugin.Config(agent_api_key="test-key"),
    )
    monkeypatch.setattr(
        agent_plugin,
        "consume_quota",
        lambda *_args, **_kwargs: QuotaResult(allowed=True),
    )

    async def fake_chat_image_cq(chat_data: dict[str, Any]) -> Message:
        if rendered_calls is not None:
            rendered_calls.append(chat_data)
        return Message("[CQ:image,file=base64://AAA]")

    monkeypatch.setattr(agent_plugin, "app_chat_image_cq", fake_chat_image_cq)


def test_auth_message_distinguishes_missing_profile_key() -> None:
    missing = agent_plugin._auth_message(HermesMissingKeyError("missing"), "mc")
    assert "未配置" in missing
    assert "agent_profiles.mc" in missing
    assert "拒绝" not in missing

    remote = agent_plugin._auth_message(
        HermesAuthError("Invalid gateway API key"),
        "mc",
    )
    assert "拒绝" in remote
    assert "Invalid gateway API key" in remote


def test_handler_creates_session_and_continues_on_reply(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    async def run() -> None:
        store = AgentStore(tmp_path / "agent.sqlite3")
        client = _FakeClient()
        _patch(monkeypatch, store, client)

        first_bot = _FakeBot()
        await _invoke(first_bot, _FakeEvent(10, Message("hello")), Message("hello"))
        first = await store.lookup_message(bot_id="1", message_id="1002")
        assert first is not None
        assert first.session_id == "s1"
        assert first.role == "assistant"
        assert first.content == "final answer"

        second_bot = _FakeBot(start_id=2000)
        await _invoke(
            second_bot,
            _FakeEvent(20, Message("[CQ:reply,id=1002] /agent again")),
            Message("again"),
        )
        assert len(client.sessions) == 1
        assert len(client.chats) == 2  # noqa: PLR2004
        assert client.chats[1]["session_id"] == "s1"
        assert str(client.chats[1]["message"]) == "again"

        second = await store.lookup_message(bot_id="1", message_id="2002")
        assert second is not None
        assert second.session_id == "s1"

    asyncio.run(run())


def test_reply_to_bot_message_continues_without_command(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    async def run() -> None:
        store = AgentStore(tmp_path / "agent.sqlite3")
        client = _FakeClient()
        _patch(monkeypatch, store, client)

        await _invoke(_FakeBot(), _FakeEvent(10, Message("hello")), Message("hello"))

        second_bot = _FakeBot(start_id=2000)
        await _invoke(
            second_bot,
            _FakeEvent(20, Message("[CQ:reply,id=1002] follow up")),
        )
        assert len(client.sessions) == 1
        assert len(client.chats) == 2  # noqa: PLR2004
        assert client.chats[1]["session_id"] == "s1"
        assert str(client.chats[1]["message"]) == "follow up"

        second = await store.lookup_message(bot_id="1", message_id="2002")
        assert second is not None
        assert second.session_id == "s1"

    asyncio.run(run())


def test_command_attaches_image_from_current_message(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    async def run() -> None:
        store = AgentStore(tmp_path / "agent.sqlite3")
        client = _FakeClient()
        _patch(monkeypatch, store, client)

        _patch_download(monkeypatch)
        event = _FakeEvent(
            10,
            Message(
                "[CQ:image,url=https://cdn.example.com/a.png,"
                "file=A60532D5DA12463D7D5EC06F778BEEB0.png,sub_type=0]",
            ),
        )
        await _invoke(_FakeBot(), event, Message("这是什么"))

        prompt = client.chats[0]["message"]
        assert isinstance(prompt, list)
        assert prompt[0]["type"] == "text"
        assert "这是什么" in prompt[0]["text"]
        assert "<reference>" not in prompt[0]["text"]
        assert prompt[1]["type"] == "image_url"
        assert prompt[1]["image_url"]["url"].startswith("data:image/png;base64,")

    asyncio.run(run())


def test_session_quote_with_image_has_no_reference(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    async def run() -> None:
        store = AgentStore(tmp_path / "agent.sqlite3")
        client = _FakeClient()
        _patch(monkeypatch, store, client)
        _patch_download(monkeypatch)

        await _invoke(_FakeBot(), _FakeEvent(10, Message("hello")), Message("hello"))

        second_bot = _FakeBot(start_id=2000)
        await _invoke(
            second_bot,
            _FakeEvent(
                20,
                Message(
                    "[CQ:reply,id=1002] 这是什么"
                    "[CQ:image,url=https://cdn.example.com/a.png,"
                    "file=A60532D5DA12463D7D5EC06F778BEEB0.png,sub_type=0]",
                ),
            ),
        )

        assert len(client.sessions) == 1
        assert client.chats[1]["session_id"] == "s1"
        prompt = client.chats[1]["message"]
        assert isinstance(prompt, list)
        assert prompt[0]["type"] == "text"
        assert "这是什么" in prompt[0]["text"]
        assert "<reference>" not in prompt[0]["text"]
        assert prompt[1]["type"] == "image_url"
        assert prompt[1]["image_url"]["url"].startswith("data:image/png;base64,")

    asyncio.run(run())


def test_handler_retries_without_title_on_conflict(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    async def run() -> None:
        store = AgentStore(tmp_path / "agent.sqlite3")
        client = _TitleConflictClient()
        _patch(monkeypatch, store, client)

        await _invoke(_FakeBot(), _FakeEvent(10, Message("hello")), Message("hello"))
        assert len(client.sessions) == 1
        assert client.sessions[0]["title"] is None
        assert len(client.chats) == 1
        record = await store.lookup_message(bot_id="1", message_id="1002")
        assert record is not None
        assert record.session_id == "s1"

    asyncio.run(run())


def test_handler_starts_new_session_for_direct_or_unknown_quote(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    async def run() -> None:
        store = AgentStore(tmp_path / "agent.sqlite3")
        client = _FakeClient()
        _patch(monkeypatch, store, client)

        await _invoke(_FakeBot(), _FakeEvent(10, Message("first")), Message("first"))
        await _invoke(
            _FakeBot(),
            _FakeEvent(20, Message("second")),
            Message("second"),
        )
        assert len(client.sessions) == 2  # noqa: PLR2004
        assert client.chats[1]["session_id"] == "s2"

        quoted_bot = _FakeBot(
            {
                999: {
                    "message": [
                        {"type": "text", "data": {"text": "outside text"}},
                    ],
                },
            },
        )
        await _invoke(
            quoted_bot,
            _FakeEvent(30, Message("[CQ:reply,id=999] /agent explain")),
            Message("explain"),
        )
        assert len(client.sessions) == 3  # noqa: PLR2004
        prompt = str(client.chats[-1]["message"])
        assert "<reference>" in prompt
        assert "outside text" in prompt
        assert "explain" in prompt

    asyncio.run(run())


def test_handler_renders_assistant_reply_and_falls_back_to_text(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    async def run() -> None:
        store = AgentStore(tmp_path / "agent.sqlite3")
        client = _FakeClient()
        rendered_calls: list[dict[str, Any]] = []
        _patch(monkeypatch, store, client, rendered_calls)

        bot = _FakeBot()
        await _invoke(bot, _FakeEvent(10, Message("hello")), Message("hello"))
        assert rendered_calls == [
            {
                "messages": [
                    {
                        "role": "assistant",
                        "content": [{"type": "text", "text": "final answer"}],
                    },
                ],
            },
        ]
        assert "[CQ:image,file=base64://AAA]" in str(bot.sent[-1])

        async def failing_chat_image_cq(_chat_data: dict[str, Any]) -> Message:
            msg = "playwright unavailable"
            raise RuntimeError(msg)

        monkeypatch.setattr(agent_plugin, "app_chat_image_cq", failing_chat_image_cq)
        fallback_bot = _FakeBot(start_id=2000)
        await _invoke(
            fallback_bot,
            _FakeEvent(20, Message("fallback")),
            Message("fallback"),
        )
        assert "final answer" in str(fallback_bot.sent[-1])

    asyncio.run(run())
