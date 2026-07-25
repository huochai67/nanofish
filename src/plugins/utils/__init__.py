from dataclasses import dataclass
from typing import NoReturn

from nonebot import get_plugin_config, logger
from nonebot.adapters.onebot.v11 import Bot, MessageEvent, MessageSegment
from nonebot.adapters.onebot.v11.message import Message
from nonebot.matcher import Matcher
from nonebot.plugin import PluginMetadata

from .cloudscraper import CloudScraperClient
from .config import Config
from .http import (
    HttpRequestError,
    configure_proxy_environment,
    get_http_proxy,
    http_client,
    http_error_message,
    http_get,
    http_post,
    log_http_trace,
    request_error_message,
)

__plugin_meta__ = PluginMetadata(
    name="utils",
    description="共享消息解析与 HTTP 工具",
    usage="",
    config=Config,
)

_config = get_plugin_config(Config)
configure_proxy_environment()


def get_globalconfig() -> Config:
    return _config


def get_replyid(msg: Message) -> int | None:
    for segment in msg:
        if segment.type == "reply":
            reply_id = segment.data.get("id")
            if reply_id is None:
                return None
            return int(reply_id)
    return None


def get_first_image(msg: Message) -> str | None:
    image_urls = get_image_urls(msg)
    return image_urls[0] if image_urls else None


def get_image_urls(msg: Message) -> list[str]:
    """Return image URLs in their original message order."""
    return [
        str(url)
        for segment in msg
        if segment.type == "image" and (url := segment.data.get("url"))
    ]


def get_plaintext(msg: Message) -> str:
    parts: list[str] = []
    for segment in msg:
        if segment.type == "text":
            text = segment.data.get("text")
            if text:
                parts.append(str(text))
    return "".join(parts)


async def get_reply(bot: Bot, msg: Message) -> dict | None:
    message_id = get_replyid(msg)
    if message_id is None:
        return None
    return await bot.get_msg(message_id=message_id)


def reply_to_event(event: MessageEvent, content: Message | str) -> Message:
    """Build a message that quotes the triggering event."""
    return MessageSegment.reply(event.message_id) + content


@dataclass(frozen=True, slots=True)
class ProcessingReply:
    """A temporary acknowledgement that is removed after the final response."""

    bot: Bot
    message_id: int | None

    async def retract(self) -> None:
        if self.message_id is None:
            return
        try:
            await self.bot.call_api("delete_msg", message_id=self.message_id)
        except Exception:  # noqa: BLE001
            logger.exception("failed to retract processing message %s", self.message_id)


def _sent_message_id(result: object) -> int | None:
    if not isinstance(result, dict):
        logger.warning("processing message send returned no message id: %r", result)
        return None
    message_id = result.get("message_id")
    try:
        return int(message_id)
    except (TypeError, ValueError):
        logger.warning(
            "processing message send returned invalid message id: %r", result
        )
        return None


async def send_processing_reply(
    matcher: Matcher,
    bot: Bot,
    event: MessageEvent,
    text: str,
) -> ProcessingReply:
    """Reply to a request immediately and retain the acknowledgement message id."""
    result = await matcher.send(reply_to_event(event, text))
    return ProcessingReply(bot=bot, message_id=_sent_message_id(result))


async def finish_processing_reply(
    matcher: Matcher,
    processing: ProcessingReply,
    event: MessageEvent,
    message: Message | str,
    *,
    at_sender: bool = False,
) -> NoReturn:
    """Send the final response before retracting its temporary acknowledgement."""
    try:
        await matcher.send(reply_to_event(event, message), at_sender=at_sender)
    finally:
        await processing.retract()
    await matcher.finish()


__all__ = [
    "CloudScraperClient",
    "HttpRequestError",
    "configure_proxy_environment",
    "finish_processing_reply",
    "get_first_image",
    "get_globalconfig",
    "get_http_proxy",
    "get_image_urls",
    "get_plaintext",
    "get_reply",
    "get_replyid",
    "http_client",
    "http_error_message",
    "http_get",
    "http_post",
    "log_http_trace",
    "reply_to_event",
    "request_error_message",
    "send_processing_reply",
]
