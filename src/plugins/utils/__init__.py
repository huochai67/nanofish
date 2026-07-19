from nonebot import get_plugin_config
from nonebot.adapters.onebot.v11 import Bot
from nonebot.adapters.onebot.v11.message import Message
from nonebot.plugin import PluginMetadata

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="utils",
    description="共享消息解析工具",
    usage="",
    config=Config,
)

_config = get_plugin_config(Config)


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
    for segment in msg:
        if segment.type == "image":
            return segment.data.get("url")
    return None


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
