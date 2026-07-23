import asyncio
import base64
import mimetypes
import re
import time
from dataclasses import dataclass
from typing import Any

from nonebot import logger, on_command, require
from nonebot.adapters.onebot.v11 import Bot, MessageEvent, MessageSegment
from nonebot.adapters.onebot.v11.message import Message
from nonebot.exception import FinishedException
from nonebot.plugin import PluginMetadata

from src.plugin_config import get_yaml_plugin_config

from .config import Config

require("acl")
require("app")
require("utils")
from ..acl import check_quota, consume_quota, require_command
from ..app import app_imgsearch_image_cq
from ..utils import (
    HttpRequestError,
    finish_processing_reply,
    get_first_image,
    get_reply,
    http_get,
    http_post,
    send_processing_reply,
)

__plugin_meta__ = PluginMetadata(
    name="imgsearch",
    description="SauceNAO 与 Soutubot 反向图片搜索",
    usage="/imgsearch 后附图，或回复一张图片后发送 /imgsearch",
    config=Config,
)

config: Config = get_yaml_plugin_config(Config, "imgsearch")
imgsearch = on_command(
    "imgsearch",
    priority=10,
    block=True,
    permission=require_command("imgsearch"),
)


@dataclass(frozen=True, slots=True)
class SearchResult:
    source: str
    similarity: float | None
    title: str
    author: str
    url: str
    thumbnail: str


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _first_text(data: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = data.get(key)
        if isinstance(value, list):
            value = next((item for item in value if isinstance(item, str)), None)
        text = _text(value)
        if text:
            return text
    return ""


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _image_filename(content_type: str) -> str:
    extension = mimetypes.guess_extension(content_type) or ".jpg"
    return f"image{extension}"


def _soutubot_api_key(m: int, user_agent: str) -> str:
    timestamp = int(time.time())
    value = timestamp**2 + len(user_agent) ** 2 + m
    return base64.b64encode(str(value).encode()).decode().rstrip("=")[::-1]


_SOUTUBOT_HOSTS = {
    "nhentai": "nhentai.net",
    "ehentai": "e-hentai.org",
    "panda": "panda.chaika.moe",
}

_SOUTUBOT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def _soutubot_result_url(data: dict[str, Any]) -> str:
    direct_url = _first_text(data, "url", "source_url", "link", "ext_urls")
    if direct_url:
        return direct_url

    page_path = _text(data.get("pagePath"))
    source = _text(data.get("source")).lower()
    host = _SOUTUBOT_HOSTS.get(source)
    if host and page_path.startswith("/"):
        return f"https://{host}{page_path}"
    return ""


async def _resolve_image_url(bot: Bot, event: MessageEvent) -> str | None:
    direct = get_first_image(event.original_message)
    if direct:
        return direct

    reply = await get_reply(bot=bot, msg=event.original_message)
    if not reply:
        return None
    raw = reply.get("raw_message")
    return get_first_image(Message(raw)) if raw else None


async def _download_image(url: str) -> tuple[bytes, str]:
    response = await http_get(url, proxy=config.proxy, timeout=config.imgsearch_timeout)
    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip()
    if not content_type.startswith("image/"):
        raise ValueError("消息图片不是有效的图片文件")
    content_length = response.headers.get("content-length")
    if content_length and int(content_length) > config.imgsearch_max_file_size:
        raise ValueError("图片超过大小限制")
    if len(response.content) > config.imgsearch_max_file_size:
        raise ValueError("图片超过大小限制")
    return response.content, content_type


class ImageSearchClient:
    def __init__(self) -> None:
        self._soutubot_m: int | None = None

    async def _refresh_soutubot_cache(self) -> None:
        response = await http_get(
            "https://soutubot.moe/",
            headers={"user-agent": _SOUTUBOT_USER_AGENT},
            proxy=config.proxy,
            timeout=config.imgsearch_timeout,
        )
        match = re.search(r"m:\s*(-?\d+),", response.text)
        if match is None or int(match.group(1)) <= 0:
            raise HttpRequestError("Soutubot 初始化失败")
        self._soutubot_m = int(match.group(1))

    async def _soutubot_headers(self) -> dict[str, str]:
        if self._soutubot_m is None:
            await self._refresh_soutubot_cache()
        if self._soutubot_m is None:
            raise HttpRequestError("Soutubot 初始化失败")
        return {
            "accept": "application/json, text/plain, */*",
            "dnt": "1",
            "origin": "https://soutubot.moe",
            "referer": "https://soutubot.moe/",
            "user-agent": _SOUTUBOT_USER_AGENT,
            "x-api-key": _soutubot_api_key(self._soutubot_m, _SOUTUBOT_USER_AGENT),
            "x-requested-with": "XMLHttpRequest",
        }

    async def search_saucenao(
        self,
        image: bytes,
        content_type: str,
    ) -> list[SearchResult]:
        params: dict[str, str | int] = {
            "output_type": 2,
            "numres": config.imgsearch_result_limit,
            "db": 999,
        }
        if config.imgsearch_saucenao_api_key:
            params["api_key"] = config.imgsearch_saucenao_api_key
        response = await http_post(
            "https://saucenao.com/search.php",
            params=params,
            files={"file": (_image_filename(content_type), image, content_type)},
            proxy=config.proxy,
            timeout=config.imgsearch_timeout,
        )
        try:
            payload = response.json()
        except ValueError as e:
            raise HttpRequestError("SauceNAO 返回了非 JSON 响应") from e
        if not isinstance(payload, dict):
            raise HttpRequestError("SauceNAO 返回数据异常")

        header = payload.get("header")
        status = _number(header.get("status")) if isinstance(header, dict) else None
        if isinstance(header, dict) and status not in {None, 0.0}:
            message = _first_text(header, "message") or "上游请求失败"
            raise HttpRequestError(f"SauceNAO: {message}")

        results: list[SearchResult] = []
        raw_results = payload.get("results")
        if not isinstance(raw_results, list):
            return results
        for raw in raw_results:
            if not isinstance(raw, dict):
                continue
            result_header = raw.get("header")
            result_data = raw.get("data")
            if not isinstance(result_header, dict) or not isinstance(result_data, dict):
                continue
            results.append(
                SearchResult(
                    source=_first_text(result_data, "source") or "SauceNAO",
                    similarity=_number(result_header.get("similarity")),
                    title=_first_text(result_data, "title", "eng_name", "jp_name"),
                    author=_first_text(
                        result_data,
                        "member_name",
                        "author_name",
                        "creator",
                        "author",
                    ),
                    url=_first_text(result_data, "ext_urls", "source_url", "url"),
                    thumbnail=_first_text(result_header, "thumbnail"),
                )
            )
        return results

    async def search_soutubot(
        self,
        image: bytes,
        content_type: str,
    ) -> list[SearchResult]:
        logger.info(
            "[Soutubot] sending search: key_configured=true proxy_configured={} "
            "image_bytes={} content_type={}",
            bool(config.proxy),
            len(image),
            content_type,
        )
        try:
            response = await http_post(
                "https://soutubot.moe/api/search",
                data={"factor": str(config.imgsearch_soutubot_factor)},
                files={"file": (_image_filename(content_type), image, content_type)},
                headers=await self._soutubot_headers(),
                proxy=config.proxy,
                timeout=config.imgsearch_timeout,
            )
        except HttpRequestError as e:
            if e.status not in {401, 403}:
                raise
            self._soutubot_m = None
            response = await http_post(
                "https://soutubot.moe/api/search",
                data={"factor": str(config.imgsearch_soutubot_factor)},
                files={"file": (_image_filename(content_type), image, content_type)},
                headers=await self._soutubot_headers(),
                proxy=config.proxy,
                timeout=config.imgsearch_timeout,
            )
        try:
            payload = response.json()
        except ValueError as e:
            raise HttpRequestError("Soutubot 返回了非 JSON 响应") from e
        raw_results: Any = payload
        if isinstance(payload, dict):
            raw_results = (
                payload.get("results")
                or payload.get("data")
                or payload.get("result")
                or []
            )
        if not isinstance(raw_results, list):
            raise HttpRequestError("Soutubot 返回数据异常")

        results: list[SearchResult] = []
        for raw in raw_results:
            if not isinstance(raw, dict):
                continue
            similarity = _number(
                raw.get("similarity") or raw.get("score") or raw.get("confidence")
            )
            results.append(
                SearchResult(
                    source=_first_text(raw, "source", "site", "provider") or "Soutubot",
                    similarity=similarity,
                    title=_first_text(raw, "title", "name", "filename"),
                    author=_first_text(raw, "author", "artist", "creator", "user"),
                    url=_soutubot_result_url(raw),
                    thumbnail=_first_text(
                        raw, "previewImageUrl", "thumbnail", "imageUrl"
                    ),
                )
            )
        return results

    async def search(
        self,
        image: bytes,
        content_type: str,
    ) -> tuple[list[SearchResult], list[str]]:
        tasks = [self.search_saucenao(image, content_type)]
        source_names = ["SauceNAO"]
        tasks.append(self.search_soutubot(image, content_type))
        source_names.append("Soutubot")
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        results: list[SearchResult] = []
        errors: list[str] = []
        for source_name, response in zip(source_names, responses, strict=True):
            if isinstance(response, BaseException):
                message = (
                    response.message
                    if isinstance(response, HttpRequestError)
                    else str(response)
                )
                errors.append(f"{source_name}: {message or type(response).__name__}")
            else:
                results.extend(response)
        results = [
            result
            for result in results
            if result.similarity is None
            or result.similarity >= config.imgsearch_similarity_threshold
        ]
        results.sort(key=lambda item: item.similarity or -1, reverse=True)
        return results[: config.imgsearch_result_limit], errors


search_client = ImageSearchClient()


def _format_results(results: list[SearchResult], errors: list[str]) -> str:
    lines = ["搜图结果"]
    for index, result in enumerate(results, start=1):
        similarity = (
            f" {result.similarity:.2f}%" if result.similarity is not None else ""
        )
        lines.append(f"{index}. [{result.source}]{similarity}")
        if result.title:
            lines.append(f"标题: {result.title}")
        if result.author:
            lines.append(f"作者: {result.author}")
        if result.url:
            lines.append(result.url)
    if errors:
        lines.append("失败来源: " + "；".join(errors))
    return "\n".join(lines)


def _build_payload(
    image: bytes,
    content_type: str,
    results: list[SearchResult],
    errors: list[str],
) -> dict[str, Any]:
    encoded_image = base64.b64encode(image).decode("ascii")
    return {
        "image": f"data:{content_type};base64,{encoded_image}",
        "results": [
            {
                "source": result.source,
                "similarity": result.similarity,
                "title": result.title,
                "author": result.author,
                "url": result.url,
                "thumbnail": result.thumbnail,
            }
            for result in results
        ],
        "errors": errors,
    }


def _reply(event: MessageEvent, content: str) -> Message:
    return MessageSegment.reply(event.message_id) + content


@imgsearch.handle()
async def handle_imgsearch(bot: Bot, event: MessageEvent) -> None:
    quota = check_quota(event, "imgsearch")
    if not quota.allowed:
        await imgsearch.finish(quota.message or "额度不足")
        return

    image_url = await _resolve_image_url(bot, event)
    if not image_url:
        await imgsearch.finish(
            "用法: /imgsearch 后附图，或回复一张图片后发送 /imgsearch"
        )
        return

    processing = await send_processing_reply(imgsearch, bot, event, "正在搜图，请稍候…")
    try:
        image, content_type = await _download_image(image_url)
        quota = consume_quota(event, "imgsearch")
        if not quota.allowed:
            await finish_processing_reply(
                imgsearch,
                processing,
                _reply(event, quota.message or "额度不足"),
            )
            return
        results, errors = await search_client.search(image, content_type)
        if not results and not errors:
            await finish_processing_reply(
                imgsearch,
                processing,
                _reply(event, "未找到匹配结果"),
            )
            return
        try:
            result_image = await app_imgsearch_image_cq(
                _build_payload(image, content_type, results, errors)
            )
        except FinishedException:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("imgsearch result page screenshot failed")
            await finish_processing_reply(
                imgsearch,
                processing,
                _reply(event, _format_results(results, errors)),
            )
            return
        await finish_processing_reply(imgsearch, processing, result_image)
    except FinishedException:
        raise
    except (HttpRequestError, ValueError) as e:
        logger.warning("imgsearch request error: {}", e)
        await finish_processing_reply(imgsearch, processing, _reply(event, str(e)))
    except Exception:  # noqa: BLE001
        logger.exception("imgsearch unexpected error")
        await finish_processing_reply(
            imgsearch,
            processing,
            _reply(event, "搜图失败，请稍后重试"),
        )
