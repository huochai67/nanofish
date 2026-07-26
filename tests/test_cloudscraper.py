import asyncio
from types import TracebackType
from typing import Any, ClassVar, Self

import httpx
import pytest
from pytest import MonkeyPatch

from src.plugins.utils.cloudscraper import CloudScraperClient
from src.plugins.utils.config import Config
from src.plugins.utils.http import HttpRequestError

_HTTP_OK = 200


class _RecordingAsyncClient:
    requests: ClassVar[list[tuple[str, str]]] = []
    status_code: ClassVar[int] = _HTTP_OK

    def __init__(self, **kwargs: Any) -> None:
        del kwargs

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc, traceback

    async def request(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> httpx.Response:
        del kwargs
        self.requests.append((method, url))
        return httpx.Response(
            self.status_code,
            request=httpx.Request(method, url),
        )


def _configure_direct_client(monkeypatch: MonkeyPatch, *, status_code: int) -> None:
    _RecordingAsyncClient.requests = []
    _RecordingAsyncClient.status_code = status_code
    monkeypatch.setattr(
        "src.plugins.utils.cloudscraper.httpx.AsyncClient",
        _RecordingAsyncClient,
    )


def test_empty_flaresolverr_url_uses_direct_request(monkeypatch: MonkeyPatch) -> None:
    _configure_direct_client(monkeypatch, status_code=_HTTP_OK)
    client = CloudScraperClient(config=Config(flaresolverr_url=""))

    response = asyncio.run(client.get("https://example.com/path"))

    assert response.status_code == _HTTP_OK
    assert _RecordingAsyncClient.requests == [("GET", "https://example.com/path")]


@pytest.mark.parametrize("status_code", [403, 503])
def test_empty_flaresolverr_url_does_not_retry_challenge(
    monkeypatch: MonkeyPatch,
    status_code: int,
) -> None:
    _configure_direct_client(monkeypatch, status_code=status_code)
    client = CloudScraperClient(config=Config(flaresolverr_url=""))

    with pytest.raises(HttpRequestError) as exc_info:
        asyncio.run(client.get("https://example.com/challenge"))

    assert exc_info.value.status == status_code
    assert _RecordingAsyncClient.requests == [("GET", "https://example.com/challenge")]
