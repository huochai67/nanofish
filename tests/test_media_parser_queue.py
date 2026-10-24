import asyncio
import re
from pathlib import Path
from typing import Any

import httpx
import pytest
from nonebot.exception import FinishedException

from src.plugins.media_parser import matchers
from src.plugins.media_parser.delivery import collect_parse_messages
from src.plugins.media_parser.download.ytdlp import describe_ytdlp_error
from src.plugins.media_parser.exception import (
    DeliveryFailure,
    DownloadException,
    IgnoreException,
    ParseException,
    TipException,
    format_parse_error,
    is_retryable,
)
from src.plugins.media_parser.helper import UniHelper
from src.plugins.media_parser.matchers.rule import SearchResult
from src.plugins.media_parser.parsers.data import ImageContent, ParseResult, Platform
from src.plugins.media_parser.parsers.task import PathTask
from src.plugins.media_parser.queue import ParseTaskQueue

_MAX_ATTEMPTS = 3


def test_queue_limits_concurrency_and_runs_all_jobs() -> None:
    async def scenario() -> tuple[int, int]:
        queue = ParseTaskQueue(concurrency=2, max_pending=16, max_retries=0)
        running = 0
        peak = 0

        async def job() -> int:
            nonlocal running, peak
            running += 1
            peak = max(peak, running)
            await asyncio.sleep(0.01)
            running -= 1
            return 1

        try:
            results = await asyncio.gather(*(queue.submit(job) for _ in range(6)))
        finally:
            await queue.shutdown()
        return peak, sum(results)

    assert asyncio.run(scenario()) == (2, 6)


def test_queue_retries_until_success() -> None:
    async def scenario() -> tuple[int, str]:
        queue = ParseTaskQueue(concurrency=1, max_retries=2, retry_delay=0)
        attempts = 0

        async def job() -> str:
            nonlocal attempts
            attempts += 1
            if attempts < _MAX_ATTEMPTS:
                raise RuntimeError("temporary")
            return "ok"

        try:
            result = await queue.submit(job)
        finally:
            await queue.shutdown()
        return attempts, result

    assert asyncio.run(scenario()) == (_MAX_ATTEMPTS, "ok")


def test_queue_stops_after_retries_exhausted() -> None:
    async def scenario() -> int:
        queue = ParseTaskQueue(concurrency=1, max_retries=2, retry_delay=0)
        attempts = 0

        async def job() -> None:
            nonlocal attempts
            attempts += 1
            raise RuntimeError("still broken")

        try:
            with pytest.raises(RuntimeError, match="still broken"):
                await queue.submit(job)
        finally:
            await queue.shutdown()
        return attempts

    assert asyncio.run(scenario()) == _MAX_ATTEMPTS


def test_queue_does_not_retry_non_retryable_errors() -> None:
    async def scenario() -> int:
        queue = ParseTaskQueue(concurrency=1, max_retries=3, retry_delay=0)
        attempts = 0

        async def job() -> None:
            nonlocal attempts
            attempts += 1
            raise TipException("链接无效")

        try:
            with pytest.raises(TipException):
                await queue.submit(job)
        finally:
            await queue.shutdown()
        return attempts

    assert asyncio.run(scenario()) == 1


def test_queue_propagates_matcher_control_flow_without_retry() -> None:
    async def scenario() -> int:
        queue = ParseTaskQueue(concurrency=1, max_retries=3, retry_delay=0)
        attempts = 0

        async def job() -> None:
            nonlocal attempts
            attempts += 1
            raise FinishedException

        try:
            with pytest.raises(FinishedException):
                await queue.submit(job)
        finally:
            await queue.shutdown()
        return attempts

    assert asyncio.run(scenario()) == 1


def test_queue_deduplicates_inflight_jobs() -> None:
    async def scenario() -> tuple[int, list[str]]:
        queue = ParseTaskQueue(concurrency=1, max_retries=0)
        runs = 0

        async def job() -> str:
            nonlocal runs
            runs += 1
            await asyncio.sleep(0.01)
            return "shared"

        try:
            results = await asyncio.gather(
                queue.submit(job, dedupe_key="same-link"),
                queue.submit(job, dedupe_key="same-link"),
            )
        finally:
            await queue.shutdown()
        return runs, results

    assert asyncio.run(scenario()) == (1, ["shared", "shared"])


def test_error_is_retryable_by_type() -> None:
    request = httpx.Request("GET", "https://example.com/video")
    not_found = httpx.HTTPStatusError(
        "not found",
        request=request,
        response=httpx.Response(404, request=request),
    )
    server_error = httpx.HTTPStatusError(
        "server error",
        request=request,
        response=httpx.Response(503, request=request),
    )

    assert is_retryable(ParseException("tmp"))
    assert is_retryable(DownloadException("tmp"))
    assert is_retryable(server_error)
    assert is_retryable(httpx.ReadTimeout("timed out"))
    assert not is_retryable(not_found)
    assert not is_retryable(TipException("invalid"))
    assert not is_retryable(IgnoreException())


def test_format_parse_error_prefers_parser_message() -> None:
    error = ParseException("获取视频信息失败")
    assert format_parse_error(error, "哔哩哔哩") == "哔哩哔哩解析失败：获取视频信息失败"


def test_format_parse_error_maps_http_status() -> None:
    request = httpx.Request("GET", "https://example.com/video")
    error = httpx.HTTPStatusError(
        "not found",
        request=request,
        response=httpx.Response(404, request=request),
    )
    assert format_parse_error(error, "哔哩哔哩") == (
        "哔哩哔哩解析失败：请求失败（HTTP 404）：内容不存在或已被删除"
    )


def test_format_parse_error_keeps_media_failure_detail() -> None:
    error = DownloadException(
        "媒体下载失败：请求失败（HTTP 403）：访问被拒绝",
    )
    assert format_parse_error(error, "微博") == (
        "微博媒体下载失败：请求失败（HTTP 403）：访问被拒绝"
    )


def test_format_parse_error_keeps_delivery_summary() -> None:
    error = DeliveryFailure("2 项媒体下载失败：请求超时，请稍后重试")
    assert (
        format_parse_error(error, "小红书")
        == "小红书：2 项媒体下载失败：请求超时，请稍后重试"
    )


def test_collect_parse_messages_keeps_partial_result_on_media_failure(
    tmp_path: Path,
) -> None:
    async def fail() -> Path:
        raise DownloadException("媒体下载失败：请求超时，请稍后重试")

    async def scenario() -> DeliveryFailure:
        card = tmp_path / "card.png"
        card.write_bytes(b"png")
        result = ParseResult(
            platform=Platform("weibo", "微博"),
            render_image=card,
            contents=[ImageContent(PathTask(fail()))],
        )
        with pytest.raises(DeliveryFailure) as exc_info:
            await collect_parse_messages(result)
        return exc_info.value

    error = asyncio.run(scenario())

    assert len(error.partial_messages) == 1
    assert error.message == "1 项媒体下载失败：请求超时，请稍后重试"


class _Receipt:
    async def recall(self) -> None:
        return None


class _Reply:
    def __init__(self, content: str, sent: list[str]) -> None:
        self.content = content
        self.sent = sent

    async def send(self) -> _Receipt:
        self.sent.append(self.content)
        return _Receipt()


def _install_handler_stubs(
    monkeypatch: pytest.MonkeyPatch,
    *,
    parser: Any,
    collect: Any,
    queue: ParseTaskQueue,
) -> tuple[list[str], list[Any]]:
    sent: list[str] = []
    sent_messages: list[Any] = []

    def reply_to_current_event(_cls: type[UniHelper], content: str) -> _Reply:
        return _Reply(content, sent)

    async def send_messages(messages: list[Any]) -> None:
        sent_messages.extend(messages)

    monkeypatch.setattr(
        UniHelper,
        "reply_to_current_event",
        classmethod(reply_to_current_event),
    )
    monkeypatch.setattr(matchers, "KEYWORD_PARSER_MAP", {"fake-kw": parser})
    monkeypatch.setattr(matchers, "parser_queue", queue)
    monkeypatch.setattr(matchers, "collect_parse_messages", collect)
    monkeypatch.setattr(matchers, "_send_messages", send_messages)
    monkeypatch.setattr(matchers, "_RESULT_CACHE", {})
    return sent, sent_messages


def _fake_parser(parse: Any) -> Any:
    platform = type("Platform", (), {"name": "fake", "display_name": "假平台"})
    return type(
        "FakeParser",
        (),
        {"platform": platform, "parse": staticmethod(parse)},
    )()


def _search_result() -> SearchResult:
    url = "https://example.com/unique-video"
    matched = re.search(r"https://example\.com/\w+", url)
    assert matched is not None
    return SearchResult(url, "fake-kw", matched)


def test_handler_only_sends_final_result_after_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0

    async def parse(_keyword: str, _searched: re.Match[str]) -> object:
        nonlocal attempts
        attempts += 1
        if attempts < _MAX_ATTEMPTS:
            raise RuntimeError("temporary")
        return object()

    parser = _fake_parser(parse)
    queue = ParseTaskQueue(concurrency=1, max_retries=2, retry_delay=0)

    async def collect(_result: object) -> list[str]:
        return ["final-message"]

    sent, sent_messages = _install_handler_stubs(
        monkeypatch,
        parser=parser,
        collect=collect,
        queue=queue,
    )

    async def scenario() -> None:
        try:
            await matchers.parser_handler(_search_result())
        finally:
            await queue.shutdown()

    asyncio.run(scenario())

    assert attempts == _MAX_ATTEMPTS
    assert sent == ["正在解析，请稍候…"]
    assert sent_messages == ["final-message"]


def test_handler_sends_one_specific_error_after_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0

    async def parse(_keyword: str, _searched: re.Match[str]) -> object:
        nonlocal attempts
        attempts += 1
        raise ParseException("平台返回错误")

    parser = _fake_parser(parse)
    queue = ParseTaskQueue(concurrency=1, max_retries=2, retry_delay=0)

    async def collect(_result: object) -> list[str]:
        raise AssertionError("collect must not run when parsing fails")

    sent, sent_messages = _install_handler_stubs(
        monkeypatch,
        parser=parser,
        collect=collect,
        queue=queue,
    )

    async def scenario() -> None:
        try:
            await matchers.parser_handler(_search_result())
        finally:
            await queue.shutdown()

    asyncio.run(scenario())

    assert attempts == _MAX_ATTEMPTS
    assert sent == [
        "正在解析，请稍候…",
        "假平台解析失败：平台返回错误",
    ]
    assert sent_messages == []


def test_handler_sends_partial_result_and_one_error_after_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0

    async def parse(_keyword: str, _searched: re.Match[str]) -> object:
        nonlocal attempts
        attempts += 1
        return object()

    parser = _fake_parser(parse)
    queue = ParseTaskQueue(concurrency=1, max_retries=2, retry_delay=0)

    async def collect(_result: object) -> list[str]:
        raise DeliveryFailure(
            "2 项媒体下载失败：请求超时，请稍后重试",
            ["partial"],
        )

    sent, sent_messages = _install_handler_stubs(
        monkeypatch,
        parser=parser,
        collect=collect,
        queue=queue,
    )

    async def scenario() -> None:
        try:
            await matchers.parser_handler(_search_result())
        finally:
            await queue.shutdown()

    asyncio.run(scenario())

    assert attempts == _MAX_ATTEMPTS
    assert sent == [
        "正在解析，请稍候…",
        "假平台：2 项媒体下载失败：请求超时，请稍后重试",
    ]
    assert sent_messages == ["partial"]


def test_ytdlp_error_mapping_reports_permanent_reason() -> None:
    from yt_dlp.utils import DownloadError

    detail, retryable = describe_ytdlp_error(
        DownloadError(
            "[youtube] abc: Private video. Sign in if you've been granted access"
        )
    )

    assert detail == "视频为私密内容，无法访问"
    assert not retryable


def test_ytdlp_error_mapping_retries_transient_failure() -> None:
    from yt_dlp.utils import DownloadError

    detail, retryable = describe_ytdlp_error(
        DownloadError("Unable to download webpage: The read operation timed out")
    )

    assert detail == "网络请求失败，请稍后重试"
    assert retryable
