import asyncio

from nonebot import logger, on_command, on_message, require
from nonebot.adapters.onebot.v11 import Bot, MessageEvent, MessageSegment
from nonebot.adapters.onebot.v11.message import Message
from nonebot.plugin import PluginMetadata

from src.plugin_config import get_yaml_plugin_config

from .c2pa_validation import trusted_message
from .config import Config

require("acl")
require("utils")
from ..acl import check_quota, consume_quota, require_command
from ..utils import (
    HttpRequestError,
    ProcessingReply,
    finish_processing_reply,
    get_first_image,
    get_image_urls,
    get_reply,
    http_get,
    send_processing_reply,
)
from .c2pa import inspect_image_url

__plugin_meta__ = PluginMetadata(
    name="genai-detect",
    description="AI 生成图片检测",
    usage="回复一张图片后发送 /genai",
    config=Config,
)

plugin_config = get_yaml_plugin_config(Config, "genai_detect")

genai = on_command(
    "genai",
    priority=10,
    block=True,
    permission=require_command("genai"),
)

c2pa_monitor = on_message(priority=1, block=False)

AI_LIKELY_THRESHOLD = 0.8
AI_UNLIKELY_THRESHOLD = 0.2


async def _consume_quota_or_finish(event: MessageEvent) -> None:
    quota = consume_quota(event, "genai")
    if not quota.allowed:
        await genai.finish(quota.message or "额度不足")


async def _finish_if_trusted_c2pa(processing: ProcessingReply, imageurl: str) -> None:
    result = await inspect_image_url(imageurl, plugin_config)
    if result.trusted:
        await finish_processing_reply(  # type: ignore[reportArgumentType]
            genai,
            processing,
            trusted_message(result),
        )


@c2pa_monitor.handle()
async def handle_received_images(bot: Bot, event: MessageEvent) -> None:
    """Announce only verified embedded Content Credentials for incoming images."""
    if str(event.user_id) == bot.self_id:
        return
    image_urls = get_image_urls(event.original_message)
    if not image_urls:
        return
    results = await asyncio.gather(
        *(inspect_image_url(url, plugin_config) for url in image_urls)
    )
    trusted = [trusted_message(result) for result in results if result.trusted]
    if not trusted:
        return
    message = "检测到可信 C2PA 信息：\n" + "\n".join(
        f"{index}. {text}" for index, text in enumerate(trusted, start=1)
    )
    await c2pa_monitor.send(MessageSegment.reply(event.message_id) + message)


@genai.handle()
async def handle_function(bot: Bot, event: MessageEvent) -> None:
    quota = check_quota(event, "genai")
    if not quota.allowed:
        await genai.finish(quota.message or "额度不足")

    msg_reply = await get_reply(bot=bot, msg=event.original_message)
    if not msg_reply:
        await genai.finish("获取被回复消息失败")
    assert msg_reply is not None

    imageurl = get_first_image(msg=Message(msg_reply.get("raw_message")))
    if not imageurl:
        await genai.finish("被回复消息中没有图片")
    assert imageurl is not None

    processing = await send_processing_reply(
        genai,
        bot,
        event,
        "正在检查 C2PA 凭证并检测图片，请稍候…",
    )
    await _finish_if_trusted_c2pa(processing, imageurl)

    try:
        await _consume_quota_or_finish(event)
        req = await http_get(
            "https://api.sightengine.com/1.0/check.json",
            params={
                "url": imageurl,
                "models": "genai",
                "api_user": plugin_config.sightengine_api_user,
                "api_secret": plugin_config.sightengine_api_secret,
            },
            proxy=plugin_config.proxy,
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
