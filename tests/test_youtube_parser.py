import asyncio
from types import SimpleNamespace

import httpx
from pytest import MonkeyPatch

from src.plugins.media_parser.download.ytdlp import VideoInfo
from src.plugins.media_parser.parsers.youtube import YouTubeParser
from src.plugins.media_parser.parsers.youtube import meta as youtube_meta
import src.plugins.media_parser.parsers.youtube as youtube


def test_youtube_author_lookup_uses_parser_proxy(monkeypatch: MonkeyPatch) -> None:
    options: dict[str, object] = {}

    class Response:
        content = b"response"

        def raise_for_status(self) -> None:
            pass

    class Client:
        def __init__(self, **kwargs: object) -> None:
            options.update(kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args: object) -> None:
            pass

        async def post(self, *_args: object, **_kwargs: object) -> Response:
            return Response()

    monkeypatch.setattr(youtube.httpx, "AsyncClient", Client)
    monkeypatch.setattr(youtube, "get_http_proxy_for_url", lambda *_args: "http://proxy:23333")
    monkeypatch.setattr(
        youtube_meta,
        "decoder",
        SimpleNamespace(
            decode=lambda _content: SimpleNamespace(
                name="Channel", avatar_url=None, description=None
            )
        ),
    )

    author = asyncio.run(YouTubeParser()._fetch_author_info("channel-id"))

    assert options["proxy"] == "http://proxy:23333"
    assert author.name == "Channel"


def test_youtube_parser_falls_back_when_author_lookup_times_out(
    monkeypatch: MonkeyPatch,
) -> None:
    info = VideoInfo(
        title="Video",
        channel="Fallback channel",
        uploader="uploader",
        duration=1,
        timestamp=0,
        thumbnail="https://example.com/thumbnail.jpg",
        description="",
        channel_id="channel-id",
        view_count=123,
        like_count=45,
        comment_count=6,
    )

    class Downloader:
        async def extract_video_info(self, *_args: object) -> VideoInfo:
            return info

        def download_video(self, *_args: object) -> object:
            return object()

    async def timeout(_channel_id: str):
        raise httpx.ConnectTimeout("timed out")

    monkeypatch.setattr(youtube, "yt_dlp_downloader", Downloader())
    parser = YouTubeParser()
    monkeypatch.setattr(parser, "_fetch_author_info", timeout)
    monkeypatch.setattr(parser, "create_video", lambda *_args: None)

    result = asyncio.run(parser.parse_video("https://www.youtube.com/watch?v=test"))

    assert result.author is not None
    assert result.author.name == "Fallback channel"
    assert result.extra["stats"] == {"view": 123, "like": 45, "comment": 6}
