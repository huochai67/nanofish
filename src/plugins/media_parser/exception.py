from __future__ import annotations

from typing import Any

import httpx
import curl_cffi
from curl_cffi.requests.exceptions import HTTPError as CurlHTTPError
from nonebot.exception import MatcherException

# 这些状态码通常只是暂时的, 值得在队列中重试
_RETRYABLE_HTTP_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})

_HTTP_STATUS_HINTS: dict[int, str] = {
    400: "请求参数有误",
    401: "需要登录或授权",
    403: "访问被拒绝，可能触发平台风控",
    404: "内容不存在或已被删除",
    408: "请求超时",
    412: "触发平台风控",
    418: "触发平台风控",
    429: "请求过于频繁，已被平台限流",
    500: "平台服务器错误",
    502: "平台网关错误",
    503: "平台服务暂不可用",
    504: "平台网关超时",
}

_MEDIA_GENERIC_MESSAGES = frozenset({"媒体下载失败", "媒体下载失败，请稍后重试"})


class ParseException(Exception):
    """解析异常; retryable 决定队列是否重试"""

    retryable: bool = True

    def __init__(self, message: str, *, retryable: bool | None = None):
        super().__init__(message)
        self.message = message
        if retryable is not None:
            self.retryable = retryable


class DownloadException(ParseException):
    """下载异常"""

    def __init__(self, message: str | None = None, *, retryable: bool | None = None):
        super().__init__(message or "媒体下载失败", retryable=retryable)


class DeliveryFailure(DownloadException):
    """媒体投递失败, 携带已经生成的卡片/部分媒体消息"""

    def __init__(
        self,
        message: str,
        partial_messages: list[Any] | None = None,
    ):
        super().__init__(message)
        self.partial_messages: list[Any] = partial_messages or []


class IgnoreException(ParseException):
    """可忽略异常"""

    retryable = False

    def __init__(self, message: str | None = None):
        super().__init__(message or "可忽略异常")


class TipException(ParseException):
    """提示异常"""

    retryable = False


def is_retryable(error: BaseException) -> bool:
    """判断异常是否值得重试; 控制流异常与明确的业务错误不重试"""
    if isinstance(error, MatcherException):
        return False
    if isinstance(error, ParseException):
        if not error.retryable:
            return False
        cause = error.__cause__
        if cause is not None and cause is not error:
            return is_retryable(cause)
        return True
    if isinstance(error, (TimeoutError, httpx.TimeoutException)):
        return True
    if isinstance(error, httpx.HTTPStatusError):
        return error.response.status_code in _RETRYABLE_HTTP_STATUS
    if isinstance(error, CurlHTTPError):
        response = getattr(error, "response", None)
        status = getattr(response, "status_code", None)
        return status in _RETRYABLE_HTTP_STATUS if status is not None else True
    if isinstance(error, httpx.TransportError):
        return True
    if isinstance(error, curl_cffi.CurlError):
        return True
    if isinstance(error, (ConnectionError, OSError)):
        return True
    # 未预期的异常可能来自临时性的页面结构/网络变化, 交给队列重试
    return True


def _truncate(text: str, limit: int = 160) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1]}…"


def _http_status_text(status: int) -> str:
    hint = _HTTP_STATUS_HINTS.get(status)
    if hint is None:
        hint = "平台服务异常" if status >= 500 else "请求被平台拒绝"
    return f"请求失败（HTTP {status}）：{hint}"


def _http_status_message(error: httpx.HTTPStatusError) -> str:
    return _http_status_text(error.response.status_code)


def _curl_error_message(error: curl_cffi.CurlError) -> str:
    if isinstance(error, CurlHTTPError):
        response = getattr(error, "response", None)
        status = getattr(response, "status_code", None)
        if status is not None:
            return _http_status_text(status)

    detail = str(error).lower()
    if "timed out" in detail or "timeout" in detail:
        return "网络请求超时，请稍后重试"
    return "网络请求失败，请检查网络后重试"


def describe_error(error: BaseException) -> str:
    """把异常转换为可直接展示给用户的简短说明"""
    if isinstance(error, (TipException, IgnoreException, DownloadException)):
        return _truncate(error.message)

    if isinstance(error, httpx.HTTPStatusError):
        return _http_status_message(error)

    if isinstance(error, (TimeoutError, httpx.TimeoutException)):
        return "请求超时，请稍后重试"

    if isinstance(error, curl_cffi.CurlError):
        return _curl_error_message(error)

    if isinstance(error, httpx.TransportError):
        return "网络连接失败，请检查网络后重试"

    if isinstance(error, httpx.HTTPError):
        detail = _truncate(str(error))
        return f"请求失败：{detail}" if detail else "请求失败"

    if isinstance(error, OSError):
        detail = _truncate(str(error))
        return f"网络或文件操作失败：{detail}" if detail else "网络或文件操作失败"

    if isinstance(error, ParseException):
        return _truncate(error.message) or "平台返回了无法识别的数据"

    detail = _truncate(str(error))
    return detail or type(error).__name__


def format_parse_error(error: BaseException, platform: str | None = None) -> str:
    """生成最终错误提示; platform 为平台显示名称"""
    detail = describe_error(error)

    if isinstance(error, TipException):
        return detail
    if isinstance(error, IgnoreException):
        return detail
    if isinstance(error, DeliveryFailure):
        return f"{platform}：{detail}" if platform else detail

    if isinstance(error, DownloadException):
        prefix = f"{platform}媒体下载失败" if platform else "媒体下载失败"
        if not detail or detail in _MEDIA_GENERIC_MESSAGES:
            return prefix
        if detail.startswith("媒体下载失败"):
            detail = detail[len("媒体下载失败") :].lstrip("：: ")
            if not detail:
                return prefix
        return f"{prefix}：{detail}"

    prefix = f"{platform}解析失败" if platform else "解析失败"
    if detail.startswith("解析失败"):
        detail = detail[len("解析失败") :].lstrip("：: ")
    if not detail:
        return prefix
    return f"{prefix}：{detail}"
