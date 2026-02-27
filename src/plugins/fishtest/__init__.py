from nonebot import get_plugin_config, logger, on_command, require
from nonebot.adapters.onebot.v11 import (
    Bot,
    MessageEvent,
)
from nonebot.adapters.onebot.v11.message import Message
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata

from .config import Config

require("app")
from ..app import app_getimage_cq

__plugin_meta__ = PluginMetadata(
    name="fishtest",
    description="",
    usage="",
    config=Config,
)

config: Config = get_plugin_config(Config)


# from nonebot.adapters.onebot.v11

echo = on_command("test", priority=10, block=True)


@echo.handle()
async def handle_function(bot: Bot, event: MessageEvent, args: Message = CommandArg()) -> None:
    d = await app_getimage_cq("/chat")
    await echo.finish(
        d,
        at_sender=True,
    )
    pass
