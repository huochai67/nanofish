import os
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
from nonebot import get_plugin_config, logger

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
    return request.content if hasattr(request, "content") else request.body


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

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


def _config() -> Config:
    return get_plugin_config(Config)


def get_http_proxy() -> str | None:
    """Return the configured proxy, preferring the documented ``PROXY`` setting."""
    cfg = _config()
    return cfg.proxy or cfg.http_proxy


def configure_proxy_environment() -> None:
    """Expose the configured proxy to SDKs that create their own HTTP clients."""
    proxy = get_http_proxy()
    if not proxy:
        return
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        os.environ[name] = proxy


def http_client(
    *,
    proxy: str | None = None,
    timeout: float | None = None,
    **kwargs: Any,
) -> httpx.AsyncClient:
    """创建带全局默认 timeout / proxy 的 AsyncClient。

    ``proxy`` 为 None 时回退到全局 ``PROXY`` / ``HTTP_PROXY`` 配置；
    ``timeout`` 为 None 时回退到 ``http_timeout`` 配置。
    """
    cfg = _config()
    return httpx.AsyncClient(
        proxy=get_http_proxy() if proxy is None else proxy,
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
        async with http_client(proxy=proxy, timeout=timeout) as client:
            response = await client.post(url, **kwargs)
            if _config().http_trace:
                log_http_trace("httpx", response)
            response.raise_for_status()
            return response
    except httpx.HTTPError as e:
        raise _map_httpx_error(e) from e
