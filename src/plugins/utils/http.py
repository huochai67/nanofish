from typing import Any

import httpx
from nonebot import get_plugin_config

from .config import Config


class HttpRequestError(Exception):
    """HTTP 请求失败，message 可直接展示给用户。"""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


def _config() -> Config:
    return get_plugin_config(Config)


def http_client(
    *,
    proxy: str | None = None,
    timeout: float | None = None,
    **kwargs: Any,
) -> httpx.AsyncClient:
    """创建带全局默认 timeout / proxy 的 AsyncClient。

    ``proxy`` 为 None 时回退到 ``http_proxy`` 配置；
    ``timeout`` 为 None 时回退到 ``http_timeout`` 配置。
    """
    cfg = _config()
    return httpx.AsyncClient(
        proxy=cfg.http_proxy if proxy is None else proxy,
        timeout=cfg.http_timeout if timeout is None else timeout,
        **kwargs,
    )


def _map_httpx_error(exc: httpx.HTTPError) -> HttpRequestError:
    if isinstance(exc, httpx.TimeoutException):
        return HttpRequestError("请求超时，请稍后重试")
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        reason = exc.response.reason_phrase
        return HttpRequestError(f"请求失败: HTTP {status} {reason}".rstrip())
    return HttpRequestError(f"请求失败: {type(exc).__name__}")


async def http_get(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    proxy: str | None = None,
    timeout: float | None = None,  # noqa: ASYNC109  # httpx 超时，非 asyncio.timeout
    **kwargs: Any,
) -> httpx.Response:
    try:
        async with http_client(proxy=proxy, timeout=timeout, **kwargs) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response
    except httpx.HTTPError as e:
        raise _map_httpx_error(e) from e


async def http_post(
    url: str,
    *,
    proxy: str | None = None,
    timeout: float | None = None,  # noqa: ASYNC109  # httpx 超时，非 asyncio.timeout
    **kwargs: Any,
) -> httpx.Response:
    try:
        async with http_client(proxy=proxy, timeout=timeout) as client:
            response = await client.post(url, **kwargs)
            response.raise_for_status()
            return response
    except httpx.HTTPError as e:
        raise _map_httpx_error(e) from e
