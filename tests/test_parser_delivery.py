import asyncio
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from nonebot_plugin_alconna.uniseg import Text
from pytest import MonkeyPatch

from src.plugins.app import BrowserUnavailableError
from src.plugins.media_parser import delivery
from src.plugins.media_parser.delivery import _normalize_image_url, _result_data
from src.plugins.media_parser.parsers.base import BaseParser
from src.plugins.media_parser.parsers.data import (
    AudioContent,
    Author,
    ImageContent,
    MusicMetadata,
    ParseResult,
    Platform,
    VideoContent,
)
from src.plugins.media_parser.parsers.task import PathTask


async def _unused_path() -> Path:
    return Path("unused-image.jpg")


def _image_task(source_url: str | None = None) -> PathTask:
    return PathTask(_unused_path(), source_url=source_url)


def test_parser_passes_avatar_and_video_cover_urls_without_downloading(
    monkeypatch: MonkeyPatch,
) -> None:
    def unexpected_download(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("avatar and video cover must not be downloaded")

    monkeypatch.setattr(
        "src.plugins.media_parser.parsers.base.downloader.download_img",
        unexpected_download,
    )

    async def create_media() -> None:
        parser = BaseParser()
        avatar = "https://cdn.example.com/avatar.jpg"
        poster = "https://cdn.example.com/poster.jpg"
        video_task = asyncio.create_task(_unused_path())

        author = parser.create_author("Author", avatar)
        video = parser.create_video(video_task, cover_url=poster)

        assert author.avatar == avatar
        assert video.cover == poster
        assert await video.get_path() == Path("unused-image.jpg")

    asyncio.run(create_media())


def test_delivery_serializes_post_payload() -> None:
    repost = ParseResult(
        platform=Platform("twitter", "X"),
        title="Original post",
    )
    result = ParseResult(
        platform=Platform("bilibili", "哔哩哔哩"),
        title="Post title",
        text="Post text",
        extra={"stats": {"share": 1, "reply": 2, "like": 3}},
        repost=repost,
    )

    data = asyncio.run(_result_data(result))

    assert data["kind"] == "post"
    assert data["title"] == "Post title"
    assert data["text"] == "Post text"
    assert data["media"] == []
    assert data["graphics"] == []
    assert data["repost"]["kind"] == "post"
    assert data["stats"] == {"share": 1, "reply": 2, "like": 3}
    assert "contents" not in data


def test_delivery_serializes_music_payload() -> None:
    duration = 213
    result = ParseResult(
        platform=Platform("spotify", "Spotify"),
        kind="music",
        title="Track title",
        music=MusicMetadata(artist="Artist", album="Album", duration=duration),
    )

    data = asyncio.run(_result_data(result))

    assert data["kind"] == "music"
    assert data["title"] == "Track title"
    assert data["artist"] == "Artist"
    assert data["album"] == "Album"
    assert data["duration"] == duration
    assert data["cover"] is None
    assert "media" not in data
    assert "repost" not in data


def test_delivery_serializes_remote_image_urls_without_base64() -> None:
    avatar = "https://cdn.example.com/avatar.jpg"
    pendant = "https://cdn.example.com/pendant.png"
    image = "https://cdn.example.com/image.jpg"
    poster = "https://cdn.example.com/poster.jpg"
    graphic = "https://cdn.example.com/graphic.jpg"
    cover = "https://cdn.example.com/cover.jpg"

    async def serialize_post():
        result = ParseResult(
            platform=Platform("bilibili", "哔哩哔哩"),
            author=Author(
                name="Author",
                avatar=avatar,
                pendant=pendant,
            ),
            contents=[
                ImageContent(_image_task(image)),
                VideoContent(_image_task(), cover=poster),
            ],
            graphics=[ImageContent(_image_task(graphic))],
        )
        return await _result_data(result)

    data = asyncio.run(serialize_post())

    assert data["author"] == {
        "name": "Author",
        "avatar": avatar,
        "pendant": pendant,
        "description": None,
    }
    assert data["media"] == [
        {"kind": "image", "src": image, "alt": None},
        {"kind": "video", "poster": poster, "duration": None, "isGif": False},
    ]
    assert data["graphics"] == [{"kind": "image", "src": graphic, "alt": None}]

    async def serialize_music():
        music = ParseResult(
            platform=Platform("spotify", "Spotify"),
            kind="music",
            title="Track title",
            contents=[AudioContent(_image_task(), cover=_image_task(cover))],
        )
        return await _result_data(music)

    music_data = asyncio.run(serialize_music())

    assert music_data["cover"] == cover
    assert all(
        not isinstance(value, str) or not value.startswith("data:image/")
        for value in (
            data["author"]["avatar"],
            data["author"]["pendant"],
            data["media"][0]["src"],
            data["media"][1]["poster"],
            data["graphics"][0]["src"],
            music_data["cover"],
        )
    )


def test_delivery_omits_images_without_https_source_url() -> None:
    async def serialize():
        result = ParseResult(
            platform=Platform("bilibili", "哔哩哔哩"),
            author=Author(name="Author", avatar="http://cdn.example.com/avatar.jpg"),
            contents=[
                ImageContent(_image_task("http://cdn.example.com/image.jpg")),
                VideoContent(_image_task(), cover="http://cdn.example.com/poster.jpg"),
            ],
            graphics=[ImageContent(_image_task())],
        )
        return await _result_data(result)

    data = asyncio.run(serialize())

    assert data["author"]["avatar"] is None
    assert data["media"][0]["src"] is None
    assert data["media"][1]["poster"] is None
    assert data["graphics"][0]["src"] is None


def test_delivery_normalizes_bilibili_image_urls_to_https() -> None:
    assert (
        _normalize_image_url("http://i0.hdslb.com/bfs/archive/cover.jpg")
        == "https://i0.hdslb.com/bfs/archive/cover.jpg"
    )
    assert (
        _normalize_image_url("//i0.hdslb.com/bfs/archive/cover.jpg")
        == "https://i0.hdslb.com/bfs/archive/cover.jpg"
    )
    assert _normalize_image_url("http://example.com/cover.jpg") is None


def test_delivery_normalizes_xiaohongshu_image_urls_to_https() -> None:
    assert (
        _normalize_image_url("http://sns-webpic-qc.xhscdn.com/notes/image.jpg")
        == "https://sns-webpic-qc.xhscdn.com/notes/image.jpg"
    )


def test_delivery_always_appends_urls_to_rendered_reply(
    monkeypatch: MonkeyPatch,
) -> None:
    async def card_segment(_result: ParseResult) -> str:
        return "rendered card"

    monkeypatch.setattr(delivery, "_card_segment", card_segment)
    result = ParseResult(
        platform=Platform("twitter", "X"),
        url="https://x.com/example/status/1",
        repost=ParseResult(
            platform=Platform("twitter", "X"),
            url="https://x.com/example/status/2",
        ),
    )

    async def messages() -> AsyncGenerator[Any, None]:
        async for message in delivery.deliver_parse_result(result):
            yield message

    delivered = asyncio.run(anext(messages()))

    assert delivered.extract_plain_text() == (
        "rendered card链接: https://x.com/example/status/1\n"
        "原帖: https://x.com/example/status/2"
    )


def test_card_falls_back_to_text_without_playwright(
    monkeypatch: MonkeyPatch,
) -> None:
    async def unavailable(_result: ParseResult) -> bytes:
        raise BrowserUnavailableError("Playwright 未安装")

    monkeypatch.setattr(delivery, "_render_card", unavailable)
    result = ParseResult(
        platform=Platform("weibo", "微博"),
        author=Author(name="作者"),
        title="标题",
        text="正文内容",
    )

    segment = asyncio.run(delivery._card_segment(result))

    assert isinstance(segment, Text)
    assert segment.text == "【标题】\n作者\n正文内容"
