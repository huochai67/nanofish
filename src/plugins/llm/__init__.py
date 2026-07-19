import base64
import mimetypes
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Literal, Self

import litellm
from nonebot import get_plugin_config, logger, on_command, require
from nonebot.adapters.onebot.v11 import Bot, Message, MessageEvent
from nonebot.exception import FinishedException
from nonebot.plugin import PluginMetadata

require("acl")
require("app")
require("utils")
from ..acl import check_quota, consume_quota, require_command
from ..app import app_chat_image_cq
from ..utils import http_get
from .config import Config

__plugin_meta__ = PluginMetadata(
    name="llm",
    description="多模态 LLM 对话，结果以截图回传",
    usage="/llm <内容>，可附带图片/文件，或回复消息",
    config=Config,
)

config: Config = get_plugin_config(Config)

llm = on_command("llm", permission=require_command("llm"))


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

    def role(self, _role: Literal["user", "system", "developer"]) -> Self:
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

    def build(self) -> list[litellm.Message]:
        return self.content


async def openai(model: str, message: list[litellm.Message]) -> litellm.Message:
    response = await litellm.acompletion(
        api_key=config.openai_api_key,
        api_base=config.openai_api_base,
        model=model,
        messages=message,
    )
    retmsg = response.choices[0].message
    return CompletionMessage().role(retmsg.role).text(retmsg.content).build()[0]


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
            await llm.finish(quota.message or "额度不足", at_sender=True)
            return

        if event.raw_message == "":
            await llm.finish("请发送内容", at_sender=True)
            return

        llmmsg = (await parse_message(bot=bot, message=event.original_message)).build()
        logger.debug(f"[LLM]llmmsg: {llmmsg}")

        consume_quota(event, "llm")
        retmsg = await openai(model=f"openai/{config.model}", message=llmmsg)
        logger.debug(f"[LLM]retmsg: {retmsg}")

        llmmsg.append(retmsg)
        await llm.finish(
            await app_chat_image_cq({"messages": llmmsg}),
            at_sender=True,
        )
    except FinishedException:
        raise
    except ValueError as e:
        logger.warning(f"[LLM] input error: {e}")
        await llm.finish(str(e), at_sender=True)
    except Exception as e:  # noqa: BLE001
        logger.exception(f"[LLM] unexpected error: {e}")
        await llm.finish("处理失败，请稍后重试", at_sender=True)
