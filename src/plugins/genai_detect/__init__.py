import httpx
from nonebot import get_plugin_config, logger, on_command, require
from nonebot.adapters.onebot.v11 import Bot, MessageEvent
from nonebot.adapters.onebot.v11.message import Message
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata

from .config import Config

require("utils")
from ..utils import get_first_image, get_reply

__plugin_meta__ = PluginMetadata(
    name="genai-detect",
    description="AI 生成图片检测",
    usage="回复一张图片后发送 /genai",
    config=Config,
)

config = get_plugin_config(Config)

genai = on_command("genai", priority=10, block=True, permission=SUPERUSER)

AI_LIKELY_THRESHOLD = 0.8
AI_UNLIKELY_THRESHOLD = 0.2


@genai.handle()
async def handle_function(bot: Bot, event: MessageEvent) -> None:
    msg_reply = await get_reply(bot=bot, msg=event.original_message)
    if not msg_reply:
        await genai.finish("获取被回复消息失败")
        return

    imageurl = get_first_image(msg=Message(msg_reply.get("raw_message")))
    if not imageurl:
        await genai.finish("被回复消息中没有图片")
        return

    async with httpx.AsyncClient(proxy=config.proxy) as client:
        req = await client.get(
            url="https://api.sightengine.com/1.0/check.json",
            params={
                "url": imageurl,
                "models": "genai",
                "api_user": config.sightengine_api_user,
                "api_secret": config.sightengine_api_secret,
            },
        )
        req.raise_for_status()
        output = req.json()

    if output.get("status") != "success":
        logger.debug(f"sightengine api failed: {output}")
        await genai.finish("Sightengine API 请求失败")
        return

    rate = float(output["type"]["ai_generated"])
    if rate < AI_UNLIKELY_THRESHOLD:
        ret = "不太可能是 AI 生成"
    elif rate > AI_LIKELY_THRESHOLD:
        ret = "很可能是 AI 生成"
    else:
        ret = "无法确定是否为 AI 生成"

    await genai.finish(f"sightengine: {ret} ({rate:.2f})")
