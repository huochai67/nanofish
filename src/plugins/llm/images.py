"""Image generate / edit helpers for llm plugin, dispatched by profile backend.

Backends: OpenAI Images API (SDK), xAI Images API (JSON), Gemini Interactions
API (REST). Other plugins::

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
    http_post,
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


def max_reference_images(profile: ImageModelConfig) -> int:
    """Vendor-specific reference image cap; the global cap stays as a first check."""
    if profile.backend == "grok":
        return 3
    if profile.backend == "gemini":
        return 14
    return MAX_REFERENCE_IMAGES


def _base64_ascii(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _image_data_uri(data: bytes, mime: str) -> str:
    return f"data:{mime};base64,{_base64_ascii(data)}"


async def _grok_request(
    profile: ImageModelConfig,
    path: str,
    payload: dict[str, object],
) -> dict[str, object]:
    """POST a JSON payload to the xAI Images API and return the JSON body."""
    url = f"{profile.api_base.rstrip('/')}/{path}"
    try:
        response = await http_post(
            url,
            headers={"Authorization": f"Bearer {profile.api_key}"},
            json=payload,
            timeout=profile.timeout,
        )
    except HttpRequestError as e:
        raise ImageAPIError(e.message) from e
    try:
        body = response.json()
    except ValueError:
        raise ImageAPIError("生图 API 返回无法解析的图片数据") from None
    if not isinstance(body, dict):
        raise ImageAPIError("生图 API 返回无法解析的图片数据")
    return body


async def _json_data_to_b64_list(
    body: dict[str, object],
    *,
    timeout: float,  # noqa: ASYNC109  # HTTP client timeout
) -> list[str]:
    data = body.get("data")
    if not isinstance(data, list) or not data:
        raise ImageAPIError("生图 API 返回无法解析的图片数据")

    results: list[str] = []
    for item in data:
        if not isinstance(item, dict):
            logger.warning("[LLM/image] item is not an object: %r", item)
            continue
        b64 = item.get("b64_json")
        if isinstance(b64, str) and b64:
            results.append(b64)
            continue
        url = item.get("url")
        if isinstance(url, str) and url:
            raw, _, _ = await _download_image(url, timeout=timeout)
            results.append(_base64_ascii(raw))
            continue
        logger.warning("[LLM/image] item missing b64_json and url: %r", item)
    if not results:
        raise ImageAPIError("生图 API 返回无法解析的图片数据")
    return results


async def _gemini_request(
    profile: ImageModelConfig,
    input: list[dict[str, str]],  # noqa: A002  # matches the Interactions API field
    response_format: dict[str, str],
) -> list[str]:
    """POST one stateless interaction to the Gemini Interactions API.

    ``store`` stays ``False``: /draw is single-turn and never retains
    user reference images server-side.
    """
    url = f"{profile.api_base.rstrip('/')}/interactions"
    payload: dict[str, object] = {
        "model": profile.model,
        "input": input,
        "response_format": response_format,
        "store": False,
    }
    try:
        response = await http_post(
            url,
            headers={"x-goog-api-key": profile.api_key},
            json=payload,
            timeout=profile.timeout,
        )
    except HttpRequestError as e:
        raise ImageAPIError(e.message) from e
    try:
        body = response.json()
    except ValueError:
        raise ImageAPIError("生图 API 返回无法解析的图片数据") from None
    if not isinstance(body, dict):
        raise ImageAPIError("生图 API 返回无法解析的图片数据")

    results = _extract_gemini_images(body)
    if not results:
        raise ImageAPIError("生图 API 未返回图片")
    return results


def _extract_gemini_images(body: dict[str, object]) -> list[str]:
    """Collect non-empty image data from every ``model_output`` step."""
    results: list[str] = []
    steps = body.get("steps")
    if isinstance(steps, list):
        for step in steps:
            if not isinstance(step, dict) or step.get("type") != "model_output":
                continue
            content = step.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "image":
                    continue
                data = block.get("data")
                if isinstance(data, str) and data:
                    results.append(data)
    return results


def _grok_generation_payload(
    profile: ImageModelConfig,
    text: str,
) -> dict[str, object]:
    payload: dict[str, object] = {"model": profile.model, "prompt": text, "n": 1}
    if profile.response_format:
        payload["response_format"] = profile.response_format
    if profile.aspect_ratio:
        payload["aspect_ratio"] = profile.aspect_ratio
    if profile.resolution:
        payload["resolution"] = profile.resolution
    return payload


def _gemini_response_format(profile: ImageModelConfig) -> dict[str, str]:
    response_format: dict[str, str] = {"type": "image"}
    if profile.aspect_ratio:
        response_format["aspect_ratio"] = profile.aspect_ratio
    if profile.resolution:
        response_format["image_size"] = profile.resolution
    return response_format


async def image_generate(
    prompt: str,
    *,
    profile: ImageModelConfig,
) -> list[str]:
    """Text-to-image. Returns base64 strings (no data: prefix). Does not enforce ACL."""
    text = prompt.strip()
    if not text:
        raise ImageAPIError("prompt 不能为空")

    if profile.backend == "openai":
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

    if profile.backend == "grok":
        body = await _grok_request(
            profile, "images/generations", _grok_generation_payload(profile, text)
        )
        return await _json_data_to_b64_list(body, timeout=profile.timeout)

    # gemini
    return await _gemini_request(
        profile,
        [{"type": "text", "text": text}],
        _gemini_response_format(profile),
    )


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
    text = prompt.strip()
    if not text:
        raise ImageAPIError("prompt 不能为空")

    images = [image] if isinstance(image, bytes | str) else list(image)
    if not images:
        raise ImageAPIError("至少需要一张参考图")
    if len(images) > MAX_REFERENCE_IMAGES:
        raise ImageAPIError(f"参考图最多支持 {MAX_REFERENCE_IMAGES} 张")
    limit = max_reference_images(profile)
    if len(images) > limit:
        raise ImageAPIError(f"当前生图后端最多支持 {limit} 张参考图")

    image_files = [
        await _to_file_tuple(item, timeout=profile.timeout, filename=filename)
        for item in images
    ]

    if profile.backend == "openai":
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

    if profile.backend == "grok":
        payload = _grok_generation_payload(profile, text)
        references = [
            {"url": _image_data_uri(data, mime)} for _, data, mime in image_files
        ]
        if len(references) == 1:
            payload["image"] = references[0]
        else:
            payload["images"] = references
        body = await _grok_request(profile, "images/edits", payload)
        return await _json_data_to_b64_list(body, timeout=profile.timeout)

    # gemini
    input_blocks: list[dict[str, str]] = [{"type": "text", "text": text}]
    for _, data, mime in image_files:
        input_blocks.append(
            {"type": "image", "mime_type": mime, "data": _base64_ascii(data)}
        )
    return await _gemini_request(
        profile, input_blocks, _gemini_response_format(profile)
    )


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
    "max_reference_images",
    "openai_error_message",
]
