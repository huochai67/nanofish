import asyncio
import json

from pytest import MonkeyPatch

from src.plugins.media_parser.parsers.base import BaseParser
from src.plugins.media_parser.parsers.music import (
    MusicParser,
    NeteaseMusicParser,
    QQMusicParser,
    SpotifyParser,
    YouTubeMusicParser,
    pconfig,
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
        (
            QQMusicParser,
            "https://y.qq.com/n/ryqq_v2/songDetail/002l7Fbe2KaBCU",
            "y.qq.com",
        ),
        (
            QQMusicParser,
            "https://i.y.qq.com/v8/playsong.html?songid=653936658#webchat_redirect",
            "i.y.qq.com",
        ),
    ]

    for parser_class, url, expected_keyword in cases:
        keyword, match = parser_class.search_url(url)
        assert keyword == expected_keyword
        assert match.group(0) in url


def test_qq_music_v2_song_mid_uses_full_mid() -> None:
    expected_song_mid = "002l7Fbe2KaBCU"
    parser = QQMusicParser()
    calls: list[tuple[str | None, int | None]] = []

    async def fetch_song(
        song_mid: str | None = None,
        song_id: int | None = None,
    ) -> object:
        calls.append((song_mid, song_id))
        return None

    async def parse_track(url: str, info: object = None) -> object:
        assert url == f"https://y.qq.com/n/ryqq/songDetail/{expected_song_mid}"
        assert info is None
        return None

    parser._fetch_song = fetch_song  # type: ignore[method-assign]
    parser.parse_track = parse_track  # type: ignore[method-assign]
    keyword, match = parser.search_url(
        f"https://y.qq.com/n/ryqq_v2/songDetail/{expected_song_mid}"
    )

    asyncio.run(parser.parse(keyword, match))

    assert match.group("id") == expected_song_mid
    assert calls == [(expected_song_mid, None)]


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


def test_qq_music_song_id_uses_song_id_api_parameter() -> None:
    async def qq_json(*_args: object, **kwargs: object) -> object:
        params = kwargs["params"]
        assert isinstance(params, dict)
        payload = json.loads(params["data"])
        assert payload["req_0"]["param"] == {"song_id": 653936658, "song_type": 0}
        return {
            "req_0": {
                "data": {
                    "track_info": {
                        "name": "Song C",
                        "singer": [],
                        "album": {},
                        "interval": 120,
                    }
                }
            }
        }

    qq = QQMusicParser()
    qq._get_json = qq_json  # type: ignore[method-assign]

    info = asyncio.run(qq._fetch_song(song_id=653936658))

    assert info is not None
    assert info.title == "Song C"


def test_youtube_music_oembed_fallback_maps_metadata() -> None:
    async def youtube_json(*_args: object, **_kwargs: object) -> object:
        return {
            "title": "Song D",
            "author_name": "Artist D",
            "thumbnail_url": "https://example.com/cover.jpg",
        }

    youtube = YouTubeMusicParser()
    youtube._get_json = youtube_json  # type: ignore[method-assign]

    info = asyncio.run(
        youtube.fetch_track_info("https://music.youtube.com/watch?v=test")
    )

    assert info is not None
    assert info.title == "Song D"
    assert info.artist == "Artist D"


def test_youtube_music_uses_youtube_cookie_as_fallback(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(pconfig, "parser_ytmusic_ck", None)
    monkeypatch.setattr(pconfig, "parser_ytb_ck", "youtube-cookie=value")

    parser = YouTubeMusicParser()

    assert parser._cookie_value == "youtube-cookie=value"
