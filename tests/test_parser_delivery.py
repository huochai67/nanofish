import asyncio

from src.plugins.media_parser.delivery import _result_data
from src.plugins.media_parser.parsers.data import MusicMetadata, ParseResult, Platform


def test_delivery_serializes_post_payload() -> None:
    repost = ParseResult(
        platform=Platform("twitter", "X"),
        title="Original post",
    )
    result = ParseResult(
        platform=Platform("bilibili", "哔哩哔哩"),
        title="Post title",
        text="Post text",
        repost=repost,
    )

    data = asyncio.run(_result_data(result))

    assert data["kind"] == "post"
    assert data["title"] == "Post title"
    assert data["text"] == "Post text"
    assert data["media"] == []
    assert data["graphics"] == []
    assert data["repost"]["kind"] == "post"
    assert "contents" not in data


def test_delivery_serializes_music_payload() -> None:
    result = ParseResult(
        platform=Platform("spotify", "Spotify"),
        kind="music",
        title="Track title",
        music=MusicMetadata(artist="Artist", album="Album", duration=213),
    )

    data = asyncio.run(_result_data(result))

    assert data["kind"] == "music"
    assert data["title"] == "Track title"
    assert data["artist"] == "Artist"
    assert data["album"] == "Album"
    assert data["duration"] == 213
    assert data["cover"] is None
    assert "media" not in data
    assert "repost" not in data
