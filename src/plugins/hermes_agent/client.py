"""Minimal Hermes Agent HTTP client for session chat."""

from __future__ import annotations

import re
from dataclasses import dataclass
from http import HTTPStatus
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

import httpx
from nonebot import logger

if TYPE_CHECKING:
    from .config import Config

_PROFILE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


def normalize_profile(profile: str) -> str:
    """Map the explicit ``default`` spelling to the unprefixed Hermes route."""
    value = profile.strip()
    return "" if value == "default" else value


def valid_profile(profile: str) -> bool:
    return not profile or bool(_PROFILE_PATTERN.fullmatch(profile))


class HermesError(Exception):
    """A user-displayable Hermes request failure."""

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        code: str = "",
    ) -> None:
        self.message = message
        self.status = status
        self.code = code
        super().__init__(message)


class HermesAuthError(HermesError):
    """The gateway rejected the API key (or none is configured)."""


class HermesMissingKeyError(HermesAuthError):
    """No API key is configured locally for the selected profile."""


class HermesSessionNotFoundError(HermesError):
    """The requested Hermes session no longer exists."""


class HermesTimeoutError(HermesError):
    """The gateway did not answer within the configured timeout."""


class HermesBusyError(HermesError):
    """The gateway is rate-limiting or the conversation is already running."""


@dataclass(frozen=True, slots=True)
class ChatResult:
    session_id: str
    content: str
    status: str


def _error_details(response: httpx.Response) -> tuple[str, str]:
    try:
        payload = response.json()
    except ValueError:
        return "", ""
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            return (
                str(error.get("message") or "").strip()[:300],
                str(error.get("code") or "").strip(),
            )
        if isinstance(error, str):
            return error.strip()[:300], ""
        return (
            str(payload.get("message") or payload.get("detail") or "").strip()[:300],
            str(payload.get("code") or "").strip(),
        )
    return "", ""


def _content_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)
    return ""


class HermesClient:
    """Thin client around the Hermes session API."""

    def __init__(
        self,
        config: Config,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._config = config
        self._transport = transport

    def _api_key(self, profile: str) -> str:
        key = self._config.agent_profiles.get(profile, "")
        if not key and not profile:
            key = (
                self._config.agent_profiles.get("default", "")
                or self._config.agent_api_key
            )
        if not key:
            msg = (
                f"未配置 profile `{profile}` 的 Hermes API Key"
                if profile
                else "未配置 Hermes Agent API Key"
            )
            raise HermesMissingKeyError(msg)
        return key

    def _url(self, profile: str, path: str) -> str:
        base = self._config.agent_endpoint
        if profile:
            return f"{base}/p/{quote(profile, safe='')}{path}"
        return f"{base}{path}"

    async def _request(
        self,
        method: str,
        profile: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        profile = normalize_profile(profile)
        headers = {
            "Authorization": f"Bearer {self._api_key(profile)}",
            "Accept": "application/json",
        }
        timeout = httpx.Timeout(self._config.agent_timeout)
        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                transport=self._transport,
                trust_env=False,
            ) as client:
                response = await client.request(
                    method,
                    self._url(profile, path),
                    headers=headers,
                    json=body,
                )
        except httpx.TimeoutException as exc:
            msg = "Hermes 响应超时，请稍后重试"
            raise HermesTimeoutError(msg) from exc
        except httpx.HTTPError as exc:
            logger.warning("[hermes_agent] request failed: {}", type(exc).__name__)
            msg = "无法连接 Hermes，请检查服务状态"
            raise HermesError(msg) from exc

        if response.status_code >= HTTPStatus.BAD_REQUEST:
            message, code = _error_details(response)
            logger.warning(
                "[hermes_agent] {} {} -> {} {}",
                method,
                path,
                response.status_code,
                code,
            )
            self._raise_for_status(response.status_code, message, code)

        try:
            payload = response.json()
        except ValueError as exc:
            msg = "Hermes 返回了无法解析的响应"
            raise HermesError(msg, status=response.status_code) from exc
        if not isinstance(payload, dict):
            msg = "Hermes 返回了意外的响应格式"
            raise HermesError(msg, status=response.status_code)
        return payload

    @staticmethod
    def _raise_for_status(status: int, message: str, code: str) -> None:
        detail = message or f"Hermes 请求失败（HTTP {status}）"
        if status in {HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN}:
            raise HermesAuthError(detail, status=status, code=code)
        if status == HTTPStatus.NOT_FOUND and code == "session_not_found":
            raise HermesSessionNotFoundError(detail, status=status, code=code)
        if status in {HTTPStatus.CONFLICT, HTTPStatus.TOO_MANY_REQUESTS}:
            raise HermesBusyError(detail, status=status, code=code)
        raise HermesError(detail, status=status, code=code)

    async def create_session(self, profile: str, title: str | None = None) -> str:
        body: dict[str, Any] = {"source": "api_server"}
        if title:
            body["title"] = title
        payload = await self._request("POST", profile, "/api/sessions", body=body)
        session = payload.get("session")
        session_id = session.get("id") if isinstance(session, dict) else None
        if not isinstance(session_id, str) or not session_id:
            msg = "Hermes 未返回会话 ID"
            raise HermesError(msg)
        return session_id

    async def chat(
        self,
        *,
        profile: str,
        session_id: str,
        message: str | list[dict[str, Any]],
    ) -> ChatResult:
        payload = await self._request(
            "POST",
            profile,
            f"/api/sessions/{quote(session_id, safe='')}/chat",
            body={"message": message},
        )
        content = ""
        raw_message = payload.get("message")
        if isinstance(raw_message, dict):
            content = _content_text(raw_message.get("content"))
        status = str(payload.get("status") or "completed")
        if not content and status == "failed":
            msg = "Hermes 未能完成本轮回复"
            raise HermesError(msg, code="agent_error")
        effective_id = payload.get("session_id")
        return ChatResult(
            session_id=effective_id if isinstance(effective_id, str) else session_id,
            content=content,
            status=status,
        )


__all__ = [
    "ChatResult",
    "HermesAuthError",
    "HermesBusyError",
    "HermesClient",
    "HermesError",
    "HermesMissingKeyError",
    "HermesSessionNotFoundError",
    "HermesTimeoutError",
    "normalize_profile",
    "valid_profile",
]
