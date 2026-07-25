import asyncio
import base64
import mimetypes
from typing import Any

from nonebot import logger, on_command, require
from nonebot.adapters.onebot.v11 import Bot, MessageEvent
from nonebot.adapters.onebot.v11.message import Message
from nonebot.exception import FinishedException
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata

from src.plugin_config import get_yaml_plugin_config

from .config import Config
from .ehapi import EhAPI, EhMetaData

require("acl")
require("app")
require("utils")
from ..acl import check_quota, consume_quota, require_command
from ..app import app_eh_image_cq
from ..utils import (
    HttpRequestError,
    finish_processing_reply,
    get_plaintext,
    get_reply,
    http_get,
    reply_to_event,
    send_processing_reply,
)

__plugin_meta__ = PluginMetadata(
    name="ehsearch",
    description="E-Hentai 搜索",
    usage="/eh <书名>，或回复一条消息后发送 /eh（结果 HTML 截图回传）",
    config=Config,
)

config = get_yaml_plugin_config(Config, "ehsearch")
ehapi = EhAPI(
    proxy=config.proxy,
    cookies={
        "ipb_member_id": config.eh_ipb_member_id,
        "ipb_pass_hash": config.eh_ipb_pass_hash,
        "sk": config.eh_sk,
        "igneous": config.eh_igneous,
    },
)

ehsearch = on_command("eh", priority=10, block=True, permission=require_command("eh"))


async def resolve_search_query(bot: Bot, event: MessageEvent, arg: Message) -> str:
    """Prefer command args; fall back to plaintext of the replied message."""
    direct = get_plaintext(arg).strip()
    if direct:
        return direct

    msg_reply = await get_reply(bot=bot, msg=event.original_message)
    if not msg_reply:
        return ""

    raw = msg_reply.get("raw_message")
    if not raw:
        return ""
    return get_plaintext(Message(raw)).strip()


async def _thumb_to_data_url(url: str) -> str:
    """Fetch thumbnail via bot proxy; return data URL or empty string on failure."""
    if not url:
        return ""
    try:
        resp = await http_get(url, proxy=config.proxy, timeout=15.0)
        content_type = resp.headers.get("content-type", "").split(";")[0].strip()
        if not content_type or not content_type.startswith("image/"):
            guessed, _ = mimetypes.guess_type(url)
            content_type = guessed or "image/jpeg"
    except Exception as e:  # noqa: BLE001
        logger.debug(f"eh thumb fetch failed: {url!r}: {e}")
        return ""
    else:
        b64 = base64.b64encode(resp.content).decode("ascii")
        return f"data:{content_type};base64,{b64}"


async def build_eh_payload(query: str, results: list[EhMetaData]) -> dict[str, Any]:
    """Build frontend payload; tags stay raw (namespace:tag), translated in Next.js."""
    thumbs = await asyncio.gather(*(_thumb_to_data_url(r.thumb) for r in results))
    items: list[dict[str, Any]] = []
    for r, thumb in zip(results, thumbs, strict=True):
        items.append(
            {
                "title": r.title,
                "title_jpn": r.title_jpn,
                "category": r.category,
                "thumb": thumb,
                "uploader": r.uploader,
                "posted": r.posted,
                "filecount": r.filecount,
                "rating": r.rating,
                "tags": list(r.tags),
                "url": r.url(),
            }
        )
    return {"query": query, "results": items}


@ehsearch.handle()
async def handle_function(
    bot: Bot,
    event: MessageEvent,
    arg: Message = CommandArg(),
) -> None:
    quota = check_quota(event, "eh")
    if not quota.allowed:
        await ehsearch.finish(reply_to_event(event, quota.message or "额度不足"))
        return

    search = await resolve_search_query(bot, event, arg)
    if not search:
        await ehsearch.finish(
            reply_to_event(event, "用法: /eh <书名>，或回复一条含书名的消息后发送 /eh")
        )
        return

    logger.info(f"searching {search}")
    processing = await send_processing_reply(ehsearch, bot, event, "正在搜索，请稍候…")
    try:
        quota = consume_quota(event, "eh")
        if not quota.allowed:
            await ehsearch.finish(reply_to_event(event, quota.message or "额度不足"))
            return
        result = await ehapi.search(title=search, size=3)
        logger.debug(result)

        if not result:
            await finish_processing_reply(ehsearch, processing, event, "未找到相关结果")
            return

        payload = await build_eh_payload(search, result)
        image = await app_eh_image_cq(payload)
        await finish_processing_reply(ehsearch, processing, event, image)
    except FinishedException:
        raise
    except HttpRequestError as e:
        logger.warning(f"ehsearch request error: {e}")
        await finish_processing_reply(ehsearch, processing, event, e.message)
        return
    except Exception as e:  # noqa: BLE001
        logger.exception("ehsearch unexpected error")
        await finish_processing_reply(
            ehsearch,
            processing,
            event,
            f"处理失败: {type(e).__name__}: {e}",
        )
        return
