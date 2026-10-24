import uuid
from collections.abc import AsyncGenerator
from itertools import chain
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import aiofiles
from nonebot import logger
from nonebot_plugin_alconna.uniseg import Text

from ..app import BrowserUnavailableError, app_parser_image
from .config import pconfig
from .exception import (
    DeliveryFailure,
    DownloadException,
    IgnoreException,
    describe_error,
    is_retryable,
)
from .helper import ForwardNodeInner, UniHelper, UniMessage
from .parsers import AudioContent, ImageContent, ParseResult, VideoContent
from .parsers.task import PathTask

_MAX_GRID_IMAGES = 9
_MAX_DIRECT_MEDIA = 4


def _normalize_image_url(source_url: str) -> str | None:
    if source_url.startswith("//"):
        return f"https:{source_url}"

    parsed = urlsplit(source_url)
    if parsed.scheme == "https":
        return source_url
    if (
        parsed.scheme == "http"
        and parsed.hostname
        and parsed.hostname.endswith((".hdslb.com", ".xhscdn.com"))
    ):
        return urlunsplit(parsed._replace(scheme="https"))
    return None


def _image_url(source: PathTask | str | None) -> str | None:
    """Return a remote image URL suitable for the frontend screenshot page."""
    if isinstance(source, PathTask):
        source = source.source_url
    return _normalize_image_url(source) if source else None


async def _result_data(result: ParseResult) -> dict[str, Any]:
    author: dict[str, Any] | None = None
    if result.author is not None:
        author = {
            "name": result.author.name,
            "avatar": _image_url(result.author.avatar),
            "pendant": _image_url(result.author.pendant),
            "description": result.author.description,
        }

    data: dict[str, Any] = {
        "kind": result.kind,
        "platform": {
            "name": result.platform.name,
            "displayName": result.platform.display_name,
        },
        "author": author,
        "timestamp": result.timestamp,
        "url": result.url,
        "contentType": result.content_type,
        "extraInfo": result.extra_info,
        "stats": result.extra.get("stats"),
    }

    if result.kind == "music":
        audio = next(
            (content for content in result.contents if isinstance(content, AudioContent)),
            None,
        )
        image = next(
            (content for content in result.contents if isinstance(content, ImageContent)),
            None,
        )
        metadata = result.music
        data.update(
            {
                "title": result.title or "未知曲目",
                "artist": metadata.artist if metadata else result.author.name if result.author else None,
                "album": metadata.album if metadata else None,
                "cover": _image_url(
                    audio.cover if audio else image.path_task if image else None
                ),
                "duration": metadata.duration if metadata else audio.duration if audio else None,
            }
        )
        return data

    media: list[dict[str, Any]] = []
    for content in result.contents:
        if isinstance(content, ImageContent):
            media.append(
                {
                    "kind": "image",
                    "src": _image_url(content.path_task),
                    "alt": content.alt,
                }
            )
        elif isinstance(content, VideoContent):
            media.append(
                {
                    "kind": "video",
                    "poster": _image_url(content.cover),
                    "duration": content.duration,
                    "isGif": content.is_gif,
                }
            )

    graphics: list[dict[str, Any]] = []
    for graphic in result.graphics:
        if isinstance(graphic, str):
            graphics.append({"kind": "text", "text": graphic})
        else:
            graphics.append(
                {
                    "kind": "image",
                    "src": _image_url(graphic.path_task),
                    "alt": graphic.alt,
                }
            )

    if result.repost is not None and result.repost.kind != "post":
        raise ValueError("Only post results can be rendered as reposts")

    data.update(
        {
            "title": result.title,
            "text": result.text,
            "media": media,
            "graphics": graphics,
            "repost": await _result_data(result.repost) if result.repost else None,
        }
    )
    return data


async def _render_card(result: ParseResult) -> bytes:
    payload = {
        "result": await _result_data(result),
        "maxGridImages": _MAX_GRID_IMAGES,
    }
    return await app_parser_image(payload)


async def _save_image(raw: bytes) -> Path:
    image_path = pconfig.cache_dir / f"{uuid.uuid4().hex}.png"
    async with aiofiles.open(image_path, "wb+") as file:
        await file.write(raw)
    return image_path


async def _card_segment(result: ParseResult):
    image_path = result.render_image
    if image_path is None or not image_path.exists():
        try:
            image_raw = await _render_card(result)
        except BrowserUnavailableError as error:
            logger.warning(f"Playwright 不可用，改发文字卡片: {error}")
            return Text(_text_card(result))
        image_path = await _save_image(image_raw)
        result.render_image = image_path
        if pconfig.use_base64:
            return UniHelper.img_seg(image_raw)
    return UniHelper.img_seg(image_path)


def _text_card(result: ParseResult) -> str:
    """Playwright 不可用时的纯文本卡片"""
    lines: list[str] = []
    if result.title:
        lines.append(f"【{result.title}】")
    if result.author is not None and result.author.name:
        lines.append(result.author.name)
    if result.text:
        text = result.text.strip()
        if len(text) > 500:
            text = f"{text[:499]}…"
        lines.append(text)
    return "\n".join(lines) or "解析完成"


def _media_failure_message(errors: list[Exception]) -> str:
    details: list[str] = []
    for error in errors:
        detail = describe_error(error)
        if detail.startswith("媒体下载失败"):
            detail = detail[len("媒体下载失败") :].lstrip("：: ")
        if not detail or detail in details:
            continue
        details.append(detail)

    message = f"{len(errors)} 项媒体下载失败"
    if details:
        message += "：" + "；".join(details[:2])
    return message


async def _media_messages(  # noqa: C901, PLR0912
    result: ParseResult,
) -> AsyncGenerator[UniMessage[Any], None]:
    failed_errors: list[Exception] = []
    mergeable_segs: list[ForwardNodeInner] = []
    other_segs: list[ForwardNodeInner] = []

    def on_error(error: Exception) -> None:
        if not isinstance(error, IgnoreException):
            failed_errors.append(error)

    for content in chain(
        result.contents,
        result.repost.contents if result.repost else (),
    ):
        path = await content.path_task.safe_get(on_error)
        if path is None:
            continue

        match content:
            case VideoContent() as video:
                if video.gif_path and (gif_path := await video.gif_path.safe_get()):
                    mergeable_segs.append(UniHelper.img_seg(gif_path))
                else:
                    yield UniMessage(UniHelper.video_seg(path))
            case AudioContent():
                yield UniMessage(UniHelper.record_seg(path))
            case ImageContent():
                mergeable_segs.append(UniHelper.img_seg(path))

    for content in chain(
        result.graphics,
        result.repost.graphics if result.repost else (),
    ):
        if isinstance(content, str):
            mergeable_segs.append(content)
            continue

        if path := await content.path_task.safe_get(on_error):
            image_seg = UniHelper.img_seg(path)
            if content.alt:
                image_seg += content.alt
            mergeable_segs.append(image_seg)

    if mergeable_segs or other_segs:
        if (
            pconfig.need_forward_contents
            or len(other_segs) > 1
            or (len(mergeable_segs) + len(other_segs)) > _MAX_DIRECT_MEDIA
        ):
            yield UniMessage(
                UniHelper.construct_forward_message(mergeable_segs + other_segs)
            )
        else:
            if mergeable_segs:
                yield UniMessage(mergeable_segs)
            for segment in other_segs:
                yield UniMessage(segment)

    if failed_errors:
        raise DownloadException(
            _media_failure_message(failed_errors),
            retryable=any(is_retryable(error) for error in failed_errors),
        )


async def deliver_parse_result(
    result: ParseResult,
) -> AsyncGenerator[UniMessage[Any], None]:
    """Send the frontend-rendered card followed by parser media attachments."""
    message = UniMessage(await _card_segment(result))
    urls = (result.display_url, result.repost_display_url)
    message += "\n".join(url for url in urls if url)
    yield message

    async for message in _media_messages(result):
        yield message


async def collect_parse_messages(result: ParseResult) -> list[UniMessage[Any]]:
    """收集完整投递内容; 媒体失败时附带已完成的消息一起抛出, 便于最终失败时一次性发送"""
    messages: list[UniMessage[Any]] = []
    try:
        async for message in deliver_parse_result(result):
            messages.append(message)
    except DownloadException as error:
        raise DeliveryFailure(error.message, messages) from error
    return messages
