import datetime
import random

from nonebot import get_plugin_config, on_command, require
from nonebot.adapters.onebot.v11 import MessageEvent
from nonebot.plugin import PluginMetadata

from .config import Config

require("acl")
from ..acl import require_command

__plugin_meta__ = PluginMetadata(
    name="jrrp",
    description="今日人品",
    usage="/jrrp",
    config=Config,
)

config = get_plugin_config(Config)

jrrp = on_command("jrrp", permission=require_command("jrrp"))


@jrrp.handle()
async def handle_function(event: MessageEvent) -> None:
    user_id = event.sender.user_id or 0
    today = datetime.datetime.now(tz=datetime.UTC).date().toordinal()
    random.seed(today + user_id)
    luck = random.randint(0, 100)
    await jrrp.finish(f"{event.sender.nickname} 您今天将收到我 {luck} 的真诚祝福")
