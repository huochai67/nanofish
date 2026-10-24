import asyncio
import json
from typing import Any, cast

import httpx
import pytest
from nonebot.adapters.onebot.v11 import Bot, Message, MessageEvent
from pytest import MonkeyPatch

from src.plugins.hermes_agent import build_message_content, parse_agent_args, split_text
from src.plugins.hermes_agent.client import (
    HermesAuthError,
    HermesClient,
    HermesMissingKeyError,
    HermesSessionNotFoundError,
)
from src.plugins.hermes_agent.config import Config
from src.plugins.hermes_agent.reference import (
    ImageAttachment,
    ReferenceContext,
    collect_reference,
)
from src.plugins.hermes_agent.store import AgentStore


def test_store_maps_bot_message_to_session(tmp_path: Any) -> None:
    async def run() -> None:
        store = AgentStore(tmp_path / "agent.sqlite3")
        await store.register_session(
            session_id="s1",
            profile="",
            scope="private:42",
            owner_id=42,
        )
        await store.record_messages(
            bot_id="1",
            session_id="s1",
            profile="",
            scope="private:42",
            messages=[
                ("10", "user", "hello"),
                ("11", "assistant", "hi there"),
            ],
        )
        record = await store.lookup_message(bot_id="1", message_id="11")
        assert record is not None
        assert record.session_id == "s1"
        assert record.role == "assistant"
        assert record.content == "hi there"
        assert record.scope == "private:42"
        assert await store.lookup_message(bot_id="2", message_id="11") is None

    asyncio.run(run())


def test_client_creates_and_chats_with_default_profile() -> None:
    calls: list[tuple[str, str, str]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(
            (
                request.method,
                request.url.path,
                request.headers.get("authorization", ""),
            ),
        )
        if request.url.path == "/api/sessions":
            assert json.loads(request.content) == {
                "source": "api_server",
                "title": "hi",
            }
            return httpx.Response(
                201,
                json={"object": "hermes.session", "session": {"id": "s1"}},
            )
        if request.url.path == "/api/sessions/s1/chat":
            assert json.loads(request.content) == {"message": "hi"}
            return httpx.Response(
                200,
                json={
                    "object": "hermes.session.chat.completion",
                    "status": "completed",
                    "session_id": "s1",
                    "message": {"role": "assistant", "content": "hello"},
                },
            )
        return httpx.Response(404)

    client = HermesClient(
        Config(agent_api_key="key", agent_endpoint="http://hermes"),
        transport=httpx.MockTransport(handler),
    )

    async def run() -> None:
        session_id = await client.create_session("", "hi")
        result = await client.chat(profile="", session_id=session_id, message="hi")
        assert session_id == "s1"
        assert result.content == "hello"
        assert result.status == "completed"

    asyncio.run(run())
    assert calls == [
        ("POST", "/api/sessions", "Bearer key"),
        ("POST", "/api/sessions/s1/chat", "Bearer key"),
    ]


def test_client_uses_profile_prefix_and_profile_key() -> None:
    paths: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        assert request.headers.get("authorization") == "Bearer profile-key"
        return httpx.Response(
            201,
            json={"object": "hermes.session", "session": {"id": "s2"}},
        )

    client = HermesClient(
        Config(
            agent_api_key="default-key",
            agent_endpoint="http://hermes",
            agent_profiles={"test-bot": "profile-key"},
        ),
        transport=httpx.MockTransport(handler),
    )

    async def run() -> None:
        assert await client.create_session("test-bot", "hi") == "s2"

    asyncio.run(run())
    assert paths == ["/p/test-bot/api/sessions"]


def test_client_reports_missing_session() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404,
            json={
                "error": {
                    "message": "Session not found: gone",
                    "code": "session_not_found",
                },
            },
        )

    client = HermesClient(
        Config(agent_api_key="key", agent_endpoint="http://hermes"),
        transport=httpx.MockTransport(handler),
    )

    async def run() -> None:
        with pytest.raises(HermesSessionNotFoundError):
            await client.chat(profile="", session_id="gone", message="hi")

    asyncio.run(run())


def test_client_requires_profile_key_before_request() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={})

    client = HermesClient(
        Config(agent_api_key="default-key", agent_endpoint="http://hermes"),
        transport=httpx.MockTransport(handler),
    )

    async def run() -> None:
        with pytest.raises(HermesMissingKeyError, match="mc"):
            await client.create_session("mc")

    asyncio.run(run())
    assert requests == []


def test_client_reports_auth_failure() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={"error": {"message": "Invalid gateway API key"}},
        )

    client = HermesClient(
        Config(agent_api_key="key", agent_endpoint="http://hermes"),
        transport=httpx.MockTransport(handler),
    )

    async def run() -> None:
        with pytest.raises(HermesAuthError):
            await client.create_session("")

    asyncio.run(run())


def test_parse_agent_args() -> None:
    assert parse_agent_args(Message("hello")) == (None, "hello")
    assert parse_agent_args(Message("@test-bot hello")) == ("test-bot", "hello")
    assert parse_agent_args(Message("@test-bot")) == ("test-bot", "")
    assert parse_agent_args(Message("")) == (None, "")


def test_split_text_prefers_newlines() -> None:
    text = "a" * 60 + "\n" + "b" * 60
    chunks = split_text(text, 100)
    assert chunks == ["a" * 60, "b" * 60]


def test_build_message_content_includes_reference_and_images() -> None:
    reference = ReferenceContext(
        text_parts=["quoted"],
        images=[ImageAttachment("x.png", "data:image/png;base64,AAAA")],
    )
    content = build_message_content(reference, "question")
    assert isinstance(content, list)
    assert content[0]["type"] == "text"
    assert "<reference>" in content[0]["text"]
    assert "question" in content[0]["text"]
    assert content[1]["type"] == "image_url"


class _FakeBot:
    self_id = "1"

    def __init__(self, response: dict[str, Any] | None = None) -> None:
        self.response = response
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call_api(self, api: str, **kwargs: Any) -> Any:
        self.calls.append((api, kwargs))
        if self.response is None:
            msg = "no response"
            raise RuntimeError(msg)
        return self.response


class _FakeEvent:
    original_message = Message("[CQ:reply,id=100] /agent hi")


def test_collect_reference_continues_session_from_db(tmp_path: Any) -> None:
    async def run() -> None:
        store = AgentStore(tmp_path / "agent.sqlite3")
        await store.record_messages(
            bot_id="1",
            session_id="s1",
            profile="",
            scope="private:42",
            messages=[("100", "assistant", "previous answer")],
        )
        reference = await collect_reference(
            cast("Bot", _FakeBot()),
            cast("MessageEvent", _FakeEvent()),
            store,
            Config(),
            scope="private:42",
        )
        assert reference.session_id == "s1"
        assert reference.profile == ""
        assert reference.has_content
        assert "previous answer" in reference.render()

    asyncio.run(run())


def test_collect_reference_does_not_cross_scope(tmp_path: Any) -> None:
    async def run() -> None:
        store = AgentStore(tmp_path / "agent.sqlite3")
        await store.record_messages(
            bot_id="1",
            session_id="s1",
            profile="",
            scope="group:1",
            messages=[("100", "assistant", "group answer")],
        )
        reference = await collect_reference(
            cast("Bot", _FakeBot()),
            cast("MessageEvent", _FakeEvent()),
            store,
            Config(),
            scope="private:42",
        )
        assert reference.session_id is None
        assert "group answer" in reference.render()

    asyncio.run(run())


def test_collect_reference_reads_plain_text(tmp_path: Any) -> None:
    bot = _FakeBot(
        {
            "message": [
                {"type": "text", "data": {"text": "original message"}},
            ],
        },
    )

    async def run() -> None:
        store = AgentStore(tmp_path / "agent.sqlite3")
        reference = await collect_reference(
            cast("Bot", bot),
            cast("MessageEvent", _FakeEvent()),
            store,
            Config(),
            scope="private:42",
        )
        assert reference.session_id is None
        assert "original message" in reference.render()
        assert bot.calls == [("get_msg", {"message_id": 100})]

    asyncio.run(run())


def test_collect_reference_inlines_image(
    tmp_path: Any,
    monkeypatch: MonkeyPatch,
) -> None:
    bot = _FakeBot(
        {
            "message": [
                {
                    "type": "image",
                    "data": {
                        "url": "https://cdn.example.com/a.png",
                        "file_name": "a.png",
                    },
                },
            ],
        },
    )

    async def fake_download(_url: str, _max_bytes: int) -> tuple[bytes, str]:
        return b"\x89PNG\r\n\x1a\npayload", "image/png"

    monkeypatch.setattr(
        "src.plugins.hermes_agent.reference._download",
        fake_download,
    )

    async def run() -> None:
        store = AgentStore(tmp_path / "agent.sqlite3")
        reference = await collect_reference(
            cast("Bot", bot),
            cast("MessageEvent", _FakeEvent()),
            store,
            Config(),
            scope="private:42",
        )
        assert len(reference.images) == 1
        assert reference.images[0].data_url.startswith("data:image/png;base64,")

    asyncio.run(run())


def test_collect_reference_uses_url_for_oversized_text_file(
    tmp_path: Any,
    monkeypatch: MonkeyPatch,
) -> None:
    bot = _FakeBot(
        {
            "message": [
                {"type": "text", "data": {"text": "q" * 100}},
                {
                    "type": "file",
                    "data": {
                        "url": "https://cdn.example.com/a.txt",
                        "file_name": "a.txt",
                    },
                },
            ],
        },
    )

    async def fake_download(_url: str, _max_bytes: int) -> tuple[bytes, str]:
        return b"y" * 300, "text/plain"

    monkeypatch.setattr(
        "src.plugins.hermes_agent.reference._download",
        fake_download,
    )

    async def run() -> None:
        store = AgentStore(tmp_path / "agent.sqlite3")
        reference = await collect_reference(
            cast("Bot", bot),
            cast("MessageEvent", _FakeEvent()),
            store,
            Config(agent_reference_max_chars=100),
            scope="private:42",
        )
        rendered = reference.render()
        assert "[文件: a.txt]（文本过长，未内联" in rendered
        assert "https://cdn.example.com/a.txt" in rendered
        assert "y" * 20 not in rendered

    asyncio.run(run())


def test_collect_reference_inlines_text_file(
    tmp_path: Any,
    monkeypatch: MonkeyPatch,
) -> None:
    bot = _FakeBot(
        {
            "message": [
                {
                    "type": "file",
                    "data": {
                        "url": "https://cdn.example.com/a.txt",
                        "file_name": "a.txt",
                    },
                },
            ],
        },
    )

    async def fake_download(_url: str, _max_bytes: int) -> tuple[bytes, str]:
        return b"file body", "text/plain"

    monkeypatch.setattr(
        "src.plugins.hermes_agent.reference._download",
        fake_download,
    )

    async def run() -> None:
        store = AgentStore(tmp_path / "agent.sqlite3")
        reference = await collect_reference(
            cast("Bot", bot),
            cast("MessageEvent", _FakeEvent()),
            store,
            Config(),
            scope="private:42",
        )
        rendered = reference.render()
        assert "[引用文件: a.txt]" in rendered
        assert "file body" in rendered

    asyncio.run(run())
