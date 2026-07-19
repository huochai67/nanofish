import asyncio
import atexit
import base64
import json
import threading
from typing import Any, ClassVar, Self

from nonebot import get_driver, get_plugin_config, logger
from nonebot.adapters.onebot.v11.message import Message
from nonebot.plugin import PluginMetadata
from playwright.async_api import Browser, BrowserContext, Playwright, async_playwright

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="app",
    description="前端页面截图服务",
    usage="",
    config=Config,
)

config: Config = get_plugin_config(Config)


class Client:
    _instance: ClassVar[Self | None] = None
    _lock: ClassVar[threading.Lock] = threading.Lock()

    def __new__(cls, *_args: Any, **_kwargs: Any) -> Self:
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_initialized") and self._initialized:
            return

        self._initialized = True
        self._async_lock = asyncio.Lock()
        self.playwright: Playwright | None = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None

    async def get_context(self) -> BrowserContext:
        async with self._async_lock:
            if self.browser and self.browser.is_connected() and self.context:
                return self.context

            await self._close_unlocked()
            playwright = await async_playwright().start()
            browser = await playwright.chromium.launch()
            context = await browser.new_context(
                viewport={
                    "width": config.app_viewport_width,
                    "height": config.app_viewport_height,
                },
            )
            self.playwright = playwright
            self.browser = browser
            self.context = context
            logger.info("Playwright browser launched")
            return context

    async def shoot(self, url: str) -> str:
        context = await self.get_context()
        page = await context.new_page()
        try:
            await page.goto(
                url,
                wait_until="networkidle",
                timeout=config.app_page_timeout_ms,
            )
            image_bytes = await page.screenshot(type="jpeg", full_page=True)
            return base64.b64encode(image_bytes).decode("utf-8")
        finally:
            await page.close()

    async def shoot_chat(self, chat_data: dict[str, Any]) -> str:
        context = await self.get_context()
        page = await context.new_page()
        try:
            # inject before any page JS so React reads data on first mount
            await page.add_init_script(
                f"window.__CHAT_DATA__ = {json.dumps(chat_data)};"
            )
            await page.goto(
                f"{config.app_api_base}/chat",
                wait_until="domcontentloaded",
                timeout=config.app_page_timeout_ms,
            )
            await page.wait_for_selector(
                "[data-ready='true']",
                timeout=config.app_page_timeout_ms,
            )
            await page.evaluate("() => document.fonts.ready")
            image_bytes = await page.screenshot(type="jpeg", full_page=True)
            return base64.b64encode(image_bytes).decode("utf-8")
        finally:
            await page.close()

    async def close(self) -> None:
        async with self._async_lock:
            await self._close_unlocked()

    async def _close_unlocked(self) -> None:
        if self.context:
            try:
                await self.context.close()
            except Exception as e:  # noqa: BLE001
                logger.warning(f"关闭 browser context 失败: {e}")
            self.context = None

        if self.browser:
            try:
                await self.browser.close()
            except Exception as e:  # noqa: BLE001
                logger.warning(f"关闭 browser 失败: {e}")
            self.browser = None

        if self.playwright:
            try:
                await self.playwright.stop()
            except Exception as e:  # noqa: BLE001
                logger.warning(f"停止 playwright 失败: {e}")
            self.playwright = None


client: Client = Client()
_atexit_tasks: list[asyncio.Task[None]] = []


def _sync_close_client() -> None:
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            _atexit_tasks.append(loop.create_task(client.close()))
        else:
            loop.run_until_complete(client.close())
    except RuntimeError:
        try:
            asyncio.run(client.close())
        except Exception as e:  # noqa: BLE001
            logger.warning(f"退出时关闭 playwright 失败: {e}")


atexit.register(_sync_close_client)

driver = get_driver()


@driver.on_startup
async def _warm_browser() -> None:
    try:
        await client.get_context()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"预热 Playwright 失败: {e}")


@driver.on_shutdown
async def _shutdown_browser() -> None:
    await client.close()


async def app_getimage_b64(api: str) -> str:
    return await client.shoot(f"{config.app_api_base}{api}")


async def app_getimage_uri(api: str) -> str:
    base64img = await app_getimage_b64(api=api)
    return f"data:image/jpeg;base64,{base64img}"


async def app_getimage_cq(api: str) -> Message:
    base64img = await app_getimage_b64(api=api)
    return Message(f"[CQ:image,file=base64://{base64img}]")


async def app_chat_image_b64(chat_data: dict[str, Any]) -> str:
    return await client.shoot_chat(chat_data)


async def app_chat_image_cq(chat_data: dict[str, Any]) -> Message:
    base64img = await app_chat_image_b64(chat_data)
    return Message(f"[CQ:image,file=base64://{base64img}]")
