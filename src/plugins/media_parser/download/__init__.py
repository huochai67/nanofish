import asyncio
import weakref
from pathlib import Path
from uuid import uuid4
from functools import partial
from contextlib import contextmanager
from urllib.parse import urljoin

import httpx
import aiofiles
import curl_cffi
from nonebot import logger, get_driver
from rich.progress import (
    Progress,
    BarColumn,
    TextColumn,
    DownloadColumn,
)
from src.proxy import get_http_proxy_from_env

from .task import auto_task
from ..utils import (
    merge_av,
    safe_unlink,
    generate_file_name,
    is_module_available,
    valid_cached_file,
)
from ..config import pconfig
from ..constants import COMMON_HEADER, DOWNLOAD_TIMEOUT
from ..exception import IgnoreException, DownloadException


class StreamDownloader:
    def __init__(self):
        self.headers: dict[str, str] = COMMON_HEADER.copy()
        self.cache_dir: Path = pconfig.cache_dir
        self.client: httpx.AsyncClient = httpx.AsyncClient(
            timeout=DOWNLOAD_TIMEOUT,
            verify=pconfig.verify_ssl,
            proxy=get_http_proxy_from_env(),
        )
        self._target_locks: weakref.WeakValueDictionary[Path, asyncio.Lock] = (
            weakref.WeakValueDictionary()
        )

    async def aclose(self):
        await self.client.aclose()

    def _get_target_lock(self, file_path: Path) -> asyncio.Lock:
        """按最终缓存路径获取下载锁; 同步查找/创建/存储, 不持有强引用"""
        lock = self._target_locks.get(file_path)
        if lock is None:
            lock = asyncio.Lock()
            self._target_locks[file_path] = lock
        return lock

    async def _cached_file(self, file_path: Path) -> Path | None:
        """返回有效的非空缓存文件; 零字节缓存被删除; 非普通文件抛异常"""
        if await valid_cached_file(file_path):
            return file_path
        if file_path.exists():
            raise DownloadException("媒体缓存路径无效")
        return None

    def _temporary_path(self, file_path: Path) -> Path:
        """同目录唯一临时文件路径, 保证 replace 原子性"""
        return file_path.with_name(f".{file_path.name}.{uuid4().hex}.part")

    @staticmethod
    @contextmanager
    def rich_progress(
        desc: str,
        total: int | None = None,
    ):
        with Progress(
            TextColumn("[bold blue]{task.description}", justify="right"),
            BarColumn(bar_width=None),
            "[progress.percentage]{task.percentage:>3.1f}%",
            "•",
            DownloadColumn(),
        ) as progress:
            task_id = progress.add_task(description=desc, total=total)
            yield partial(progress.update, task_id)

    @staticmethod
    def _expected_content_length(
        response: httpx.Response | curl_cffi.Response,
    ) -> int | None:
        """解析 Content-Length; 缺失返回 None, 非法/零抛 DownloadException, 超限抛 IgnoreException"""
        raw = response.headers.get("content-length")
        if raw is None:
            return None

        try:
            content_length = int(raw)
        except ValueError:
            logger.warning(f"媒体 url: {response.url}, Content-Length 非法: {raw!r}")
            raise DownloadException("媒体大小信息无效")

        if content_length <= 0:
            logger.warning(f"媒体 url: {response.url}, 大小为 {content_length}, 取消下载")
            raise DownloadException("媒体大小信息无效")

        if content_length / 1024 / 1024 > pconfig.max_size:
            logger.warning(
                f"媒体 url: {response.url} 大小 {content_length / 1024 / 1024:.2f} MB, "
                f"超过 {pconfig.max_size} MB, 取消下载"
            )
            raise IgnoreException

        return content_length

    async def _write_stream(
        self,
        chunk_iter,
        *,
        file_path: Path,
        desc: str,
        expected_length: int | None,
    ) -> None:
        """流式写入共享逻辑: 运行时字节上限与完整性校验"""
        max_bytes = pconfig.max_size * 1024 * 1024
        completed = 0
        with self.rich_progress(desc, expected_length) as update_progress:
            async with aiofiles.open(file_path, "wb") as file:
                async for chunk in chunk_iter:
                    if completed + len(chunk) > max_bytes:
                        raise IgnoreException(f"媒体大小超过 {pconfig.max_size} MB")
                    await file.write(chunk)
                    completed += len(chunk)
                    update_progress(advance=len(chunk))

        if completed == 0:
            raise DownloadException("媒体下载不完整")
        if expected_length is not None and completed != expected_length:
            raise DownloadException("媒体下载不完整")

    async def _download_file_with_httpx(
        self,
        url: str,
        *,
        file_path: Path,
        headers: dict[str, str],
        chunk_size: int = 64 * 1024,
    ) -> Path:
        """download file by url with stream"""

        async with self.client.stream(
            "GET",
            url,
            headers=headers,
            follow_redirects=True,
        ) as response:
            response.raise_for_status()
            expected_length = self._expected_content_length(response)

            await self._write_stream(
                response.aiter_bytes(chunk_size),
                file_path=file_path,
                desc=f"httpx | {file_path.name}",
                expected_length=expected_length,
            )

        return file_path

    async def _download_file_with_curl_cffi(
        self,
        url: str,
        *,
        file_path: Path,
        headers: dict[str, str],
    ) -> Path:
        async with curl_cffi.AsyncSession(
            allow_redirects=True,
            proxy=get_http_proxy_from_env(),
            verify=pconfig.verify_ssl,
        ) as session:
            response: curl_cffi.Response = await session.get(
                url,
                headers=headers,
                timeout=DOWNLOAD_TIMEOUT,
                stream=True,
            )
            response.raise_for_status()
            expected_length = self._expected_content_length(response)

            await self._write_stream(
                response.aiter_content(chunk_size=8192),
                file_path=file_path,
                desc=f"curl_cffi | {file_path.name}",
                expected_length=expected_length,
            )

        return file_path

    async def _download_file(
        self,
        url: str,
        *,
        file_name: str | None = None,
        ext_headers: dict[str, str] | None = None,
        chunk_size: int = 64 * 1024,
    ) -> Path:
        """download file by url with fallback"""
        if not file_name:
            file_name = generate_file_name(url)
        file_path = self.cache_dir / file_name

        if await self._cached_file(file_path):
            return file_path

        headers = {**self.headers, **(ext_headers or {})}
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        temp_path = self._temporary_path(file_path)

        async with self._get_target_lock(file_path):
            if await self._cached_file(file_path):
                return file_path

            try:
                try:
                    await self._download_file_with_httpx(
                        url,
                        file_path=temp_path,
                        headers=headers,
                        chunk_size=chunk_size,
                    )
                except httpx.HTTPError:
                    logger.opt(exception=True).warning(f"下载失败(httpx) | url: {url}")
                    await self._download_file_with_curl_cffi(
                        url,
                        file_path=temp_path,
                        headers=headers,
                    )
                temp_path.replace(file_path)
            except curl_cffi.CurlError:
                logger.opt(exception=True).warning(f"下载失败(curl_cffi) | url: {url}")
                raise DownloadException("媒体下载失败")
            finally:
                await safe_unlink(temp_path)

            return file_path

    @auto_task
    async def download_video(
        self,
        url: str,
        *,
        video_name: str | None = None,
        ext_headers: dict[str, str] | None = None,
    ) -> Path:
        """download video file by url with stream"""
        if video_name is None:
            video_name = generate_file_name(url, ".mp4")

        return await self._download_file(
            url,
            file_name=video_name,
            ext_headers=ext_headers,
            chunk_size=1024 * 1024,
        )

    @auto_task
    async def download_audio(
        self,
        url: str,
        *,
        audio_name: str | None = None,
        ext_headers: dict[str, str] | None = None,
    ) -> Path:
        """download audio file by url with stream"""
        if audio_name is None:
            audio_name = generate_file_name(url, ".mp3")

        return await self._download_file(
            url,
            file_name=audio_name,
            ext_headers=ext_headers,
        )

    @auto_task
    async def download_img(
        self,
        url: str,
        *,
        img_name: str | None = None,
        ext_headers: dict[str, str] | None = None,
    ) -> Path:
        """download image file by url with stream"""
        if img_name is None:
            img_name = generate_file_name(url, ".jpg")

        return await self._download_file(
            url,
            file_name=img_name,
            ext_headers=ext_headers,
        )

    @auto_task
    async def download_av_and_merge(
        self,
        v_url: str,
        a_url: str,
        *,
        output_path: Path,
        ext_headers: dict[str, str] | None = None,
    ) -> Path:
        """download video and audio file by url with stream and merge"""
        if await self._cached_file(output_path):
            return output_path

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        temp_path = self._temporary_path(output_path)
        v_path = self.cache_dir / generate_file_name(v_url)
        a_path = self.cache_dir / generate_file_name(a_url)

        async with self._get_target_lock(output_path):
            if await self._cached_file(output_path):
                return output_path

            v_task = asyncio.create_task(
                self._download_file(v_url, file_name=v_path.name, ext_headers=ext_headers)
            )
            a_task = asyncio.create_task(
                self._download_file(a_url, file_name=a_path.name, ext_headers=ext_headers)
            )
            try:
                await asyncio.gather(v_task, a_task)
                await merge_av(
                    v_path=v_path,
                    a_path=a_path,
                    output_path=temp_path,
                    output_format=output_path.suffix.lstrip(".").lower() or None,
                )
                temp_path.replace(output_path)
            finally:
                for task in (v_task, a_task):
                    if not task.done():
                        task.cancel()
                await asyncio.gather(v_task, a_task, return_exceptions=True)
                await asyncio.gather(safe_unlink(v_path), safe_unlink(a_path))
                await safe_unlink(temp_path)

            return output_path

    @auto_task
    async def download_m3u8(
        self,
        m3u8_url: str,
        *,
        video_name: str | None = None,
        ext_headers: dict[str, str] | None = None,
    ) -> Path:
        """download m3u8 file by url with stream"""
        if video_name is None:
            video_name = generate_file_name(m3u8_url, ".mp4")

        video_path = self.cache_dir / video_name
        if await self._cached_file(video_path):
            return video_path

        headers = {**self.headers, **(ext_headers or {})}
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        temp_path = self._temporary_path(video_path)

        async with self._get_target_lock(video_path):
            if await self._cached_file(video_path):
                return video_path

            try:
                slices = await self._get_m3u8_slices(m3u8_url, headers=headers)
                if not slices:
                    raise DownloadException("m3u8 视频下载失败")

                total_size = 0
                max_bytes = pconfig.max_size * 1024 * 1024
                with self.rich_progress(desc=video_name) as update_progress:
                    async with aiofiles.open(temp_path, "wb") as f:
                        for url in slices:
                            async with self.client.stream(
                                "GET",
                                url,
                                headers=headers,
                                follow_redirects=True,
                            ) as response:
                                response.raise_for_status()
                                async for chunk in response.aiter_bytes(
                                    chunk_size=1024 * 1024
                                ):
                                    total_size += len(chunk)
                                    if total_size > max_bytes:
                                        raise IgnoreException(
                                            f"媒体大小超过 {pconfig.max_size} MB"
                                        )
                                    await f.write(chunk)
                                    update_progress(advance=len(chunk), total=total_size)

                if total_size == 0:
                    raise DownloadException("m3u8 视频下载失败")

                temp_path.replace(video_path)
            except httpx.HTTPError:
                logger.opt(exception=True).warning(f"m3u8 视频下载失败 | url: {m3u8_url}")
                raise DownloadException("m3u8 视频下载失败")
            finally:
                await safe_unlink(temp_path)

            return video_path

    async def _get_m3u8_slices(
        self,
        m3u8_url: str,
        *,
        headers: dict[str, str],
    ) -> list[str]:
        """获取 m3u8 分片"""

        response = await self.client.get(m3u8_url, headers=headers, follow_redirects=True)
        response.raise_for_status()

        slices_text = response.text
        slices: list[str] = []

        for line in slices_text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            slices.append(urljoin(m3u8_url, line))

        return slices


downloader: StreamDownloader = StreamDownloader()
"""全局下载器实例，提供下载功能"""
yt_dlp_downloader = None
"""yt-dlp 下载器实例，提供下载视频功能，若 yt-dlp 未安装则为 None"""

if is_module_available("yt_dlp"):
    from .ytdlp import YtdlpDownloader

    yt_dlp_downloader = YtdlpDownloader()


@get_driver().on_shutdown
async def close_download_client():
    logger.debug("正在关闭下载器...")
    await downloader.aclose()
