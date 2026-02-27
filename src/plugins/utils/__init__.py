from nonebot import get_plugin_config
from nonebot.adapters.onebot.v11 import Bot
from nonebot.adapters.onebot.v11.message import Message
from nonebot.plugin import PluginMetadata

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="utils",
    description="",
    usage="",
    config=Config,
)

_config = get_plugin_config(Config)


def get_globalconfig() -> Config:
    return _config


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


def get_plaintext(msg: Message) -> str:
    ret = ""
    for segment in msg:
        if segment.type == "text":
            ret += str(segment.data.get("text"))
    return ret


async def get_reply(bot: Bot, msg: Message) -> None | dict:
    message_id = get_replyid(msg)
    if message_id:
        return await bot.get_msg(message_id=message_id)
    return None
