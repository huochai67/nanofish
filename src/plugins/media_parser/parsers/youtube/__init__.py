import re
from pathlib import Path
from typing import ClassVar

import httpx
from nonebot import logger

from src.proxy import get_http_proxy_for_url
from ..base import Platform, BaseParser, PlatformEnum, handle, pconfig
from ..cookie import save_cookies_with_netscape
from ...download import yt_dlp_downloader


class YouTubeParser(BaseParser):
    platform: ClassVar[Platform] = Platform(name=PlatformEnum.YOUTUBE, display_name="油管")

    def __init__(self):
        super().__init__()
        self._cookies_file: Path | None = None
        if pconfig.ytb_ck:
            pconfig.cache_dir.mkdir(parents=True, exist_ok=True)
            self._cookies_file = pconfig.cache_dir / "ytb_cookies.txt"
            self._write_cookies()

    def _write_cookies(self) -> None:
        if self._cookies_file is not None and pconfig.ytb_ck:
            save_cookies_with_netscape(
                pconfig.ytb_ck,
                self._cookies_file,
                "youtube.com",
            )

    @property
    def cookie_file(self) -> Path | None:
        """Recreate yt-dlp's temporary cookie file after cache cleanup."""
        if self._cookies_file is not None and not self._cookies_file.exists():
            self._write_cookies()
        return self._cookies_file

    @handle("youtu", r"youtu\.be/[A-Za-z\d\._\?%&\+\-=/#]+")
    @handle("youtube", r"youtube\.com/(?:watch|shorts)(?:/[A-Za-z\d_\-]+|\?v=[A-Za-z\d_\-]+)")
    async def _parse_video(self, searched: re.Match[str]):
        url = f"https://{searched.group(0)}"
        return await self.parse_video(url)

    async def parse_video(self, url: str):
        cookie_file = self.cookie_file
        video_info = await yt_dlp_downloader.extract_video_info(url, cookie_file)
        try:
            author = await self._fetch_author_info(video_info.channel_id)
        except httpx.HTTPError as e:
            logger.warning(f"YouTube channel lookup failed: {e}")
            author = self.create_author(video_info.channel)

        stats = {
            key: value
            for key, value in {
                "view": video_info.view_count,
                "like": video_info.like_count,
                "comment": video_info.comment_count,
            }.items()
            if value is not None
        }
        result = self.result(
            author=author,
            title=video_info.title,
            timestamp=video_info.timestamp,
            extra={"stats": stats} if stats else {},
        )

        if video_info.duration <= pconfig.duration_maximum:
            video = yt_dlp_downloader.download_video(url, cookie_file)
            result.video = self.create_video(
                video,
                video_info.thumbnail,
                video_info.duration,
            )
        else:
            result.contents.extend(self.create_images([video_info.thumbnail]))

        return result

    async def _fetch_author_info(self, channel_id: str):
        from . import meta

        url = "https://www.youtube.com/youtubei/v1/browse?prettyPrint=false"
        payload = {
            "context": {
                "client": {
                    "hl": "zh-HK",
                    "gl": "US",
                    "deviceMake": "Apple",
                    "deviceModel": "",
                    "clientName": "WEB",
                    "clientVersion": "2.20251002.00.00",
                    "osName": "Macintosh",
                    "osVersion": "10_15_7",
                },
                "user": {"lockedSafetyMode": False},
                "request": {
                    "useSsl": True,
                    "internalExperimentFlags": [],
                    "consistencyTokenJars": [],
                },
            },
            "browseId": channel_id,
        }

        async with httpx.AsyncClient(
            headers=self.headers,
            proxy=get_http_proxy_for_url(url, pconfig.proxy),
            timeout=self.timeout,
        ) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()

        browse = meta.decoder.decode(response.content)
        return self.create_author(browse.name, browse.avatar_url, browse.description)
