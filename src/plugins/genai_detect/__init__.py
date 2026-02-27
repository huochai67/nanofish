import json

import httpx
from nonebot import get_plugin_config, logger, on_command
from nonebot.adapters.onebot.v11 import Bot, MessageEvent
from nonebot.adapters.onebot.v11.message import Message
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="genai-detect",
    description="",
    usage="",
)

config = get_plugin_config(Config)
proxy = None
if config.proxy:
    proxy = config.proxy
    # proxy = {"http": config.proxy, "https": config.proxy, "ftp": config.proxy}

genai = on_command("genai", priority=10, block=True, permission=SUPERUSER)


def get_replyid(msg: Message) -> None | int:
    for segment in msg:
        if segment.type == "reply":
            return segment.data.get("id")
    return None


def get_first_image(msg: Message) -> None | str:
    for segment in msg:
        if segment.type == "image":
            return segment.data.get("url")
    return None


async def get_reply(bot: Bot, msg: Message) -> None | dict:
    message_id = get_replyid(msg)
    if message_id:
        return await bot.get_msg(message_id=message_id)
    return None


@genai.handle()
async def handle_function(bot: Bot, event: MessageEvent) -> None:
    msg_reply = await get_reply(bot=bot, msg=event.original_message)
    if not msg_reply:
        await genai.finish("failed get reply")
        return

    imageurl = get_first_image(msg=Message(msg_reply.get("raw_message")))
    if not imageurl:
        await genai.finish("failed get image")
        return

    async with httpx.AsyncClient(proxy=proxy) as client:
        req = await client.get(
            url="https://api.sightengine.com/1.0/check.json",
            params={
                "url": imageurl,
                "models": "genai",
                "api_user": "***REMOVED***",
                "api_secret": "***REMOVED***",
            },
        )

        output = json.loads(req.text)
        if output["status"] != "success":
            logger.debug(f"failed to request api {req}")
            await genai.finish("failed get request api")
            return

    ret = "Uncertain if AI-generated or not"
    rate = float(output["type"]["ai_generated"])
    if rate < 0.2:
        ret = "Not likely to be AI-generated"
    elif rate > 0.8:
        ret = "Likely AI-generated"

    await genai.finish(f"sightengine: {ret}({rate})")
