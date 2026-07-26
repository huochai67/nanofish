from pathlib import Path

import nonebot
from nonebot.adapters.onebot.v11 import Adapter as OneBotV11Adapter

from src import plugin_config

plugin_config._CONFIG_PATH = Path(__file__).parents[1] / "config.example.yaml"
nonebot.init(app_api_base="http://127.0.0.1:3000")
nonebot.get_driver().register_adapter(OneBotV11Adapter)
nonebot.load_plugins("src/plugins")
