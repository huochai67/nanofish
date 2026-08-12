import asyncio
import tempfile
import weakref
from dataclasses import dataclass
from typing import TYPE_CHECKING
from pathlib import Path

import yt_dlp
from msgspec import Struct, convert
from nonebot import logger
from yt_dlp.utils import DownloadError
from src.proxy import get_http_proxy_from_env

from .task import auto_task
from ..utils import LimitedSizeDict, generate_file_name, valid_cached_file
from ..config import pconfig
from ..exception import IgnoreException, ParseException, TipException


class VideoInfo(Struct):
    title: str
    """标题"""
    channel: str
    """频道名称"""
    uploader: str
    """上传者 id"""
    duration: int
    """时长"""
    timestamp: int
    """发布时间戳"""
    thumbnail: str
    """封面图片"""
    description: str
    """简介"""
    channel_id: str
    """频道 id"""
    view_count: int | None = None
    """播放量"""
    like_count: int | None = None
    """点赞数"""
    comment_count: int | None = None
    """评论数"""

    @property
    def author_name(self) -> str:
        return f"{self.channel}@{self.uploader}"


@dataclass(frozen=True, slots=True)
class AudioInfo:
    """Metadata returned by yt-dlp for a single audio item."""

    title: str
    artist: str | None = None
    album: str | None = None
    duration: float | None = None
    thumbnail: str | None = None
    webpage_url: str | None = None


class YtdlpDownloader:
    def __init__(self):
        if TYPE_CHECKING:
            from yt_dlp import _Params

        self._video_info_mapping = LimitedSizeDict[str, VideoInfo]()
        self._extract_base_opts: _Params = {
            "quiet": True,
            "skip_download": "1",
            "force_generic_extractor": True,
            "js_runtimes": {"node": {}},
        }
        self._download_base_opts: _Params = {"js_runtimes": {"node": {}}}
        self._url_locks: weakref.WeakValueDictionary[str, asyncio.Lock] = (
            weakref.WeakValueDictionary()
        )
        if proxy := get_http_proxy_from_env():
            self._download_base_opts["proxy"] = proxy
            self._extract_base_opts["proxy"] = proxy

    def _get_url_lock(self, url: str) -> asyncio.Lock:
        """按 URL 获取下载锁; 同步查找/创建/存储, 不持有强引用"""
        lock = self._url_locks.get(url)
        if lock is None:
            lock = asyncio.Lock()
            self._url_locks[url] = lock
        return lock

    @staticmethod
    async def _run_ytdlp(func, *args, **kwargs):
        try:
            return await asyncio.to_thread(func, *args, **kwargs)
        except DownloadError as e:
            logger.warning(f"yt-dlp failed: {e}")
            raise TipException("媒体资源获取失败，请稍后重试") from e

    async def extract_video_info(self, url: str, cookiefile: Path | None = None) -> VideoInfo:
        """Get video info by yt-dlp"""

        video_info = self._video_info_mapping.get(url, None)
        if video_info:
            return video_info
        ydl_opts = self._extract_base_opts.copy()

        if cookiefile:
            ydl_opts["cookiefile"] = str(cookiefile)

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = await self._run_ytdlp(ydl.extract_info, url, download=False)
            if not info_dict:
                raise ParseException("获取视频信息失败")

        video_info = convert(info_dict, VideoInfo)
        self._video_info_mapping[url] = video_info
        return video_info

    async def extract_audio_info(self, url: str, cookiefile: Path | None = None) -> AudioInfo:
        """Extract track metadata without requiring a playable audio stream."""
        ydl_opts = self._extract_base_opts.copy()
        # Music pages need their native extractors; generic extraction omits album metadata.
        ydl_opts.pop("force_generic_extractor", None)
        ydl_opts["noplaylist"] = True
        if cookiefile:
            ydl_opts["cookiefile"] = str(cookiefile)

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = await self._run_ytdlp(ydl.extract_info, url, download=False)
        if not info_dict:
            raise ParseException("获取音频信息失败")

        entry = info_dict
        if entries := info_dict.get("entries"):
            entry = next((item for item in entries if item), None)
        if entry is None:
            raise ParseException("获取音频信息失败")
        title = entry.get("title")
        if not isinstance(title, str) or not title:
            raise ParseException("获取音频信息失败")

        artist = entry.get("artist") or entry.get("uploader") or entry.get("channel")
        return AudioInfo(
            title=title,
            artist=artist,
            album=entry.get("album"),
            duration=entry.get("duration"),
            thumbnail=entry.get("thumbnail"),
            webpage_url=entry.get("webpage_url") or url,
        )

    @auto_task
    async def download_video(self, url: str, cookiefile: Path | None = None) -> Path:
        """Download video by yt-dlp"""

        video_info = await self.extract_video_info(url, cookiefile)
        duration = video_info.duration
        if duration > pconfig.duration_maximum:
            logger.warning(f"视频时长 {duration} 秒, 超过 {pconfig.duration_maximum} 秒, 取消下载")
            raise IgnoreException

        video_path = pconfig.cache_dir / generate_file_name(url, ".mp4")
        if await valid_cached_file(video_path):
            return video_path

        async with self._get_url_lock(url):
            if await valid_cached_file(video_path):
                return video_path

            pconfig.cache_dir.mkdir(parents=True, exist_ok=True)

            ydl_opts = self._download_base_opts.copy()
            if cookiefile:
                ydl_opts["cookiefile"] = str(cookiefile)

            with tempfile.TemporaryDirectory(
                dir=pconfig.cache_dir, prefix=f".{video_path.name}."
            ) as attempt_dir:
                attempt_path = Path(attempt_dir) / video_path.name
                ydl_opts["outtmpl"] = str(attempt_path)
                ydl_opts["merge_output_format"] = "mp4"
                ydl_opts["format"] = f"bv[filesize<={duration // 10 + 10}M]+ba/b[filesize<={duration // 8 + 10}M]"
                ydl_opts["postprocessors"] = [{"key": "FFmpegVideoConvertor", "preferedformat": "mp4"}]

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    await self._run_ytdlp(ydl.download, [url])

                if not attempt_path.is_file() or attempt_path.stat().st_size == 0:
                    raise ParseException("视频转换失败")
                if attempt_path.stat().st_size > pconfig.max_size * 1024 * 1024:
                    raise IgnoreException(f"视频大小超过 {pconfig.max_size} MB")
                attempt_path.replace(video_path)

            return video_path

    @auto_task
    async def download_audio(
        self,
        url: str,
        cookiefile: Path | None = None,
        duration: float | None = None,
    ) -> Path:
        """Download audio by yt-dlp"""

        if duration is not None and duration > pconfig.duration_maximum:
            raise IgnoreException(f"音频时长超过 {pconfig.duration_maximum} 秒")

        file_name = generate_file_name(url)
        audio_path = pconfig.cache_dir / f"{file_name}.flac"
        if await valid_cached_file(audio_path):
            return audio_path

        async with self._get_url_lock(url):
            if await valid_cached_file(audio_path):
                return audio_path

            pconfig.cache_dir.mkdir(parents=True, exist_ok=True)

            ydl_opts = self._download_base_opts.copy()
            if cookiefile:
                ydl_opts["cookiefile"] = str(cookiefile)

            with tempfile.TemporaryDirectory(
                dir=pconfig.cache_dir, prefix=f".{audio_path.name}."
            ) as attempt_dir:
                ydl_opts["outtmpl"] = str(Path(attempt_dir) / f"{file_name}.%(ext)s")
                ydl_opts["format"] = "bestaudio/best"
                ydl_opts["postprocessors"] = [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "flac",
                        "preferredquality": "0",
                    }
                ]

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    await self._run_ytdlp(ydl.download, [url])

                flac_path = Path(attempt_dir) / f"{file_name}.flac"
                if not flac_path.is_file() or flac_path.stat().st_size == 0:
                    raise ParseException("音频转换失败")
                if flac_path.stat().st_size > pconfig.max_size * 1024 * 1024:
                    raise IgnoreException(f"音频大小超过 {pconfig.max_size} MB")
                flac_path.replace(audio_path)

            return audio_path
