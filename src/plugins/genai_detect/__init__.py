from nonebot import logger, on_command, require
from nonebot.adapters.onebot.v11 import Bot, MessageEvent
from nonebot.adapters.onebot.v11.message import Message
from nonebot.plugin import PluginMetadata

from src.plugin_config import get_yaml_plugin_config

from .config import Config

require("acl")
require("utils")
from ..acl import check_quota, consume_quota, require_command
from ..utils import (
    HttpRequestError,
    finish_processing_reply,
    get_first_image,
    get_reply,
    http_get,
    send_processing_reply,
)

__plugin_meta__ = PluginMetadata(
    name="genai-detect",
    description="AI 生成图片检测",
    usage="回复一张图片后发送 /genai",
    config=Config,
)

config = get_yaml_plugin_config(Config, "genai_detect")

genai = on_command(
    "genai",
    priority=10,
    block=True,
    permission=require_command("genai"),
)

AI_LIKELY_THRESHOLD = 0.8
AI_UNLIKELY_THRESHOLD = 0.2


async def _consume_quota_or_finish(event: MessageEvent) -> None:
    quota = consume_quota(event, "genai")
    if not quota.allowed:
        await genai.finish(quota.message or "额度不足")


@genai.handle()
async def handle_function(bot: Bot, event: MessageEvent) -> None:
    quota = check_quota(event, "genai")
    if not quota.allowed:
        await genai.finish(quota.message or "额度不足")

    msg_reply = await get_reply(bot=bot, msg=event.original_message)
    if not msg_reply:
        await genai.finish("获取被回复消息失败")

    imageurl = get_first_image(msg=Message(msg_reply.get("raw_message")))
    if not imageurl:
        await genai.finish("被回复消息中没有图片")

    processing = await send_processing_reply(genai, bot, event, "正在检测图片，请稍候…")
    try:
        await _consume_quota_or_finish(event)
        req = await http_get(
            "https://api.sightengine.com/1.0/check.json",
            params={
                "url": imageurl,
                "models": "genai",
                "api_user": config.sightengine_api_user,
                "api_secret": config.sightengine_api_secret,
            },
            proxy=config.proxy,
        )
        output = req.json()
    except HttpRequestError as e:
        logger.warning(f"sightengine api error: {e}")
        await finish_processing_reply(
            genai,
            processing,
            e.message,
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("sightengine api unexpected error")
        await finish_processing_reply(
            genai,
            processing,
            f"Sightengine API 处理失败: {type(e).__name__}: {e}",
        )

    if output.get("status") != "success":
        logger.debug(f"sightengine api failed: {output}")
        error = output.get("error") or output.get("message") or output
        await finish_processing_reply(
            genai,
            processing,
            f"Sightengine API 请求失败: {error}",
        )

    try:
        rate = float(output["type"]["ai_generated"])
    except (KeyError, TypeError, ValueError) as e:
        logger.warning(f"sightengine api unexpected response: {output}")
        await finish_processing_reply(
            genai,
            processing,
            f"Sightengine API 返回数据异常: {e}",
        )

    if rate < AI_UNLIKELY_THRESHOLD:
        ret = "不太可能是 AI 生成"
    elif rate > AI_LIKELY_THRESHOLD:
        ret = "很可能是 AI 生成"
    else:
        ret = "无法确定是否为 AI 生成"

    await finish_processing_reply(genai, processing, f"sightengine: {ret} ({rate:.2f})")
