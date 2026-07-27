import asyncio

import pytest
from nonebot.exception import FinishedException

from src.plugins.media_parser.exception import TipException
from src.plugins.media_parser.helper import UniHelper


class _Receipt:
    def __init__(self) -> None:
        self.recalled = False

    async def recall(self) -> None:
        self.recalled = True


class _Reply:
    def __init__(self, content: str, sent: list[str], receipt: _Receipt) -> None:
        self.content = content
        self.sent = sent
        self.receipt = receipt

    async def send(self) -> _Receipt:
        self.sent.append(self.content)
        return self.receipt


def _stub_replies(monkeypatch: pytest.MonkeyPatch) -> tuple[list[str], _Receipt]:
    sent: list[str] = []
    receipt = _Receipt()

    def reply_to_current_event(_cls: type[UniHelper], content: str) -> _Reply:
        return _Reply(content, sent, receipt)

    monkeypatch.setattr(
        UniHelper,
        "reply_to_current_event",
        classmethod(reply_to_current_event),
    )
    return sent, receipt


def test_processing_reply_is_retracted_after_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent, receipt = _stub_replies(monkeypatch)

    @UniHelper.with_processing_reply
    async def handler() -> str:
        return "done"

    assert asyncio.run(handler()) == "done"
    assert sent == ["正在解析，请稍候…"]
    assert receipt.recalled


def test_processing_reply_quotes_tip_and_retracts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent, receipt = _stub_replies(monkeypatch)

    @UniHelper.with_processing_reply
    async def handler() -> None:
        raise TipException("无效链接")

    assert asyncio.run(handler()) is None
    assert sent == ["正在解析，请稍候…", "无效链接"]
    assert receipt.recalled


def test_processing_reply_quotes_unexpected_errors_and_retracts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent, receipt = _stub_replies(monkeypatch)

    @UniHelper.with_processing_reply
    async def handler() -> None:
        raise RuntimeError("network failed")

    assert asyncio.run(handler()) is None
    assert sent == ["正在解析，请稍候…", "解析失败，请稍后重试"]
    assert receipt.recalled


def test_processing_reply_retracts_before_propagating_finish(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent, receipt = _stub_replies(monkeypatch)

    @UniHelper.with_processing_reply
    async def handler() -> None:
        raise FinishedException

    with pytest.raises(FinishedException):
        asyncio.run(handler())

    assert sent == ["正在解析，请稍候…"]
    assert receipt.recalled
