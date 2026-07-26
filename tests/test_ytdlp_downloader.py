import asyncio

import pytest
import yt_dlp
from yt_dlp.utils import DownloadError

from src.plugins.media_parser.download.ytdlp import YtdlpDownloader
from src.plugins.media_parser.exception import TipException


def test_ytdlp_uses_node_runtime() -> None:
    downloader = YtdlpDownloader()

    assert downloader._extract_base_opts.get("js_runtimes") == {"node": {}}
    assert downloader._download_base_opts.get("js_runtimes") == {"node": {}}


def test_ytdlp_errors_become_user_facing_tips(monkeypatch: pytest.MonkeyPatch) -> None:
    class FailingYoutubeDL:
        def __init__(self, _options: object) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            pass

        def extract_info(self, *_args: object, **_kwargs: object) -> None:
            raise DownloadError("format unavailable")

    monkeypatch.setattr(yt_dlp, "YoutubeDL", FailingYoutubeDL)

    with pytest.raises(TipException, match="媒体资源获取失败"):
        asyncio.run(YtdlpDownloader().extract_video_info("https://example.com/video"))
