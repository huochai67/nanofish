import asyncio
from pathlib import Path
from typing import Self

import pytest
import yt_dlp
from yt_dlp.utils import DownloadError

from src.plugins.media_parser import config as media_config
from src.plugins.media_parser.config import pconfig
from src.plugins.media_parser.download.ytdlp import YtdlpDownloader
from src.plugins.media_parser.exception import IgnoreException, TipException
from src.plugins.media_parser.utils import generate_file_name


def test_ytdlp_uses_node_runtime() -> None:
    downloader = YtdlpDownloader()

    assert downloader._extract_base_opts.get("js_runtimes") == {"node": {}}
    assert downloader._download_base_opts.get("js_runtimes") == {"node": {}}


def test_ytdlp_uses_global_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROXY", "http://proxy:23333")

    downloader = YtdlpDownloader()

    assert downloader._extract_base_opts.get("proxy") == "http://proxy:23333"
    assert downloader._download_base_opts.get("proxy") == "http://proxy:23333"


def test_ytdlp_errors_become_user_facing_tips(monkeypatch: pytest.MonkeyPatch) -> None:
    class FailingYoutubeDL:
        def __init__(self, _options: object) -> None:
            pass

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *_args: object) -> None:
            pass

        def extract_info(self, *_args: object, **_kwargs: object) -> None:
            raise DownloadError("format unavailable")

    monkeypatch.setattr(yt_dlp, "YoutubeDL", FailingYoutubeDL)

    with pytest.raises(TipException, match="媒体资源获取失败"):
        asyncio.run(YtdlpDownloader().extract_video_info("https://example.com/video"))


def _video_info_dict(duration: int = 60) -> dict[str, object]:
    return {
        "title": "Test Video",
        "channel": "Channel",
        "uploader": "uploader",
        "duration": duration,
        "timestamp": 1700000000,
        "thumbnail": "https://example.com/thumb.jpg",
        "description": "desc",
        "channel_id": "UC123",
    }


class FakeYoutubeDL:
    """可配置的 yt_dlp.YoutubeDL 假实现; 子类覆写 download"""

    def __init__(self, options: dict[str, object]) -> None:
        self.options = options

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        pass

    def extract_info(self, *_args: object, **_kwargs: object) -> dict[str, object]:
        return _video_info_dict()


def test_ytdlp_video_failure_cleans_attempt_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(media_config, "_cache_dir", tmp_path)

    class FailingDownloadYoutubeDL(FakeYoutubeDL):
        def download(self, _urls: object) -> None:
            outtmpl = Path(str(self.options["outtmpl"]))
            attempt_dir = outtmpl.parent
            attempt_dir.joinpath(outtmpl.name).write_bytes(b"partial")
            attempt_dir.joinpath(f"{outtmpl.name}.part").write_bytes(b"partial")
            attempt_dir.joinpath(f"{outtmpl.name}.ytdl").write_bytes(b"meta")
            attempt_dir.joinpath("frag.f137.mp4").write_bytes(b"frag")
            raise DownloadError("download failed")

    monkeypatch.setattr(yt_dlp, "YoutubeDL", FailingDownloadYoutubeDL)
    downloader = YtdlpDownloader()
    url = "https://example.com/video"
    file_name = generate_file_name(url, ".mp4")

    async def run() -> None:
        await downloader.download_video(url)

    with pytest.raises(TipException, match="媒体资源获取失败"):
        asyncio.run(run())

    assert not (tmp_path / file_name).exists()
    assert not list(tmp_path.glob(f".{file_name}.*"))


def test_ytdlp_audio_failure_does_not_return_partial(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(media_config, "_cache_dir", tmp_path)
    url = "https://example.com/track"
    file_name = generate_file_name(url)

    class FailingAudioYoutubeDL(FakeYoutubeDL):
        def download(self, _urls: object) -> None:
            attempt_dir = Path(str(self.options["outtmpl"])).parent
            attempt_dir.joinpath(f"{file_name}.flac").write_bytes(b"partial")
            raise DownloadError("download failed")

    monkeypatch.setattr(yt_dlp, "YoutubeDL", FailingAudioYoutubeDL)
    downloader = YtdlpDownloader()

    async def run() -> None:
        await downloader.download_audio(url)

    with pytest.raises(TipException, match="媒体资源获取失败"):
        asyncio.run(run())

    assert not (tmp_path / f"{file_name}.flac").exists()
    assert not list(tmp_path.glob(f".{file_name}.flac.*"))


def test_ytdlp_video_rejects_oversize_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(media_config, "_cache_dir", tmp_path)
    monkeypatch.setattr(pconfig, "parser_max_size", 1)

    class OversizeYoutubeDL(FakeYoutubeDL):
        def download(self, _urls: object) -> None:
            Path(str(self.options["outtmpl"])).write_bytes(b"x" * (1024 * 1024 + 1))

    monkeypatch.setattr(yt_dlp, "YoutubeDL", OversizeYoutubeDL)
    downloader = YtdlpDownloader()
    url = "https://example.com/video"
    file_name = generate_file_name(url, ".mp4")

    async def run() -> None:
        await downloader.download_video(url)

    with pytest.raises(IgnoreException, match="视频大小超过 1 MB"):
        asyncio.run(run())

    assert not (tmp_path / file_name).exists()
    assert not list(tmp_path.glob(f".{file_name}.*"))


def test_ytdlp_concurrent_video_download_runs_once(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(media_config, "_cache_dir", tmp_path)
    calls: dict[str, int] = {"downloads": 0}

    class OnceYoutubeDL(FakeYoutubeDL):
        def download(self, _urls: object) -> None:
            calls["downloads"] += 1
            Path(str(self.options["outtmpl"])).write_bytes(b"complete")

    monkeypatch.setattr(yt_dlp, "YoutubeDL", OnceYoutubeDL)
    downloader = YtdlpDownloader()
    url = "https://example.com/video"
    file_name = generate_file_name(url, ".mp4")

    async def run() -> tuple[Path, Path]:
        task1 = downloader.download_video(url)
        task2 = downloader.download_video(url)
        return await asyncio.gather(task1, task2)

    paths = asyncio.run(run())

    assert paths[0] == paths[1] == tmp_path / file_name
    assert calls["downloads"] == 1
    assert (tmp_path / file_name).read_bytes() == b"complete"
