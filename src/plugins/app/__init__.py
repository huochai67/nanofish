import base64
import threading

from nonebot import get_plugin_config
from nonebot.adapters.onebot.v11.message import Message
from nonebot.plugin import PluginMetadata
from playwright.async_api import Browser, async_playwright

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="app",
    description="",
    usage="",
    config=Config,
)

config: Config = get_plugin_config(Config)


class Client:
    _instance = None
    _lock = threading.Lock()  # 用于确保线程安全的单例创建

    def __new__(cls, *args, **kwargs):
        """
        重写 __new__ 方法来实现单例模式。
        """
        if not cls._instance:
            with cls._lock:
                # 再次检查，防止多线程环境下重复创建实例
                if not cls._instance:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        # 防止重复初始化
        if hasattr(self, "_initialized") and self._initialized:
            return

        self._initialized = True
        self.browser = None
        self.context = None

    async def get_browser(self) -> Browser:
        if self.browser:
            return self.browser

        self.context = await async_playwright().start()
        self.browser = await self.context.chromium.launch()
        return self.browser

    async def shoot(self, url: str) -> str:
        browser = await self.get_browser()
        page = await browser.new_page()
        await page.set_viewport_size({"width": 1366, "height": 768})
        await page.goto(url)
        image_bytes = await page.screenshot(type="jpeg", full_page=True)
        base64_string = base64.b64encode(image_bytes).decode("utf-8")
        await page.close()
        return base64_string


client: Client = Client()


async def app_getimage_b64(api: str) -> str:
    return await client.shoot(f"{config.app_api_base}{api}")


async def app_getimage_uri(api: str) -> str:
    base64img = await app_getimage_b64(api=api)
    return f"data:image/jpeg;base64,{base64img}"


async def app_getimage_cq(api: str) -> Message:
    base64img = await app_getimage_b64(api=api)
    return Message(f"[CQ:image,file=base64://{base64img}]")
