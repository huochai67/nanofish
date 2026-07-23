"""OpenAI-compatible image generate / edit helpers for llm plugin.

Other plugins::

    require("llm")
    from ..llm import image_generate, image_edit, image_to_cq
"""

from __future__ import annotations

import base64
import mimetypes
from typing import Any
from urllib.parse import urlparse

import httpx
from nonebot import get_plugin_config, logger, require
from nonebot.adapters.onebot.v11.message import Message
from openai import APIStatusError, APITimeoutError, AsyncOpenAI, OpenAIError

from .config import Config

require("utils")
from ..utils import (
    HttpRequestError,
    get_http_proxy,
    http_get,
    request_error_message,
)

config: Config = get_plugin_config(Config)


class ImageAPIError(Exception):
    """Image API failure; ``message`` is safe to show to end users."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


def _client() -> AsyncOpenAI:
    proxy = get_http_proxy()
    http_client = (
        httpx.AsyncClient(proxy=proxy, timeout=config.image_timeout) if proxy else None
    )
    return AsyncOpenAI(
        api_key=config.openai_api_key,
        base_url=config.openai_api_base,
        timeout=config.image_timeout,
        http_client=http_client,
    )


def _optional_kwargs(
    *,
    size: str | None,
    response_format: str | None,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    if size:
        kwargs["size"] = size
    if response_format:
        kwargs["response_format"] = response_format
    return kwargs


def _resolve_model(model: str | None) -> str:
    return model or config.image_model


def _resolve_size(size: str | None) -> str | None:
    return config.image_size if size is None else size


def _resolve_response_format(response_format: str | None) -> str | None:
    return config.image_response_format if response_format is None else response_format


def _guess_filename_and_type(url: str, content_type: str | None) -> tuple[str, str]:
    path = urlparse(url).path
    name = path.rsplit("/", 1)[-1] if path else ""
    if not name or "." not in name:
        name = "image.png"
    mime = (content_type or "").split(";")[0].strip()
    if not mime or not mime.startswith("image/"):
        guessed, _ = mimetypes.guess_type(name)
        mime = guessed or "image/png"
    if name == "image.png" and mime != "image/png":
        ext = mimetypes.guess_extension(mime) or ".png"
        name = f"image{ext}"
    return name, mime


async def _download_image(url: str) -> tuple[bytes, str, str]:
    """Return (bytes, filename, content_type)."""
    try:
        resp = await http_get(url, timeout=config.image_timeout)
    except HttpRequestError as e:
        raise ImageAPIError(e.message) from e
    content_type = resp.headers.get("content-type")
    filename, mime = _guess_filename_and_type(url, content_type)
    if not resp.content:
        raise ImageAPIError("下载参考图失败: 空内容")
    return resp.content, filename, mime


async def _to_file_tuple(
    image: bytes | str,
    *,
    filename: str = "image.png",
) -> tuple[str, bytes, str]:
    if isinstance(image, bytes):
        mime, _ = mimetypes.guess_type(filename)
        return filename, image, mime or "image/png"
    if isinstance(image, str) and image.startswith(("http://", "https://")):
        data, name, mime = await _download_image(image)
        return name, data, mime
    msg = "image 须为 bytes 或 http(s) URL"
    raise ImageAPIError(msg)


async def _response_to_b64_list(response: Any) -> list[str]:
    data = getattr(response, "data", None) or []
    if not data:
        raise ImageAPIError("生图 API 未返回图片")

    results: list[str] = []
    for item in data:
        b64 = getattr(item, "b64_json", None)
        if b64:
            results.append(b64)
            continue
        url = getattr(item, "url", None)
        if url:
            raw, _, _ = await _download_image(url)
            results.append(base64.b64encode(raw).decode("ascii"))
            continue
        logger.warning("[LLM/image] item missing b64_json and url: %r", item)
    if not results:
        raise ImageAPIError("生图 API 返回无法解析的图片数据")
    return results


def openai_error_message(exc: OpenAIError) -> str:
    """Map OpenAI SDK transport failures to the shared HTTP error messages."""
    if isinstance(exc, APITimeoutError):
        return request_error_message(timeout=True)
    if isinstance(exc, APIStatusError):
        body = exc.body
        error = body.get("error") if isinstance(body, dict) else None
        if isinstance(error, dict) and error.get("code") == "moderation_blocked":
            return "请求因安全策略被拒绝，请调整内容后重试"
        return request_error_message(status=exc.status_code)
    return request_error_message()


def _map_openai_error(exc: OpenAIError) -> ImageAPIError:
    return ImageAPIError(openai_error_message(exc))


async def image_generate(
    prompt: str,
    *,
    model: str | None = None,
    size: str | None = None,
    response_format: str | None = None,
) -> list[str]:
    """Text-to-image. Returns base64 strings (no data: prefix). Does not enforce ACL."""
    text = prompt.strip()
    if not text:
        raise ImageAPIError("prompt 不能为空")

    kwargs = _optional_kwargs(
        size=_resolve_size(size),
        response_format=_resolve_response_format(response_format),
    )
    try:
        async with _client() as client:
            response = await client.images.generate(
                model=_resolve_model(model),
                prompt=text,
                n=1,
                **kwargs,
            )
    except OpenAIError as e:
        logger.warning("[LLM/image] generate failed: %s", e)
        raise _map_openai_error(e) from e

    return await _response_to_b64_list(response)


async def image_edit(
    prompt: str,
    image: bytes | str,
    *,
    model: str | None = None,
    size: str | None = None,
    response_format: str | None = None,
    filename: str = "image.png",
) -> list[str]:
    """Image-to-image (edits). ``image`` is raw bytes or downloadable URL.

    Returns base64 strings (no data: prefix). Does not enforce ACL.
    """
    text = prompt.strip()
    if not text:
        raise ImageAPIError("prompt 不能为空")

    name, data, mime = await _to_file_tuple(image, filename=filename)
    kwargs = _optional_kwargs(
        size=_resolve_size(size),
        response_format=_resolve_response_format(response_format),
    )
    try:
        async with _client() as client:
            response = await client.images.edit(
                model=_resolve_model(model),
                image=(name, data, mime),
                prompt=text,
                n=1,
                **kwargs,
            )
    except OpenAIError as e:
        logger.warning("[LLM/image] edit failed: %s", e)
        raise _map_openai_error(e) from e

    return await _response_to_b64_list(response)


def image_to_cq(b64: str) -> Message:
    """Single base64 image → OneBot CQ image message."""
    return Message(f"[CQ:image,file=base64://{b64}]")


def images_to_cq(b64_list: list[str]) -> Message:
    """Multiple base64 images → one Message with several CQ images."""
    msg = Message()
    for b64 in b64_list:
        msg += image_to_cq(b64)
    return msg


__all__ = [
    "ImageAPIError",
    "image_edit",
    "image_generate",
    "image_to_cq",
    "images_to_cq",
    "openai_error_message",
]
