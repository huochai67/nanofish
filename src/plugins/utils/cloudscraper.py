"""HTTP client that obtains Cloudflare cookies from FlareSolverr."""

from __future__ import annotations

from typing import Any

import httpx
from nonebot import get_plugin_config, logger

from .config import Config
from .http import HttpRequestError, get_http_proxy, log_http_trace


class CloudScraperClient:
    """Keep FlareSolverr-derived cookies while exposing the legacy request API."""

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
        self._flaresolverr_url = resolved_config.flaresolverr_url
        self._debug_name = debug_name
        self._trace = resolved_config.http_trace if trace is None else trace
        self._headers = headers or {}
        self._cookies = cookies.copy() if cookies else {}
        self._user_agent: str | None = None
        self._solver_response: httpx.Response | None = None

    @property
    def user_agent(self) -> str | None:
        return self._user_agent

    def _solver_cookies(self) -> list[dict[str, str]]:
        return [{"name": name, "value": value} for name, value in self._cookies.items()]

    async def _solve(  # noqa: C901, PLR0912  # HTTP client response parsing
        self,
        url: str,
        timeout: float,  # noqa: ASYNC109  # HTTP client timeout
    ) -> None:
        self._solver_response = None
        payload: dict[str, Any] = {
            "cmd": "request.get",
            "url": url,
            "maxTimeout": round(timeout * 1000),
        }
        if self._proxy:
            payload["proxy"] = {"url": self._proxy}
        if self._cookies:
            payload["cookies"] = self._solver_cookies()

        try:
            # The controller is on the Compose network, never route it through PROXY.
            async with httpx.AsyncClient(
                timeout=timeout + 5,
                trust_env=False,
            ) as client:
                response = await client.post(self._flaresolverr_url, json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.TimeoutException as e:
            raise HttpRequestError("请求超时，请稍后重试") from e
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            reason = e.response.reason_phrase
            raise HttpRequestError(
                f"FlareSolverr 请求失败: HTTP {status} {reason}".rstrip()
            ) from e
        except (httpx.HTTPError, ValueError) as e:
            raise HttpRequestError(f"FlareSolverr 请求失败: {type(e).__name__}") from e

        if not isinstance(data, dict) or data.get("status") != "ok":
            message = data.get("message") if isinstance(data, dict) else "响应格式异常"
            raise HttpRequestError(f"FlareSolverr 请求失败: {message or '未知错误'}")
        solution = data.get("solution")
        if not isinstance(solution, dict):
            raise HttpRequestError("FlareSolverr 请求失败: 响应格式异常")

        status = solution.get("status")
        body = solution.get("response")
        raw_headers = solution.get("headers")
        if isinstance(status, int) and isinstance(body, str):
            solution_headers = (
                {str(key): str(value) for key, value in raw_headers.items()}
                if isinstance(raw_headers, dict)
                else {}
            )
            self._solver_response = httpx.Response(
                status,
                headers=solution_headers,
                content=body.encode(),
                request=httpx.Request("GET", url),
            )

        user_agent = solution.get("userAgent")
        if isinstance(user_agent, str) and user_agent:
            self._user_agent = user_agent
        raw_cookies = solution.get("cookies")
        received_cookies = 0
        if isinstance(raw_cookies, list):
            for cookie in raw_cookies:
                if not isinstance(cookie, dict):
                    continue
                name = cookie.get("name")
                value = cookie.get("value")
                if isinstance(name, str) and isinstance(value, str):
                    self._cookies[name] = value
                    received_cookies += 1
        if self._trace:
            logger.debug(
                "[{}] FlareSolverr solution: "
                "cookies_received={} user_agent_received={}",
                self._debug_name or "flaresolverr",
                received_cookies,
                self._user_agent is not None,
            )

    async def _ensure_solution(
        self,
        url: str,
        timeout: float,  # noqa: ASYNC109  # HTTP client timeout
        *,
        force: bool = False,
    ) -> None:
        if force or self._user_agent is None:
            await self._solve(url, timeout)

    def _request_headers(self, headers: dict[str, str] | None) -> dict[str, str]:
        request_headers = self._headers | (headers or {})
        if self._user_agent:
            # Cloudflare clearance cookies are bound to the solver browser's UA.
            request_headers["user-agent"] = self._user_agent
        return request_headers

    def _update_cookies(self, response: httpx.Response) -> None:
        self._cookies.update(response.cookies)

    async def _request(  # noqa: C901  # Retry and fallback handling
        self,
        method: str,
        url: str,
        *,
        timeout: float | None = None,  # noqa: ASYNC109  # HTTP client timeout
        **kwargs: Any,
    ) -> httpx.Response:
        request_timeout = self._timeout if timeout is None else timeout
        params = kwargs.pop("params", None)
        headers = kwargs.pop("headers", None)
        request_url = str(httpx.URL(url, params=params))
        if method.upper() == "GET":
            # The browser response is the authoritative result for each GET URL.
            await self._solve(request_url, request_timeout)
        else:
            await self._ensure_solution(request_url, request_timeout)
        if (
            method.upper() == "GET"
            and self._solver_response is not None
            and self._solver_response.is_success
        ):
            if self._trace:
                log_http_trace(
                    self._debug_name or "flaresolverr", self._solver_response
                )
            return self._solver_response

        try:
            async with httpx.AsyncClient(
                proxy=self._proxy,
                timeout=request_timeout,
                trust_env=False,
                follow_redirects=True,
            ) as client:
                response = await client.request(
                    method,
                    url,
                    params=params,
                    headers=self._request_headers(headers),
                    cookies=self._cookies,
                    **kwargs,
                )
            self._update_cookies(response)
            if response.status_code in {403, 503}:
                await self._ensure_solution(request_url, request_timeout, force=True)
                async with httpx.AsyncClient(
                    proxy=self._proxy,
                    timeout=request_timeout,
                    trust_env=False,
                    follow_redirects=True,
                ) as client:
                    response = await client.request(
                        method,
                        url,
                        params=params,
                        headers=self._request_headers(headers),
                        cookies=self._cookies,
                        **kwargs,
                    )
                self._update_cookies(response)
            if self._trace:
                log_http_trace(self._debug_name or "flaresolverr", response)
            response.raise_for_status()
        except httpx.TimeoutException as e:
            raise HttpRequestError("请求超时，请稍后重试") from e
        except httpx.HTTPStatusError as e:
            if (
                method.upper() == "GET"
                and self._solver_response is not None
                and self._solver_response.is_success
            ):
                if self._trace:
                    log_http_trace(
                        self._debug_name or "flaresolverr",
                        self._solver_response,
                    )
                return self._solver_response
            response = e.response
            status = response.status_code
            reason = response.reason_phrase
            raise HttpRequestError(
                f"请求失败: HTTP {status} {reason}".rstrip(),
                status=status,
            ) from e
        except httpx.HTTPError as e:
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
    ) -> httpx.Response:
        return await self._request(method, url, timeout=timeout, **kwargs)

    async def get(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,  # noqa: ASYNC109  # requests timeout
        **kwargs: Any,
    ) -> httpx.Response:
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
    ) -> httpx.Response:
        return await self.request("POST", url, timeout=timeout, **kwargs)
