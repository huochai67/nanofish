import base64
import mimetypes
import zipfile
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Self, cast

import httpx
from nonebot import logger, on_command, require
from nonebot.adapters.onebot.v11 import Bot, Message, MessageEvent
from nonebot.exception import FinishedException
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata
from openai import AsyncOpenAI, OpenAIError

from src.plugin_config import get_yaml_plugin_config
from src.proxy import get_http_proxy_for_url

if TYPE_CHECKING:
    from openai.types.chat import ChatCompletionMessageParam

require("acl")
require("app")
require("utils")
from ..acl import check_quota, consume_quota, require_command
from ..app import app_chat_image_cq
from ..utils import (
    finish_processing_reply,
    get_image_urls,
    get_plaintext,
    get_reply,
    http_get,
    reply_to_event,
    send_processing_reply,
)
from .config import Config
from .images import (
    MAX_REFERENCE_IMAGES,
    ImageAPIError,
    image_edit,
    image_generate,
    image_to_cq,
    images_to_cq,
    openai_error_message,
)

__plugin_meta__ = PluginMetadata(
    name="llm",
    description="多模态 LLM 对话与 OpenAI 兼容生图/图生图",
    usage=(
        "/llm <内容>，可附带图片/文件，或回复消息；"
        "/draw <描述> 文生图；直接引用消息与当前消息中的图片可作为参考图"
        "（引用优先，最多 16 张）"
    ),
    config=Config,
)

config: Config = get_yaml_plugin_config(Config, "llm")

llm = on_command("llm", permission=require_command("llm"))
draw = on_command(
    "draw",
    priority=10,
    block=True,
    permission=require_command("draw"),
)


async def download_and_extract_zip(url: str) -> list[tuple[str, str]]:
    response = await http_get(url)

    zip_buffer = BytesIO(response.content)
    result: list[tuple[str, str]] = []
    with zipfile.ZipFile(zip_buffer, "r") as zip_file:
        for file_info in zip_file.filelist:
            if not file_info.is_dir():
                file_content = zip_file.read(file_info.filename)
                encoded_content = base64.b64encode(file_content).decode("utf-8")
                result.append((file_info.filename, encoded_content))
    return result


class CompletionMessage:
    def __init__(self) -> None:
        self.content: list = []

    def role(self, _role: Literal["user", "system", "developer", "assistant"]) -> Self:
        self.content.append(
            {
                "role": _role,
                "content": [],
            }
        )
        return self

    def check_input(self) -> None:
        if len(self.content) == 0:
            raise BufferError("请先设置角色")

    def text(self, _text: str) -> Self:
        self.check_input()
        self.content[-1]["content"].append(
            {
                "type": "text",
                "text": _text,
            }
        )
        return self

    def image(self, image_url: str) -> Self:
        self.check_input()
        self.content[-1]["content"].append(
            {
                "type": "image_url",
                "image_url": {"url": image_url},
            }
        )
        return self

    def images(self, image_urls: list[str]) -> Self:
        self.check_input()
        for image_url in image_urls:
            self.content[-1]["content"].append(
                {
                    "type": "image_url",
                    "image_url": {"url": image_url},
                }
            )
        return self

    async def zip(self, zip_url: str) -> Self:
        self.check_input()
        files = await download_and_extract_zip(zip_url)
        for filename, filedata in files:
            mime_type, _encoding = mimetypes.guess_type(filename)
            self.content[-1]["content"].append(
                {
                    "type": "file",
                    "file": {
                        "filename": filename,
                        "file_data": f"data:{mime_type};base64,{filedata}",
                    },
                }
            )
        return self

    def file(self, file_data: str, filename: str) -> Self:
        self.check_input()
        mime_type, _encoding = mimetypes.guess_type(filename)
        self.content[-1]["content"].append(
            {
                "type": "file",
                "file": {
                    "filename": filename,
                    "file_data": f"data:{mime_type};base64,{file_data}",
                },
            }
        )
        return self

    def file_url(self, file_url: str, filename: str) -> Self:
        self.check_input()
        mime_type, _encoding = mimetypes.guess_type(filename)
        self.content[-1]["content"].append(
            {
                "type": "file",
                "file": {
                    "filename": filename,
                    "format": mime_type,
                    "file_id": file_url,
                },
            }
        )
        return self

    def build(self) -> list[dict[str, Any]]:
        return self.content


async def openai(
    model: str,
    message: list[dict[str, Any]],
) -> dict[str, Any]:
    proxy = get_http_proxy_for_url(config.openai_api_base)
    http_client = httpx.AsyncClient(proxy=proxy) if proxy else None
    async with AsyncOpenAI(
        api_key=config.openai_api_key,
        base_url=config.openai_api_base,
        http_client=http_client,
    ) as client:
        response = await client.chat.completions.create(
            model=model,
            messages=cast("list[ChatCompletionMessageParam]", message),
        )
    retmsg = response.choices[0].message
    return CompletionMessage().role(retmsg.role).text(retmsg.content or "").build()[0]


async def get_reply_message(bot: Bot, message_id: int) -> Message:
    return Message((await bot.get_msg(message_id=message_id)).get("raw_message"))


async def parse_message(bot: Bot, message: Message) -> CompletionMessage:
    logger.debug(f"[LLM]parse_message: {message.to_rich_text()}")
    _input = CompletionMessage()

    text = ""
    filelist: list[str] = []
    imagenum = 1
    for seg in message:
        if seg.type == "reply":
            message_id = seg.data.get("id")
            if message_id is None:
                raise ValueError("回复消息缺少必要的字段")

            replied = await get_reply_message(bot, int(message_id))
            _input = await parse_message(bot=bot, message=replied)
        elif seg.type == "file":
            filename = seg.data.get("file")
            file_url = seg.data.get("url")

            if filename is None or file_url is None:
                raise ValueError("文件消息缺少必要的字段")

            extension = Path(filename).suffix
            file_url = f"{file_url}{filename}"
            if extension == ".zip":
                return await CompletionMessage().role("user").zip(zip_url=file_url)
            return (
                CompletionMessage()
                .role("user")
                .file_url(file_url=file_url, filename=filename)
            )

        elif seg.type == "text":
            text += str(seg)
        elif seg.type == "image":
            text += f"{{这条消息的第{imagenum}张图片}}"
            imagenum += 1
            filelist.append(seg.data["url"])

    return _input.role("user").text(text.removeprefix("/llm ")).images(filelist)


@llm.handle()
async def handle_function(bot: Bot, event: MessageEvent) -> None:
    try:
        quota = check_quota(event, "llm")
        if not quota.allowed:
            await llm.finish(
                reply_to_event(event, quota.message or "额度不足"), at_sender=True
            )
            return

        if event.raw_message == "":
            await llm.finish(reply_to_event(event, "请发送内容"), at_sender=True)
            return
    except FinishedException:
        raise
    except Exception as e:  # noqa: BLE001
        logger.exception(f"[LLM] request setup failed: {e}")
        await llm.finish(reply_to_event(event, "处理失败，请稍后重试"), at_sender=True)
        return

    processing = await send_processing_reply(llm, bot, event, "正在处理，请稍候…")
    try:
        llmmsg = (await parse_message(bot=bot, message=event.original_message)).build()
        logger.debug(f"[LLM]llmmsg: {llmmsg}")

        quota = consume_quota(event, "llm")
        if not quota.allowed:
            await llm.finish(
                reply_to_event(event, quota.message or "额度不足"), at_sender=True
            )
            return
        retmsg = await openai(model=config.model, message=llmmsg)
        logger.debug(f"[LLM]retmsg: {retmsg}")

        llmmsg.append(retmsg)
        await finish_processing_reply(
            llm,
            processing,
            event,
            await app_chat_image_cq({"messages": llmmsg}),
            at_sender=True,
        )
    except FinishedException:
        raise
    except ValueError as e:
        logger.warning(f"[LLM] input error: {e}")
        await finish_processing_reply(llm, processing, event, str(e), at_sender=True)
    except OpenAIError as e:
        logger.warning(f"[LLM] api error: {e}")
        await finish_processing_reply(
            llm,
            processing,
            event,
            openai_error_message(e),
            at_sender=True,
        )
    except Exception as e:  # noqa: BLE001
        logger.exception(f"[LLM] unexpected error: {e}")
        await finish_processing_reply(
            llm,
            processing,
            event,
            "处理失败，请稍后重试",
            at_sender=True,
        )


async def _resolve_draw_request(
    bot: Bot,
    event: MessageEvent,
    arg: Message,
) -> tuple[str, list[str]]:
    """Resolve prompt and direct-reply images, without traversing nested replies."""
    direct = get_plaintext(arg).strip()
    msg_reply = await get_reply(bot=bot, msg=event.original_message)
    raw = msg_reply.get("raw_message") if msg_reply else None
    replied_message = Message(raw) if raw else None
    replied_prompt = get_plaintext(replied_message).strip() if replied_message else ""
    prompt = direct or replied_prompt
    image_urls = (
        get_image_urls(replied_message) if replied_message else []
    ) + get_image_urls(event.original_message)
    return prompt, image_urls


async def _consume_draw_quota_or_finish(event: MessageEvent) -> None:
    quota = consume_quota(event, "draw")
    if not quota.allowed:
        await draw.finish(
            reply_to_event(event, quota.message or "额度不足"), at_sender=True
        )


@draw.handle()
async def handle_draw(
    bot: Bot,
    event: MessageEvent,
    arg: Message = CommandArg(),
) -> None:
    try:
        quota = check_quota(event, "draw")
        if not quota.allowed:
            await draw.finish(
                reply_to_event(event, quota.message or "额度不足"), at_sender=True
            )
            return

        prompt, image_urls = await _resolve_draw_request(bot, event, arg)
        if not prompt:
            await draw.finish(
                reply_to_event(
                    event, "用法: /draw <描述>；可附图或直接引用含图片的消息作为参考图"
                ),
                at_sender=True,
            )
            return
        if len(image_urls) > MAX_REFERENCE_IMAGES:
            await draw.finish(
                reply_to_event(event, f"参考图最多支持 {MAX_REFERENCE_IMAGES} 张"),
                at_sender=True,
            )
            return
    except FinishedException:
        raise
    except Exception as e:  # noqa: BLE001
        logger.exception("[LLM/draw] request setup failed: %s", e)
        await draw.finish(reply_to_event(event, "生图失败，请稍后重试"))
        return

    await _consume_draw_quota_or_finish(event)
    processing = await send_processing_reply(draw, bot, event, "正在生成图片，请稍候…")
    try:
        if image_urls:
            logger.debug("[LLM/draw] edit prompt=%r images=%r", prompt, image_urls)
            b64_list = await image_edit(prompt, image_urls)
        else:
            logger.debug("[LLM/draw] generate prompt=%r", prompt)
            b64_list = await image_generate(prompt)

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
