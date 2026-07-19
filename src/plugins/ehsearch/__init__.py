import asyncio
import base64
import mimetypes
from typing import Any

from nonebot import get_plugin_config, logger, on_command, require
from nonebot.adapters.onebot.v11 import Bot, MessageEvent
from nonebot.adapters.onebot.v11.message import Message
from nonebot.exception import FinishedException
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata

from .config import Config
from .ehapi import EhAPI, EhMetaData
from .ehtag import TagTranslator
from .sql import ensure_tag_db

require("acl")
require("app")
require("utils")
from ..acl import check_quota, consume_quota, require_command
from ..app import app_eh_image_cq
from ..utils import HttpRequestError, get_plaintext, get_reply, http_get

__plugin_meta__ = PluginMetadata(
    name="ehsearch",
    description="E-Hentai 搜索",
    usage="/eh <书名>，或回复一条消息后发送 /eh（结果 HTML 截图回传）",
    config=Config,
)

config = get_plugin_config(Config)
ehapi = EhAPI(
    proxy=config.proxy,
    cookies={
        "ipb_member_id": config.eh_ipb_member_id,
        "ipb_pass_hash": config.eh_ipb_pass_hash,
        "sk": config.eh_sk,
        "igneous": config.eh_igneous,
    },
)
# o.db is generated from db.text.json and is not committed to git
ensure_tag_db(config.eh_db)
ehtranslator = TagTranslator(db_path=config.eh_db)

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
        b64 = base64.b64encode(resp.content).decode("ascii")
        return f"data:{content_type};base64,{b64}"
    except Exception as e:  # noqa: BLE001
        logger.debug(f"eh thumb fetch failed: {url!r}: {e}")
        return ""


async def build_eh_payload(query: str, results: list[EhMetaData]) -> dict[str, Any]:
    thumbs = await asyncio.gather(*(_thumb_to_data_url(r.thumb) for r in results))
    items: list[dict[str, Any]] = []
    for r, thumb in zip(results, thumbs, strict=True):
        tags = ehtranslator.trans_all(list(r.tags))
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
                "tags": tags,
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
        await ehsearch.finish(quota.message or "额度不足")
        return

    search = await resolve_search_query(bot, event, arg)
    if not search:
        await ehsearch.finish("用法: /eh <书名>，或回复一条含书名的消息后发送 /eh")
        return

    logger.info(f"searching {search}")
    try:
        consume_quota(event, "eh")
        result = await ehapi.search(title=search, size=3)
        logger.debug(result)

        if not result:
            await ehsearch.finish("未找到相关结果")
            return

        payload = await build_eh_payload(search, result)
        image = await app_eh_image_cq(payload)
        await ehsearch.finish(image)
    except FinishedException:
        raise
    except HttpRequestError as e:
        logger.warning(f"ehsearch request error: {e}")
        await ehsearch.finish(f"请求失败: {e.message}")
        return
    except Exception as e:  # noqa: BLE001
        logger.exception("ehsearch unexpected error")
        await ehsearch.finish(f"处理失败: {type(e).__name__}: {e}")
        return
