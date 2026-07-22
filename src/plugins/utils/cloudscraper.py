"""Async wrapper around cloudscraper for plugins that need a browser-like session."""

from __future__ import annotations

import asyncio
import threading
from typing import Any

import cloudscraper
import requests
from nonebot import get_plugin_config

from .config import Config
from .http import HttpRequestError, get_http_proxy, log_http_trace


class CloudScraperClient:
    """Keep one cloudscraper session while exposing non-blocking request methods."""

    def __init__(
        self,
        *,
        config: Config | None = None,
        proxy: str | None = None,
        headers: dict[str, str] | None = None,
        cookies: dict[str, str] | None = None,
        debug_name: str | None = None,
        trace: bool | None = None,
    ) -> None:
        if cookies and any(key.lower() == "cf_clearance" for key in cookies):
            raise ValueError("cf_clearance must not be configured")

        resolved_config = config or get_plugin_config(Config)
        self._proxy = get_http_proxy() if proxy is None else proxy
        self._timeout = resolved_config.http_timeout
        self._debug_name = debug_name
        self._trace = resolved_config.http_trace if trace is None else trace
        self._lock = threading.Lock()
        self._scraper: Any = cloudscraper.create_scraper(  # type: ignore[attr-defined]
            interpreter="js2py",
            delay=5,
            debug=False,
        )
        if headers:
            self._scraper.headers.update(headers)
        if cookies:
            self._scraper.cookies.update(cookies)

    def _request(
        self,
        method: str,
        url: str,
        *,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> requests.Response:
        proxies = {"http": self._proxy, "https": self._proxy} if self._proxy else None
        try:
            with self._lock:
                response = self._scraper.request(
                    method,
                    url,
                    timeout=self._timeout if timeout is None else timeout,
                    proxies=proxies,
                    **kwargs,
                )
            if self._trace:
                log_http_trace(self._debug_name or "cloudscraper", response)
            response.raise_for_status()
        except requests.Timeout as e:
            raise HttpRequestError("请求超时，请稍后重试") from e
        except requests.HTTPError as e:
            response = e.response
            status = response.status_code if response is not None else "unknown"
            reason = response.reason if response is not None else ""
            raise HttpRequestError(f"请求失败: HTTP {status} {reason}".rstrip()) from e
        except requests.RequestException as e:
            raise HttpRequestError(f"请求失败: {type(e).__name__}") from e
        else:
            return response

    async def request(
        self,
        method: str,
        url: str,
        *,
        timeout: float | None = None,  # noqa: ASYNC109  # requests timeout
        **kwargs: Any,
    ) -> requests.Response:
        return await asyncio.to_thread(
            self._request,
            method,
            url,
            timeout=timeout,
            **kwargs,
        )

    async def get(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,  # noqa: ASYNC109  # requests timeout
        **kwargs: Any,
    ) -> requests.Response:
        return await self.request(
            "GET",
            url,
            params=params,
            timeout=timeout,
            **kwargs,
        )

    async def post(
        self,
        url: str,
        *,
        timeout: float | None = None,  # noqa: ASYNC109  # requests timeout
        **kwargs: Any,
    ) -> requests.Response:
        return await self.request("POST", url, timeout=timeout, **kwargs)
