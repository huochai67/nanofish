import datetime
import random

from nonebot import get_plugin_config, on_command
from nonebot.adapters.onebot.v11 import MessageEvent
from nonebot.plugin import PluginMetadata

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="jrrp",
    description="",
    usage="",
    config=Config,
)

config = get_plugin_config(Config)


jrrp = on_command("jrrp")


@jrrp.handle()
async def handle_function(event: MessageEvent) -> None:
    user_id = event.sender.user_id or 0
    random.seed(datetime.datetime.now(tz=datetime.timezone.utc).day + user_id)
    luck = random.randint(0, 100)
    await jrrp.finish(f"{event.sender.nickname} 您今天将收到我 {luck} 的真诚祝福")
