import asyncio

import nonebot

nonebot.init()
nonebot.load_plugins("src/plugins")

from src.plugins.media_parser.parsers.base import BaseParser
from src.plugins.media_parser.parsers.music import (
    MusicParser,
    NeteaseMusicParser,
    QQMusicParser,
    SpotifyParser,
    YouTubeMusicParser,
)

_NETEASE_DURATION_SECONDS = 213


def test_music_parsers_match_supported_track_urls() -> None:
    cases = [
        (
            YouTubeMusicParser,
            "https://music.youtube.com/watch?v=dQw4w9WgXcQ",
            "music.youtube.com",
        ),
        (
            SpotifyParser,
            "https://open.spotify.com/intl-zh/track/4uLU6hMCjMI75M1A2tKUQC",
            "open.spotify.com",
        ),
        (NeteaseMusicParser, "https://music.163.com/#/song?id=347230", "music.163.com"),
        (
            QQMusicParser,
            "https://y.qq.com/n/ryqq/songDetail/004Z8Ihr0JIu5s",
            "y.qq.com",
        ),
    ]

    for parser_class, url, expected_keyword in cases:
        keyword, match = parser_class.search_url(url)
        assert keyword == expected_keyword
        assert match.group(0) in url


def test_music_parser_base_is_not_registered_as_a_platform() -> None:
    assert MusicParser not in BaseParser.get_all_subclass()


def test_music_metadata_fallbacks_map_platform_responses() -> None:
    async def netease_json(*_args: object, **_kwargs: object) -> object:
        return {
            "songs": [
                {
                    "name": "Song A",
                    "artists": [{"name": "Artist A"}, {"name": "Artist B"}],
                    "album": {
                        "name": "Album A",
                        "picUrl": "https://example.com/cover.jpg",
                    },
                    "duration": 213000,
                }
            ]
        }

    async def qq_json(*_args: object, **_kwargs: object) -> object:
        return {
            "req_0": {
                "data": {
                    "track_info": {
                        "name": "Song B",
                        "singer": [{"name": "Artist C"}],
                        "album": {"name": "Album B", "mid": "album-mid"},
                        "interval": 180,
                    }
                }
            }
        }

    netease = NeteaseMusicParser()
    netease._get_json = netease_json  # type: ignore[method-assign]
    qq = QQMusicParser()
    qq._get_json = qq_json  # type: ignore[method-assign]

    netease_info = asyncio.run(netease._fetch_song("1"))
    qq_info = asyncio.run(qq._fetch_song("song-mid"))

    assert netease_info is not None
    assert netease_info.title == "Song A"
    assert netease_info.artist == "Artist A / Artist B"
    assert netease_info.duration == _NETEASE_DURATION_SECONDS
    assert qq_info is not None
    assert qq_info.title == "Song B"
    assert (
        qq_info.cover_url
        == "https://y.qq.com/music/photo_new/T002R500x500M000album-mid.jpg"
    )
