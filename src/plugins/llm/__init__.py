from nonebot import logger, on_command, require
from nonebot.adapters.onebot.v11 import Bot, Message, MessageEvent
from nonebot.exception import FinishedException
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata

from src.plugin_config import get_yaml_plugin_config

require("acl")
require("utils")
from ..acl import (
    QuotaDefaults,
    Role,
    check_quota,
    consume_quota,
    register_command,
    require_command,
)
from ..utils import (
    finish_processing_reply,
    get_image_urls,
    get_plaintext,
    get_reply,
    reply_to_event,
    send_processing_reply,
)
from .config import Config, ImageModelConfig
from .images import (
    MAX_REFERENCE_IMAGES,
    ImageAPIError,
    image_edit,
    image_generate,
    image_to_cq,
    images_to_cq,
)

__plugin_meta__ = PluginMetadata(
    name="llm",
    description="OpenAI 兼容文生图与图生图",
    usage=(
        "/draw [@模型] <描述> 文生图；直接引用消息与当前消息中的图片可作为参考图"
        "（引用优先，最多 16 张）"
    ),
    config=Config,
)

config: Config = get_yaml_plugin_config(Config, "llm")

register_command(
    "draw",
    default_role=Role.USER,
    quota=QuotaDefaults(daily=5, cooldown=60.0),
)

draw = on_command(
    "draw",
    priority=10,
    block=True,
    permission=require_command("draw"),
)


def _parse_draw_model_selector(text: str) -> tuple[str | None, str]:
    parts = text.split(maxsplit=1)
    if not parts or not parts[0].startswith("@"):
        return None, text
    prompt = parts[1] if len(parts) > 1 else ""
    return parts[0][1:], prompt


def _resolve_draw_profile(alias: str | None) -> ImageModelConfig:
    if alias is None:
        return config.image_models[config.image_default_model]
    try:
        return config.image_models[alias]
    except KeyError:
        shown_alias = alias or "(空)"
        available = " ".join(f"@{name}" for name in config.image_models)
        msg = f"未知生图模型: @{shown_alias}；可用模型: {available}"
        raise ValueError(msg) from None


async def _resolve_draw_request(
    bot: Bot,
    event: MessageEvent,
    arg: Message,
) -> tuple[str, list[str], ImageModelConfig]:
    """Resolve the selected profile, prompt, and direct-reply images."""
    alias, direct = _parse_draw_model_selector(get_plaintext(arg).strip())
    profile = _resolve_draw_profile(alias)
    msg_reply = await get_reply(bot=bot, msg=event.original_message)
    raw = msg_reply.get("raw_message") if msg_reply else None
    replied_message = Message(raw) if raw else None
    replied_prompt = get_plaintext(replied_message).strip() if replied_message else ""
    prompt = direct or replied_prompt
    image_urls = (
        get_image_urls(replied_message) if replied_message else []
    ) + get_image_urls(event.original_message)
    return prompt, image_urls, profile


async def _consume_draw_quota_or_finish(event: MessageEvent) -> None:
    quota = consume_quota(event, "draw")
    if not quota.allowed:
        await draw.finish(
            reply_to_event(event, quota.message or "额度不足"), at_sender=True
        )


async def _finish_draw_setup_error(event: MessageEvent, error: Exception) -> None:
    if isinstance(error, ValueError):
        await draw.finish(reply_to_event(event, str(error)), at_sender=True)
        return
    logger.exception("[LLM/draw] request setup failed: %s", error)
    await draw.finish(reply_to_event(event, "生图失败，请稍后重试"))


async def _finish_if_invalid_draw_request(
    event: MessageEvent,
    image_urls: list[str],
    profile: ImageModelConfig,
) -> bool:
    """Return True after finishing when capabilities or reference count fail.

    Runs before any quota check or upstream API call. In production
    ``draw.finish`` raises FinishedException and never returns.
    """
    if image_urls and "image_to_image" not in profile.capabilities:
        await draw.finish(
            reply_to_event(event, "当前生图模型不支持图生图"),
            at_sender=True,
        )
        return True
    if not image_urls and "text_to_image" not in profile.capabilities:
        await draw.finish(
            reply_to_event(event, "当前生图模型不支持文生图"),
            at_sender=True,
        )
        return True
    if len(image_urls) > MAX_REFERENCE_IMAGES:
        await draw.finish(
            reply_to_event(event, f"参考图最多支持 {MAX_REFERENCE_IMAGES} 张"),
            at_sender=True,
        )
        return True
    return False


@draw.handle()
async def handle_draw(
    bot: Bot,
    event: MessageEvent,
    arg: Message = CommandArg(),
) -> None:
    try:
        prompt, image_urls, profile = await _resolve_draw_request(bot, event, arg)
        if not prompt:
            await draw.finish(
                reply_to_event(
                    event,
                    "用法: /draw [@模型] <描述>；"
                    "可附图或直接引用含图片的消息作为参考图",
                ),
                at_sender=True,
            )
            return
        if await _finish_if_invalid_draw_request(event, image_urls, profile):
            return

        quota = check_quota(event, "draw")
        if not quota.allowed:
            await draw.finish(
                reply_to_event(event, quota.message or "额度不足"), at_sender=True
            )
            return
    except FinishedException:
        raise
    except Exception as e:  # noqa: BLE001
        await _finish_draw_setup_error(event, e)
        return

    await _consume_draw_quota_or_finish(event)
    processing = await send_processing_reply(draw, bot, event, "正在生成图片，请稍候…")
    try:
        if image_urls:
            logger.debug("[LLM/draw] edit prompt=%r images=%r", prompt, image_urls)
            b64_list = await image_edit(prompt, image_urls, profile=profile)
        else:
            logger.debug("[LLM/draw] generate prompt=%r", prompt)
            b64_list = await image_generate(prompt, profile=profile)

        await finish_processing_reply(
            draw,
            processing,
            event,
            images_to_cq(b64_list),
        )
    except FinishedException:
        raise
    except ImageAPIError as e:
        logger.warning("[LLM/draw] api error: %s", e.message)
        await finish_processing_reply(
            draw,
            processing,
            event,
            e.message,
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("[LLM/draw] unexpected error: %s", e)
        await finish_processing_reply(
            draw,
            processing,
            event,
            "生图失败，请稍后重试",
        )


__all__ = [
    "ImageAPIError",
    "image_edit",
    "image_generate",
    "image_to_cq",
    "images_to_cq",
]
