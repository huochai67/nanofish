import json
import re
from abc import ABC
from asyncio import Task
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

from httpx import AsyncClient, HTTPError
from nonebot import logger
from src.proxy import get_http_proxy_for_url

from ..download import yt_dlp_downloader
from ..exception import IgnoreException, ParseException
from .base import BaseParser, Platform, PlatformEnum, handle, pconfig
from .cookie import save_cookies_with_netscape
from .data import Author, MusicMetadata, ParseResult
from .utils import fmt_duration


@dataclass(frozen=True, slots=True)
class TrackInfo:
    title: str
    artist: str | None = None
    album: str | None = None
    duration: float | None = None
    cover_url: str | None = None


class MusicParser(BaseParser, ABC):
    """Shared metadata, cookie, and best-effort audio handling for music links."""

    cookie_config: ClassVar[str]
    cookie_domain: ClassVar[str]

    def __init__(self) -> None:
        super().__init__()
        self._cookies_file: Path | None = None
        if self._cookie_value:
            pconfig.cache_dir.mkdir(parents=True, exist_ok=True)
            self._cookies_file = pconfig.cache_dir / f"{self.platform.name}_cookies.txt"
            self._write_cookies()

    @property
    def _cookie_value(self) -> str | None:
        return getattr(pconfig, self.cookie_config)

    def _write_cookies(self) -> None:
        if self._cookies_file is not None and self._cookie_value:
            save_cookies_with_netscape(
                self._cookie_value, self._cookies_file, self.cookie_domain
            )

    @property
    def cookie_file(self) -> Path | None:
        if self._cookies_file is not None and not self._cookies_file.exists():
            self._write_cookies()
        return self._cookies_file

    async def parse_track(self, url: str, info: TrackInfo | None = None) -> ParseResult:
        info = info or await self._extract_track_info(url)
        audio_task, audio_notice = await self._download_audio(url, info.duration)
        contents = []

        if audio_task is not None:
            contents.append(
                self.create_audio(audio_task, info.duration or 0.0, info.cover_url)
            )
        elif info.cover_url:
            # Keep the card useful when the source does not expose a playable stream.
            contents.append(self.create_image(info.cover_url, alt=info.title))

        return self.result(
            author=Author(name=info.artist) if info.artist else None,
            title=info.title,
            url=url,
            kind="music",
            music=MusicMetadata(
                artist=info.artist,
                album=info.album,
                duration=info.duration,
            ),
            contents=contents,
            extra={"content_type": "音乐", "info": audio_notice},
        )

    async def _extract_track_info(self, url: str) -> TrackInfo:
        if yt_dlp_downloader is not None:
            try:
                info = await yt_dlp_downloader.extract_audio_info(url, self.cookie_file)
                return TrackInfo(
                    title=info.title,
                    artist=info.artist,
                    album=info.album,
                    duration=info.duration,
                    cover_url=info.thumbnail,
                )
            except Exception:  # noqa: BLE001 - extractors use service-specific exceptions
                logger.debug(f"yt-dlp 无法提取 {self.platform.name} 音乐元数据")

        info = await self.fetch_track_info(url)
        if info is None:
            raise ParseException("无法获取歌曲信息")
        return info

    async def _download_audio(
        self,
        url: str,
        duration: float | None,
    ) -> tuple[Task[Path] | None, str | None]:
        if yt_dlp_downloader is None:
            return None, "未安装 yt-dlp，未下载音频"
        if duration is not None and duration > pconfig.duration_maximum:
            return None, f"音频时长超过 {pconfig.duration_maximum} 秒，未下载"

        task = yt_dlp_downloader.download_audio(url, self.cookie_file, duration)
        try:
            await task
        except IgnoreException as error:
            return None, f"{error.message}，未下载"
        except Exception:  # noqa: BLE001 - download backends use service-specific exceptions
            logger.debug(f"无法下载 {self.platform.name} 音频")
            return None, "音频受授权、登录、地区或 DRM 限制，未下载"
        return task, None

    async def fetch_track_info(self, _url: str) -> TrackInfo | None:
        """Fetch platform-specific metadata when yt-dlp has no extractor support."""
        raise NotImplementedError

    async def _get_json(self, url: str, **kwargs: Any) -> Any | None:
        try:
            async with AsyncClient(
                headers=self.headers,
                timeout=self.timeout,
                proxy=get_http_proxy_for_url(url),
            ) as client:
                response = await client.get(url, follow_redirects=True, **kwargs)
                response.raise_for_status()
                return response.json()
        except (HTTPError, ValueError):
            return None


class YouTubeMusicParser(MusicParser):
    platform: ClassVar[Platform] = Platform(
        name=PlatformEnum.YOUTUBE_MUSIC,
        display_name="YouTube Music",
    )
    cookie_config = "ytmusic_ck"
    cookie_domain = "music.youtube.com"

    @property
    def _cookie_value(self) -> str | None:
        return pconfig.ytmusic_ck or pconfig.ytb_ck

    @handle(
        "music.youtube.com",
        r"music\.youtube\.com/watch\?(?:[^\s#]*&)?v=[A-Za-z0-9_-]+[^\s#]*",
    )
    async def _parse(self, searched: re.Match[str]) -> ParseResult:
        return await self.parse_track(f"https://{searched.group(0)}")

    async def fetch_track_info(self, url: str) -> TrackInfo | None:
        data = await self._get_json(
            "https://www.youtube.com/oembed", params={"url": url, "format": "json"}
        )
        if not isinstance(data, dict) or not isinstance(data.get("title"), str):
            return None
        return TrackInfo(
            title=data["title"],
            artist=data.get("author_name")
            if isinstance(data.get("author_name"), str)
            else None,
            cover_url=data.get("thumbnail_url")
            if isinstance(data.get("thumbnail_url"), str)
            else None,
        )


class SpotifyParser(MusicParser):
    platform: ClassVar[Platform] = Platform(
        name=PlatformEnum.SPOTIFY, display_name="Spotify"
    )
    cookie_config = "spotify_ck"
    cookie_domain = "spotify.com"

    @handle(
        "open.spotify.com",
        r"open\.spotify\.com/(?:intl-[a-z]{2}/)?track/[A-Za-z0-9]+(?:\?[^\s#]*)?",
    )
    async def _parse(self, searched: re.Match[str]) -> ParseResult:
        return await self.parse_track(f"https://{searched.group(0)}")

    @handle("spotify.link", r"spotify\.link/[A-Za-z0-9_-]+")
    async def _parse_short(self, searched: re.Match[str]) -> ParseResult:
        return await self.parse_with_redirect(f"https://{searched.group(0)}")

    async def fetch_track_info(self, url: str) -> TrackInfo | None:
        data = await self._get_json(
            "https://open.spotify.com/oembed", params={"url": url}
        )
        if not isinstance(data, dict) or not isinstance(data.get("title"), str):
            return None
        return TrackInfo(
            title=data["title"],
            artist=data.get("author_name")
            if isinstance(data.get("author_name"), str)
            else None,
            cover_url=data.get("thumbnail_url")
            if isinstance(data.get("thumbnail_url"), str)
            else None,
        )


class NeteaseMusicParser(MusicParser):
    platform: ClassVar[Platform] = Platform(
        name=PlatformEnum.NETEASE_MUSIC,
        display_name="网易云音乐",
    )
    cookie_config = "netease_music_ck"
    cookie_domain = "music.163.com"

    @handle("music.163.com", r"music\.163\.com/(?:#/)?song\?id=(?P<id>\d+)[^\s#]*")
    @handle("y.music.163.com", r"y\.music\.163\.com/m/song\?id=(?P<id>\d+)[^\s#]*")
    async def _parse(self, searched: re.Match[str]) -> ParseResult:
        song_id = searched.group("id")
        url = f"https://music.163.com/#/song?id={song_id}"
        return await self.parse_track(url, await self._fetch_song(song_id))

    @handle("163cn.tv", r"163cn\.tv/[A-Za-z0-9_-]+")
    async def _parse_short(self, searched: re.Match[str]) -> ParseResult:
        return await self.parse_with_redirect(f"https://{searched.group(0)}")

    async def fetch_track_info(self, url: str) -> TrackInfo | None:
        matched = re.search(r"[?&]id=(\d+)", url)
        return await self._fetch_song(matched.group(1)) if matched else None

    async def _fetch_song(self, song_id: str) -> TrackInfo | None:
        data = await self._get_json(
            "https://music.163.com/api/song/detail/",
            params={"ids": f"[{song_id}]"},
        )
        songs = data.get("songs") if isinstance(data, dict) else None
        if not isinstance(songs, list) or not songs or not isinstance(songs[0], dict):
            return None
        song = songs[0]
        album_data = song.get("album")
        album = album_data if isinstance(album_data, dict) else {}
        artists_data = song.get("artists")
        artists = artists_data if isinstance(artists_data, list) else []
        artist_names = [
            name
            for item in artists
            if isinstance(item, dict) and isinstance(name := item.get("name"), str)
        ]
        duration_ms = song.get("duration")
        title = song.get("name")
        return TrackInfo(
            title=title if isinstance(title, str) else "未知歌曲",
            artist=" / ".join(artist_names) or None,
            album=album.get("name") if isinstance(album.get("name"), str) else None,
            duration=duration_ms / 1000
            if isinstance(duration_ms, (int, float))
            else None,
            cover_url=album.get("picUrl")
            if isinstance(album.get("picUrl"), str)
            else None,
        )


class QQMusicParser(MusicParser):
    platform: ClassVar[Platform] = Platform(
        name=PlatformEnum.QQ_MUSIC, display_name="QQ 音乐"
    )
    cookie_config = "qq_music_ck"
    cookie_domain = "qq.com"

    @handle(
        "y.qq.com",
        r"y\.qq\.com/n/ryqq/songDetail/(?P<id>[A-Za-z0-9]+)[^\s#]*",
    )
    @handle(
        "y.qq.com",
        r"y\.qq\.com/n/ryqq_v2/songDetail/(?P<id>\d+)[^\s#]*",
    )
    @handle(
        "y.qq.com",
        r"y\.qq\.com/x/portal/player\.html\?(?:[^\s#]*&)?songmid=(?P<id>[A-Za-z0-9]+)[^\s#]*",
    )
    @handle(
        "i.y.qq.com",
        r"i\.y\.qq\.com/v8/playsong\.html\?(?:[^\s#]*&)?songmid=(?P<id>[A-Za-z0-9]+)[^\s#]*",
    )
    @handle(
        "i.y.qq.com",
        r"i\.y\.qq\.com/v8/playsong\.html\?(?:[^\s#]*&)?songid=(?P<id>\d+)[^\s#]*",
    )
    async def _parse(self, searched: re.Match[str]) -> ParseResult:
        song_id = searched.group("id")
        if "songid=" in searched.group(0) or "ryqq_v2" in searched.group(0):
            url = f"https://y.qq.com/n/ryqq_v2/songDetail/{song_id}"
            info = await self._fetch_song(song_id=int(song_id))
        else:
            url = f"https://y.qq.com/n/ryqq/songDetail/{song_id}"
            info = await self._fetch_song(song_mid=song_id)
        return await self.parse_track(url, info)

    async def fetch_track_info(self, url: str) -> TrackInfo | None:
        if matched := re.search(r"(?:songid=|ryqq_v2/songDetail/)(\d+)", url):
            return await self._fetch_song(song_id=int(matched.group(1)))
        if matched := re.search(r"(?:songDetail/|songmid=)([A-Za-z0-9]+)", url):
            return await self._fetch_song(song_mid=matched.group(1))
        return None

    async def _fetch_song(
        self,
        song_mid: str | None = None,
        song_id: int | None = None,
    ) -> TrackInfo | None:
        param: dict[str, int | str] = {"song_type": 0}
        if song_id is not None:
            param["song_id"] = song_id
        elif song_mid:
            param["song_mid"] = song_mid
        else:
            return None
        payload = {
            "req_0": {
                "module": "music.pf_song_detail_svr",
                "method": "get_song_detail_yqq",
                "param": param,
            }
        }
        data = await self._get_json(
            "https://u.y.qq.com/cgi-bin/musicu.fcg",
            params={
                "format": "json",
                "data": json.dumps(payload, separators=(",", ":")),
            },
        )
        track = (
            data.get("req_0", {}).get("data", {}).get("track_info")
            if isinstance(data, dict)
            else None
        )
        if not isinstance(track, dict):
            return None
        title = track.get("name")
        if not isinstance(title, str) or not title:
            return None
        singers_data = track.get("singer")
        singers = singers_data if isinstance(singers_data, list) else []
        singer_names = [
            name
            for item in singers
            if isinstance(item, dict) and isinstance(name := item.get("name"), str)
        ]
        album_data = track.get("album")
        album = album_data if isinstance(album_data, dict) else {}
        album_mid = album.get("mid")
        cover_url = (
            f"https://y.qq.com/music/photo_new/T002R500x500M000{album_mid}.jpg"
            if isinstance(album_mid, str) and album_mid
            else None
        )
        return TrackInfo(
            title=title,
            artist=" / ".join(singer_names) or None,
            album=album.get("name") if isinstance(album.get("name"), str) else None,
            duration=track.get("interval")
            if isinstance(track.get("interval"), (int, float))
            else None,
            cover_url=cover_url,
        )
