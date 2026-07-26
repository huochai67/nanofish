import asyncio
from pathlib import Path

from pytest import MonkeyPatch

import src.plugins.media_parser.download as media_download


def test_media_downloader_uses_parser_proxy(monkeypatch: MonkeyPatch) -> None:
    options: dict[str, object] = {}

    class Client:
        def __init__(self, **kwargs: object) -> None:
            options.update(kwargs)

    monkeypatch.setattr(media_download.pconfig, "parser_proxy", "http://proxy:23333")
    monkeypatch.setattr(media_download.httpx, "AsyncClient", Client)

    media_download.StreamDownloader()

    assert options["proxy"] == "http://proxy:23333"


def test_curl_fallback_uses_parser_proxy(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    options: dict[str, object] = {}

    class Response:
        headers = {"Content-Length": "1"}
        url = "https://example.com/image.jpg"

        def raise_for_status(self) -> None:
            pass

        async def aiter_content(self, **_kwargs: object):
            yield b"x"

    class Session:
        def __init__(self, **kwargs: object) -> None:
            options.update(kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args: object) -> None:
            pass

        async def get(self, *_args: object, **_kwargs: object) -> Response:
            return Response()

    monkeypatch.setattr(media_download.pconfig, "parser_proxy", "http://proxy:23333")
    monkeypatch.setattr(media_download.curl_cffi, "AsyncSession", Session)

    downloader = media_download.StreamDownloader()
    asyncio.run(
        downloader._download_file_with_curl_cffi(
            "https://example.com/image.jpg",
            file_path=tmp_path / "image.jpg",
            headers={},
        )
    )

    assert options["proxy"] == "http://proxy:23333"
