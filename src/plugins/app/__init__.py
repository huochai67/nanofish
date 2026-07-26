import asyncio
import atexit
import base64
import json
import threading
import uuid
from typing import Any, ClassVar, Literal, Self

from nonebot import get_driver, get_plugin_config, logger
from nonebot.adapters.onebot.v11.message import Message
from nonebot.plugin import PluginMetadata
from playwright.async_api import Browser, BrowserContext, Playwright, async_playwright

from src.proxy import get_http_proxy_from_env, get_no_proxy_from_env

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="app",
    description="前端页面截图服务",
    usage="",
    config=Config,
)

config: Config = get_plugin_config(Config)
_MAX_FRONTEND_DIAGNOSTICS = 20


def _payload_summary(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _payload_summary(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_payload_summary(item) for item in value]
    if isinstance(value, str) and value.startswith("data:image/"):
        return f"{value.split(',', maxsplit=1)[0]},... ({len(value)} chars)"
    return value


async def _dump_frontend_payload(
    path: str,
    global_name: str,
    data: dict[str, Any],
) -> None:
    payload = {"path": path, "global": global_name, "data": data}
    directory = config.app_debug_payload_dir
    await asyncio.to_thread(directory.mkdir, parents=True, exist_ok=True)
    output = directory / f"frontend-payload-{uuid.uuid4().hex}.json"
    await asyncio.to_thread(
        output.write_text,
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info(f"前端截图调试参数已保存: {output}")
    logger.info(
        "前端截图调试参数摘要:\n"
        f"{json.dumps(_payload_summary(payload), ensure_ascii=False, indent=2)}"
    )


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
            proxy = get_http_proxy_from_env()
            browser = await playwright.chromium.launch(
                proxy={"server": proxy, "bypass": get_no_proxy_from_env() or ""}
                if proxy
                else None,
            )
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

    async def shoot_with_data(
        self,
        path: str,
        global_name: str,
        data: dict[str, Any],
    ) -> str:
        """Open a frontend page with window.<global_name> injected, then screenshot."""
        image_bytes = await self._shoot_with_data(
            path,
            global_name,
            data,
            image_type="jpeg",
        )
        return base64.b64encode(image_bytes).decode("utf-8")

    async def _shoot_with_data(
        self,
        path: str,
        global_name: str,
        data: dict[str, Any],
        *,
        image_type: Literal["jpeg", "png"],
        viewport_width: int | None = None,
        target_selector: str | None = None,
    ) -> bytes:
        context = await self.get_context()
        page = await context.new_page()
        diagnostics: list[str] = []
        try:
            if config.app_debug_frontend_payload:
                await _dump_frontend_payload(path, global_name, data)
            if viewport_width is not None:
                await page.set_viewport_size(
                    {
                        "width": viewport_width,
                        "height": config.app_viewport_height,
                    }
                )

            def add_diagnostic(message: str) -> None:
                if len(diagnostics) < _MAX_FRONTEND_DIAGNOSTICS:
                    diagnostics.append(message[:1_000])

            page.on(
                "console",
                lambda message: (
                    add_diagnostic(f"console {message.type}: {message.text}")
                    if message.type in {"error", "warning"}
                    else None
                ),
            )
            page.on("pageerror", lambda error: add_diagnostic(f"pageerror: {error}"))
            page.on(
                "requestfailed",
                lambda request: add_diagnostic(
                    f"requestfailed: {request.url.split('?', maxsplit=1)[0]} "
                    f"({request.failure})"
                ),
            )
            # inject before any page JS so React reads data on first mount
            await page.add_init_script(
                f"window.{global_name} = {json.dumps(data, ensure_ascii=False)};"
            )
            await page.goto(
                f"{config.app_api_base}{path}",
                wait_until="domcontentloaded",
                timeout=config.app_page_timeout_ms,
            )
            readiness = page.locator("[data-ready='ready'], [data-ready='timeout']")
            await readiness.wait_for(
                state="visible",
                timeout=config.app_page_timeout_ms,
            )
            if await readiness.get_attribute("data-ready") == "timeout":
                raise RuntimeError(  # noqa: TRY301
                    "截图页面的远程媒体在 10 秒内未完成加载"
                )
            await page.evaluate("() => document.fonts.ready")
            # Hide Next.js dev tools / portals that may still paint in screenshots
            await page.add_style_tag(
                content=(
                    "nextjs-portal,"
                    "[data-nextjs-toast],"
                    "[data-nextjs-dialog-overlay],"
                    "[data-next-badge-root],"
                    "#__next-build-watcher{"
                    "display:none!important;visibility:hidden!important;"
                    "}"
                )
            )
            if target_selector is not None:
                target = page.locator(target_selector)
                await target.wait_for(
                    state="visible", timeout=config.app_page_timeout_ms
                )
                return await target.screenshot(type=image_type)
            return await page.screenshot(type=image_type, full_page=True)
        except Exception:
            try:
                states = await page.locator("[data-ready]").evaluate_all(
                    "elements => elements.map(element => element.dataset.ready)"
                )
            except Exception as diagnostics_error:  # noqa: BLE001
                states = [f"unavailable: {diagnostics_error}"]
            logger.error(
                "frontend screenshot failed path={} readiness={} diagnostics={}",
                path,
                states,
                diagnostics,
            )
            raise
        finally:
            await page.close()

    async def shoot_chat(self, chat_data: dict[str, Any]) -> str:
        return await self.shoot_with_data("/chat", "__CHAT_DATA__", chat_data)

    async def shoot_eh(self, eh_data: dict[str, Any]) -> str:
        return await self.shoot_with_data("/eh", "__EH_DATA__", eh_data)

    async def shoot_imgsearch(self, imgsearch_data: dict[str, Any]) -> str:
        return await self.shoot_with_data(
            "/imgsearch", "__IMGSEARCH_DATA__", imgsearch_data
        )

    async def shoot_parser(self, parser_data: dict[str, Any]) -> bytes:
        return await self._shoot_with_data(
            "/parser",
            "__PARSER_DATA__",
            parser_data,
            image_type="png",
            viewport_width=720,
            target_selector="[data-parser-card]",
        )

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


async def app_eh_image_b64(eh_data: dict[str, Any]) -> str:
    return await client.shoot_eh(eh_data)


async def app_eh_image_cq(eh_data: dict[str, Any]) -> Message:
    base64img = await app_eh_image_b64(eh_data)
    return Message(f"[CQ:image,file=base64://{base64img}]")


async def app_imgsearch_image_b64(imgsearch_data: dict[str, Any]) -> str:
    return await client.shoot_imgsearch(imgsearch_data)


async def app_imgsearch_image_cq(imgsearch_data: dict[str, Any]) -> Message:
    base64img = await app_imgsearch_image_b64(imgsearch_data)
    return Message(f"[CQ:image,file=base64://{base64img}]")


async def app_parser_image(parser_data: dict[str, Any]) -> bytes:
    return await client.shoot_parser(parser_data)
