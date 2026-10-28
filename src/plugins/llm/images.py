"""OpenAI-compatible image generate / edit helpers for llm plugin.

Other plugins::

    require("llm")
    from ..llm import image_generate, image_edit, image_to_cq
"""

from __future__ import annotations

import base64
import mimetypes
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import httpx
from nonebot import logger, require
from nonebot.adapters.onebot.v11.message import Message
from openai import APIStatusError, APITimeoutError, AsyncOpenAI, OpenAIError

from src.proxy import get_http_proxy_for_url

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .config import ImageModelConfig

require("utils")
from ..utils import (  # noqa: I001  # runtime import must follow require()
    HttpRequestError,
    http_get,
    request_error_message,
)


MAX_REFERENCE_IMAGES = 16


class ImageAPIError(Exception):
    """Image API failure; ``message`` is safe to show to end users."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


def _openai_client(profile: ImageModelConfig) -> AsyncOpenAI:
    proxy = get_http_proxy_for_url(profile.api_base)
    http_client = (
        httpx.AsyncClient(proxy=proxy, timeout=profile.timeout) if proxy else None
    )
    return AsyncOpenAI(
        api_key=profile.api_key,
        base_url=profile.api_base,
        timeout=profile.timeout,
        http_client=http_client,
    )


def _optional_kwargs(profile: ImageModelConfig) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    if profile.size:
        kwargs["size"] = profile.size
    if profile.response_format:
        kwargs["response_format"] = profile.response_format
    return kwargs


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


async def _download_image(
    url: str,
    *,
    timeout: float,  # noqa: ASYNC109  # HTTP client timeout
) -> tuple[bytes, str, str]:
    """Return (bytes, filename, content_type)."""
    try:
        resp = await http_get(url, timeout=timeout)
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
    timeout: float,  # noqa: ASYNC109  # HTTP client timeout
    filename: str = "image.png",
) -> tuple[str, bytes, str]:
    if isinstance(image, bytes):
        mime, _ = mimetypes.guess_type(filename)
        return filename, image, mime or "image/png"
    if isinstance(image, str) and image.startswith(("http://", "https://")):
        data, name, mime = await _download_image(image, timeout=timeout)
        return name, data, mime
    msg = "image 须为 bytes 或 http(s) URL"
    raise ImageAPIError(msg)


async def _response_to_b64_list(
    response: Any,
    *,
    timeout: float,  # noqa: ASYNC109  # HTTP client timeout
) -> list[str]:
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
            raw, _, _ = await _download_image(url, timeout=timeout)
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
    profile: ImageModelConfig,
) -> list[str]:
    """Text-to-image. Returns base64 strings (no data: prefix). Does not enforce ACL."""
    if "text_to_image" not in profile.capabilities:
        raise ImageAPIError("当前生图模型不支持文生图")
    text = prompt.strip()
    if not text:
        raise ImageAPIError("prompt 不能为空")

    kwargs = _optional_kwargs(profile)
    try:
        async with _openai_client(profile) as client:
            response = await client.images.generate(
                model=profile.model,
                prompt=text,
                n=1,
                **kwargs,
            )
    except OpenAIError as e:
        logger.warning("[LLM/image] generate failed: %s", e)
        raise _map_openai_error(e) from e
    return await _response_to_b64_list(response, timeout=profile.timeout)


async def image_edit(
    prompt: str,
    image: bytes | str | Sequence[bytes | str],
    *,
    profile: ImageModelConfig,
    filename: str = "image.png",
) -> list[str]:
    """Image-to-image edits using one or more raw images or downloadable URLs.

    Returns base64 strings (no data: prefix). Does not enforce ACL.
    """
    if "image_to_image" not in profile.capabilities:
        raise ImageAPIError("当前生图模型不支持图生图")
    text = prompt.strip()
    if not text:
        raise ImageAPIError("prompt 不能为空")

    images = [image] if isinstance(image, bytes | str) else list(image)
    if not images:
        raise ImageAPIError("至少需要一张参考图")
    if len(images) > MAX_REFERENCE_IMAGES:
        raise ImageAPIError(f"参考图最多支持 {MAX_REFERENCE_IMAGES} 张")

    image_files = [
        await _to_file_tuple(item, timeout=profile.timeout, filename=filename)
        for item in images
    ]
    image_param: Any = image_files[0] if len(image_files) == 1 else image_files
    kwargs = _optional_kwargs(profile)
    try:
        async with _openai_client(profile) as client:
            response = await client.images.edit(
                model=profile.model,
                image=image_param,
                prompt=text,
                n=1,
                **kwargs,
            )
    except OpenAIError as e:
        logger.warning("[LLM/image] edit failed: %s", e)
        raise _map_openai_error(e) from e
    return await _response_to_b64_list(response, timeout=profile.timeout)


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
    "MAX_REFERENCE_IMAGES",
    "ImageAPIError",
    "image_edit",
    "image_generate",
    "image_to_cq",
    "images_to_cq",
    "openai_error_message",
]
