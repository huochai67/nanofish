from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
from nonebot import get_plugin_config, logger

from src.proxy import (
    configure_proxy_environment as _configure_proxy_environment,
)
from src.proxy import (
    get_http_proxy_for_url,
    get_http_proxy_from_env,
)

from .config import Config

_SENSITIVE_HEADERS = {"authorization", "cookie", "proxy-authorization", "x-api-key"}
_SENSITIVE_QUERY_PARAMS = {"api_key", "key", "token"}


def _redact_headers(headers: Any) -> dict[str, str]:
    return {
        str(key): "<redacted>" if str(key).lower() in _SENSITIVE_HEADERS else str(value)
        for key, value in headers.items()
    }


def _redact_url(url: str) -> str:
    parts = urlsplit(url)
    query = urlencode(
        [
            (key, "<redacted>" if key.lower() in _SENSITIVE_QUERY_PARAMS else value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
        ]
    )
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))


def _body_summary(body: Any) -> str:
    if body is None:
        return "<empty>"
    if isinstance(body, bytes):
        return f"<{len(body)} bytes>"
    return f"<{len(str(body))} characters>"


def _response_body(response: Any) -> str:
    content_type = response.headers.get("content-type", "").lower()
    if not (
        content_type.startswith("text/")
        or "json" in content_type
        or "xml" in content_type
        or "html" in content_type
    ):
        return f"<{len(response.content)} bytes; omitted>"
    return response.text[:2000]


def _request_body(request: Any) -> Any:
    try:
        return request.content
    except AttributeError:
        return request.body
    except RuntimeError:
        return "<streaming body>"


def _response_reason(response: Any) -> str:
    if hasattr(response, "reason_phrase"):
        return response.reason_phrase
    return response.reason


def log_http_trace(name: str, response: Any) -> None:
    request = response.request
    logger.debug(
        "[{}] HTTP trace request: method={} url={} headers={!r} body={}",
        name,
        request.method,
        _redact_url(str(request.url)),
        _redact_headers(request.headers),
        _body_summary(_request_body(request)),
    )
    logger.debug(
        "[{}] HTTP trace response: status={} reason={} headers={!r} body={!r}",
        name,
        response.status_code,
        _response_reason(response),
        _redact_headers(response.headers),
        _response_body(response),
    )


class HttpRequestError(Exception):
    """HTTP 请求失败，message 可直接展示给用户。"""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        self.message = message
        self.status = status
        super().__init__(message)


def _config() -> Config:
    return get_plugin_config(Config)


def get_http_proxy() -> str | None:
    """Return the shared proxy configured through any supported environment name."""
    return get_http_proxy_from_env()


def configure_proxy_environment() -> None:
    """Expose the configured proxy to SDKs that create their own HTTP clients."""
    _configure_proxy_environment()


def http_client(
    *,
    url: str | None = None,
    proxy: str | None = None,
    timeout: float | None = None,
    **kwargs: Any,
) -> httpx.AsyncClient:
    """创建带全局默认 timeout / proxy 的 AsyncClient。

    ``proxy`` 为 None 时回退到全局 ``PROXY`` / ``HTTP_PROXY`` 配置；传入
    ``url`` 时会遵循 ``NO_PROXY``。
    ``timeout`` 为 None 时回退到 ``http_timeout`` 配置。
    """
    cfg = _config()
    return httpx.AsyncClient(
        proxy=(
            get_http_proxy_for_url(url, proxy)
            if url
            else get_http_proxy()
            if proxy is None
            else proxy
        ),
        timeout=cfg.http_timeout if timeout is None else timeout,
        **kwargs,
    )


def request_error_message(
    *,
    status: int | None = None,
    timeout: bool = False,
) -> str:
    """Return the standard user-facing message for an external HTTP failure."""
    if timeout:
        return "请求超时，请稍后重试"
    if status is not None:
        return f"请求失败（HTTP {status}），请稍后重试"
    return "网络请求失败，请稍后重试"


def http_error_message(exc: httpx.HTTPError) -> str:
    """Map an httpx exception to the standard user-facing error message."""
    if isinstance(exc, httpx.TimeoutException):
        return request_error_message(timeout=True)
    if isinstance(exc, httpx.HTTPStatusError):
        return request_error_message(status=exc.response.status_code)
    return request_error_message()


def _map_httpx_error(exc: httpx.HTTPError) -> HttpRequestError:
    status = (
        exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
    )
    return HttpRequestError(http_error_message(exc), status=status)


async def http_get(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    proxy: str | None = None,
    timeout: float | None = None,  # noqa: ASYNC109  # httpx 超时，非 asyncio.timeout
    **kwargs: Any,
) -> httpx.Response:
    try:
        async with http_client(
            url=url, proxy=proxy, timeout=timeout, **kwargs
        ) as client:
            response = await client.get(url, params=params)
            if _config().http_trace:
                log_http_trace("httpx", response)
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
        async with http_client(url=url, proxy=proxy, timeout=timeout) as client:
            response = await client.post(url, **kwargs)
            if _config().http_trace:
                log_http_trace("httpx", response)
            response.raise_for_status()
            return response
    except httpx.HTTPError as e:
        raise _map_httpx_error(e) from e
