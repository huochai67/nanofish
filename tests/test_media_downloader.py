import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import ClassVar, Self

import curl_cffi
import httpx
import pytest
from pytest import MonkeyPatch

import src.plugins.media_parser.download as media_download
from src.plugins.media_parser import utils as media_utils
from src.plugins.media_parser.config import pconfig
from src.plugins.media_parser.exception import DownloadException, IgnoreException


def test_media_downloader_uses_global_proxy(monkeypatch: MonkeyPatch) -> None:
    options: dict[str, object] = {}

    class Client:
        def __init__(self, **kwargs: object) -> None:
            options.update(kwargs)

    monkeypatch.setenv("PROXY", "http://proxy:23333")
    monkeypatch.setattr(media_download.httpx, "AsyncClient", Client)

    media_download.StreamDownloader()

    assert options["proxy"] == "http://proxy:23333"


def test_curl_fallback_uses_global_proxy(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    options: dict[str, object] = {}

    class Response:
        headers: ClassVar[dict[str, str]] = {"Content-Length": "1"}
        url: ClassVar[str] = "https://example.com/image.jpg"

        def raise_for_status(self) -> None:
            pass

        async def aiter_content(self, **_kwargs: object):
            yield b"x"

    class Session:
        def __init__(self, **kwargs: object) -> None:
            options.update(kwargs)

        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *_args: object) -> None:
            pass

        async def get(self, *_args: object, **_kwargs: object) -> Response:
            return Response()

    monkeypatch.setenv("PROXY", "http://proxy:23333")
    monkeypatch.setattr(media_download.curl_cffi, "AsyncSession", Session)

    downloader = media_download.StreamDownloader()
    asyncio.run(
        downloader._download_file_with_curl_cffi(
            "https://example.com/image.jpg",
            file_path=tmp_path / "image.jpg",
            headers={},
        )
    )

    assert options["proxy"] == "http://proxy:23333"


class FakeResponse:
    """流式假响应; chunks 中的元素可为 bytes 或中途抛出的异常"""

    def __init__(
        self,
        *,
        headers: dict[str, str] | None = None,
        chunks: list[bytes | Exception] | None = None,
        url: str = "https://example.com/file.mp4",
    ) -> None:
        self.headers = headers or {}
        self.chunks = list(chunks or [])
        self.url = url
        self.iterated = 0

    def raise_for_status(self) -> None:
        pass

    async def aiter_bytes(self, _chunk_size: int) -> AsyncIterator[bytes]:
        for item in self.chunks:
            if isinstance(item, Exception):
                raise item
            self.iterated += 1
            yield item

    async def aiter_content(self, **_kwargs: object) -> AsyncIterator[bytes]:
        async for item in self.aiter_bytes(0):
            yield item


class FakeStream:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response

    async def __aenter__(self) -> FakeResponse:
        return self.response

    async def __aexit__(self, *_args: object) -> None:
        pass


class FakeClient:
    """httpx.AsyncClient 假实现; stream/get 按调用顺序弹出响应"""

    def __init__(
        self, responses: list[FakeResponse] | None = None, **_kwargs: object
    ) -> None:
        self.responses = list(responses or [])
        self.streams = 0
        self.gets = 0

    async def aclose(self) -> None:
        pass

    def stream(self, _method: str, _url: str, **_kwargs: object) -> FakeStream:
        self.streams += 1
        return FakeStream(self.responses.pop(0))

    async def get(self, _url: str, **_kwargs: object) -> FakeResponse:
        self.gets += 1
        return self.responses.pop(0)


class FakeCurlSession:
    """curl_cffi.AsyncSession 假实现"""

    def __init__(
        self, responses: list[FakeResponse] | None = None, **kwargs: object
    ) -> None:
        self.responses = list(responses or [])
        self.options = dict(kwargs)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_args: object) -> None:
        pass

    async def get(self, *_args: object, **_kwargs: object) -> FakeResponse:
        return self.responses.pop(0)


def test_media_downloader_verifies_tls_by_default(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    client_options: dict[str, object] = {}
    session_options: dict[str, object] = {}

    class CapturingClient(FakeClient):
        def __init__(self, **kwargs: object) -> None:
            client_options.update(kwargs)
            super().__init__()

    class CapturingSession(FakeCurlSession):
        def __init__(self, **kwargs: object) -> None:
            session_options.update(kwargs)
            super().__init__(
                responses=[
                    FakeResponse(headers={"content-length": "1"}, chunks=[b"x"])
                ],
                **kwargs,
            )

    monkeypatch.setattr(media_download.httpx, "AsyncClient", CapturingClient)
    monkeypatch.setattr(media_download.curl_cffi, "AsyncSession", CapturingSession)

    downloader = media_download.StreamDownloader()
    downloader.cache_dir = tmp_path
    assert client_options["verify"] is True
    asyncio.run(downloader.aclose())

    monkeypatch.setattr(pconfig, "parser_verify_ssl", False)
    downloader = media_download.StreamDownloader()
    downloader.cache_dir = tmp_path
    assert client_options["verify"] is False

    asyncio.run(
        downloader._download_file_with_curl_cffi(
            "https://example.com/file.mp4",
            file_path=tmp_path / "file.mp4",
            headers={},
        )
    )
    assert session_options["verify"] is False
    asyncio.run(downloader.aclose())


def test_download_file_cleans_partial_after_both_backends_fail(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    httpx_response = FakeResponse(
        headers={"content-length": "2"},
        chunks=[b"a", httpx.ReadError("read failed")],
    )
    curl_response = FakeResponse(
        headers={"content-length": "2"},
        chunks=[b"b", curl_cffi.CurlError("curl failed")],
    )
    client = FakeClient([httpx_response])
    session = FakeCurlSession([curl_response])
    monkeypatch.setattr(media_download.httpx, "AsyncClient", lambda **_kw: client)
    monkeypatch.setattr(
        media_download.curl_cffi, "AsyncSession", lambda **_kw: session
    )

    downloader = media_download.StreamDownloader()
    downloader.cache_dir = tmp_path

    with pytest.raises(DownloadException, match="媒体下载失败"):
        asyncio.run(
            downloader._download_file(
                "https://example.com/file.mp4", file_name="file.mp4"
            )
        )

    assert not (tmp_path / "file.mp4").exists()
    assert not list(tmp_path.glob("*.part"))
    asyncio.run(downloader.aclose())


def test_zero_byte_cache_is_redownloaded(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "file.mp4").write_bytes(b"")
    client = FakeClient(
        [FakeResponse(headers={"content-length": "5"}, chunks=[b"hello"])]
    )
    monkeypatch.setattr(media_download.httpx, "AsyncClient", lambda **_kw: client)

    downloader = media_download.StreamDownloader()
    downloader.cache_dir = tmp_path

    path = asyncio.run(
        downloader._download_file(
            "https://example.com/file.mp4", file_name="file.mp4"
        )
    )

    assert path == tmp_path / "file.mp4"
    assert (tmp_path / "file.mp4").read_bytes() == b"hello"
    assert client.streams == 1
    assert not list(tmp_path.glob("*.part"))
    asyncio.run(downloader.aclose())


def test_concurrent_duplicate_downloads_fetch_once(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    client = FakeClient(
        [FakeResponse(headers={"content-length": "10"}, chunks=[b"video-data"])]
    )
    monkeypatch.setattr(media_download.httpx, "AsyncClient", lambda **_kw: client)

    downloader = media_download.StreamDownloader()
    downloader.cache_dir = tmp_path
    url = "https://example.com/file.mp4"

    async def run_concurrent():
        task1 = downloader.download_video(url, video_name="file.mp4")
        task2 = downloader.download_video(url, video_name="file.mp4")
        return await asyncio.gather(task1, task2)

    paths = asyncio.run(run_concurrent())

    assert paths[0] == paths[1] == tmp_path / "file.mp4"
    assert client.streams == 1
    assert (tmp_path / "file.mp4").read_bytes() == b"video-data"
    asyncio.run(downloader.aclose())


def test_missing_content_length_uses_runtime_limit(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(pconfig, "parser_max_size", 1)

    # 无 Content-Length 且未超限 → 成功
    client = FakeClient([FakeResponse(chunks=[b"small-data"])])
    monkeypatch.setattr(media_download.httpx, "AsyncClient", lambda **_kw: client)
    downloader = media_download.StreamDownloader()
    downloader.cache_dir = tmp_path

    path = asyncio.run(
        downloader._download_file(
            "https://example.com/file.mp4", file_name="file.mp4"
        )
    )
    assert path == tmp_path / "file.mp4"
    assert (tmp_path / "file.mp4").read_bytes() == b"small-data"
    asyncio.run(downloader.aclose())

    # 无 Content-Length 但流式超限 → IgnoreException, 无残留
    (tmp_path / "file.mp4").unlink()
    client = FakeClient(
        [FakeResponse(chunks=[b"x" * (512 * 1024), b"y" * (512 * 1024 + 1)])]
    )
    monkeypatch.setattr(media_download.httpx, "AsyncClient", lambda **_kw: client)
    downloader = media_download.StreamDownloader()
    downloader.cache_dir = tmp_path

    with pytest.raises(IgnoreException, match="媒体大小超过 1 MB"):
        asyncio.run(
            downloader._download_file(
                "https://example.com/file.mp4", file_name="file.mp4"
            )
        )

    assert not (tmp_path / "file.mp4").exists()
    assert not list(tmp_path.glob("*.part"))
    asyncio.run(downloader.aclose())


def test_content_length_mismatch_does_not_publish_file(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    # 声明 10 字节, 实际仅发出 3 字节 → 完整性失败, 不发布
    client = FakeClient(
        [FakeResponse(headers={"content-length": "10"}, chunks=[b"abc"])]
    )
    monkeypatch.setattr(media_download.httpx, "AsyncClient", lambda **_kw: client)
    downloader = media_download.StreamDownloader()
    downloader.cache_dir = tmp_path

    with pytest.raises(DownloadException, match="媒体下载不完整"):
        asyncio.run(
            downloader._download_file(
                "https://example.com/file.mp4", file_name="file.mp4"
            )
        )

    assert not (tmp_path / "file.mp4").exists()
    assert not list(tmp_path.glob("*.part"))
    asyncio.run(downloader.aclose())

    # 声明即超限 → 流迭代前拒绝
    monkeypatch.setattr(pconfig, "parser_max_size", 1)
    declared = FakeResponse(
        headers={"content-length": str(2 * 1024 * 1024)}, chunks=[b"x"]
    )
    client = FakeClient([declared])
    monkeypatch.setattr(media_download.httpx, "AsyncClient", lambda **_kw: client)
    downloader = media_download.StreamDownloader()
    downloader.cache_dir = tmp_path

    with pytest.raises(IgnoreException):
        asyncio.run(
            downloader._download_file(
                "https://example.com/file.mp4", file_name="file.mp4"
            )
        )

    assert declared.iterated == 0
    assert not (tmp_path / "file.mp4").exists()
    assert not list(tmp_path.glob("*.part"))
    asyncio.run(downloader.aclose())


def test_m3u8_slice_error_cleans_staging(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    manifest_seen: dict[str, object] = {}
    slice_seen: dict[str, object] = {}

    class ManifestResponse(FakeResponse):
        def __init__(self) -> None:
            super().__init__(url="https://example.com/index.m3u8")
            self.text = "#EXTM3U\n#EXT-X-VERSION:3\n\nsegment0.ts\n"

    request = httpx.Request("GET", "https://example.com/segment0.ts")
    status_error = httpx.HTTPStatusError(
        "404 Not Found", request=request, response=httpx.Response(404, request=request)
    )

    class SliceResponse(FakeResponse):
        def __init__(self) -> None:
            super().__init__(url="https://example.com/segment0.ts")
            self.status_error = status_error

        def raise_for_status(self) -> None:
            raise self.status_error

    class RecordingClient(FakeClient):
        async def get(self, url: str, **kwargs: object) -> FakeResponse:
            manifest_seen.update(kwargs)
            return await super().get(url, **kwargs)

        def stream(self, method: str, url: str, **kwargs: object) -> FakeStream:
            slice_seen.update(kwargs)
            return super().stream(method, url, **kwargs)

    client = RecordingClient([ManifestResponse(), SliceResponse()])
    monkeypatch.setattr(media_download.httpx, "AsyncClient", lambda **_kw: client)

    downloader = media_download.StreamDownloader()
    downloader.cache_dir = tmp_path

    async def run() -> None:
        await downloader.download_m3u8(
            "https://example.com/index.m3u8", video_name="acfun_123.mp4"
        )

    with pytest.raises(DownloadException, match="m3u8 视频下载失败"):
        asyncio.run(run())

    assert manifest_seen["follow_redirects"] is True
    assert manifest_seen["headers"] == downloader.headers
    assert slice_seen["follow_redirects"] is True
    assert slice_seen["headers"] == downloader.headers
    assert not (tmp_path / "acfun_123.mp4").exists()
    assert not list(tmp_path.glob("*.part"))
    asyncio.run(downloader.aclose())


def test_download_av_and_merge_failure_cleans_components(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    merge_kwargs: dict[str, object] = {}

    async def failing_merge_av(**_kwargs: object) -> None:
        merge_kwargs.update(_kwargs)
        raise RuntimeError("ffmpeg failed")

    monkeypatch.setattr(media_download, "merge_av", failing_merge_av)

    client = FakeClient(
        [
            FakeResponse(headers={"content-length": "3"}, chunks=[b"vid"]),
            FakeResponse(headers={"content-length": "3"}, chunks=[b"aud"]),
        ]
    )
    monkeypatch.setattr(media_download.httpx, "AsyncClient", lambda **_kw: client)

    downloader = media_download.StreamDownloader()
    downloader.cache_dir = tmp_path
    output_path = tmp_path / "merged.mp4"

    async def run() -> None:
        await downloader.download_av_and_merge(
            "https://example.com/v.mp4",
            "https://example.com/a.mp4",
            output_path=output_path,
        )

    with pytest.raises(RuntimeError, match="ffmpeg failed"):
        asyncio.run(run())

    assert not output_path.exists()
    assert not list(tmp_path.glob("*.part"))
    assert list(tmp_path.iterdir()) == []

    # 合并必须携带最终路径的封装格式, 否则 ffmpeg 无法从 .part 暂存名推断格式
    assert merge_kwargs["output_format"] == "mp4"
    staged = Path(str(merge_kwargs["output_path"]))
    assert staged.name.startswith(".merged.mp4.") and staged.name.endswith(".part")
    asyncio.run(downloader.aclose())


def test_merge_av_forwards_format_to_ffmpeg(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, list[str]] = {}

    async def fake_exec(cmd: list[str]) -> None:
        captured["cmd"] = cmd

    monkeypatch.setattr(media_utils, "exec_ffmpeg_cmd", fake_exec)

    v_path = tmp_path / "v.mp4"
    a_path = tmp_path / "a.mp4"
    output_path = tmp_path / ".merged.mp4.deadbeef.part"
    v_path.write_bytes(b"v")
    a_path.write_bytes(b"a")
    output_path.write_bytes(b"merged")

    asyncio.run(
        media_utils.merge_av(
            v_path=v_path,
            a_path=a_path,
            output_path=output_path,
            output_format="mp4",
        )
    )

    cmd = captured["cmd"]
    assert cmd[cmd.index("-f") + 1] == "mp4"
    assert cmd[-1] == str(output_path)
