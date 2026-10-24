import re
from dataclasses import dataclass
from typing import Any, TypeVar

from nonebot import get_driver, logger, on_command
from nonebot.adapters import Message
from nonebot.exception import MatcherException
from nonebot.params import CommandArg
from nonebot_plugin_alconna.uniseg import File, Video, Voice

from ..config import pconfig
from ..delivery import collect_parse_messages
from ..exception import DeliveryFailure, ParseException, TipException, format_parse_error
from ..helper import UniHelper, UniMessage
from ..parsers import BaseParser, BilibiliParser, ParseResult
from ..queue import parser_queue
from ..utils import LimitedSizeDict
from .rule import Searched, SearchResult, on_keyword_regex


def _get_enabled_parser_classes() -> list[type[BaseParser]]:
    disabled_platforms = set(pconfig.disabled_platforms)
    all_subclass = BaseParser.get_all_subclass()
    return [
        parser_cls
        for parser_cls in all_subclass
        if parser_cls.platform.name not in disabled_platforms
    ]


# 关键词 -> Parser 映射
KEYWORD_PARSER_MAP: dict[str, BaseParser] = {}
T = TypeVar("T", bound=BaseParser)


def get_parser(keyword: str) -> BaseParser:
    return KEYWORD_PARSER_MAP[keyword]


def get_parser_by_type(parser_type: type[T]) -> T:
    for parser in KEYWORD_PARSER_MAP.values():
        if isinstance(parser, parser_type):
            return parser
    raise ValueError(f"未找到类型为 {parser_type} 的 parser 实例")


@get_driver().on_startup
def register_parser_matcher() -> None:
    enabled_classes = _get_enabled_parser_classes()

    enabled_platforms = []
    for _cls in enabled_classes:
        parser = _cls()
        enabled_platforms.append(parser.platform.display_name)
        for keyword, _ in _cls._key_patterns:
            KEYWORD_PARSER_MAP[keyword] = parser
    logger.info(f"启用平台: {', '.join(sorted(enabled_platforms))}")

    patterns = [p for _cls in enabled_classes for p in _cls._key_patterns]
    matcher = on_keyword_regex(*patterns)
    matcher.append_handler(parser_handler)


# 缓存结果
_RESULT_CACHE = LimitedSizeDict[str, ParseResult](max_size=50)


def clear_result_cache() -> None:
    _RESULT_CACHE.clear()


@dataclass(slots=True)
class _PreparedParse:
    result: ParseResult
    messages: list[UniMessage[Any]]


async def _send_messages(messages: list[UniMessage[Any]]) -> None:
    for message in messages:
        if message.has(Video) or message.has(Voice) or message.has(File):
            await message.send()
        else:
            await UniHelper.reply_to_current_event(message).send()


@UniHelper.with_processing_reply
async def parser_handler(
    sr: SearchResult = Searched(),
) -> None:
    """统一的解析处理器"""
    cache_key = sr.searched.group(0)
    parser = get_parser(sr.keyword)
    label = f"{parser.platform.name}:{cache_key[:80]}"

    async def prepare() -> _PreparedParse:
        result = _RESULT_CACHE.get(cache_key)
        if result is None:
            result = await parser.parse(sr.keyword, sr.searched)
            logger.debug(f"解析结果: {result}")
        else:
            logger.debug(f"命中缓存: {cache_key}, 结果: {result}")

        # 卡片与媒体全部生成完毕后才发送, 重试不会产生重复消息
        messages = await collect_parse_messages(result)
        _RESULT_CACHE[cache_key] = result
        return _PreparedParse(result, messages)

    try:
        prepared = await parser_queue.submit(
            prepare,
            label=label,
            dedupe_key=cache_key,
        )
    except DeliveryFailure as error:
        # 最后一次尝试仍有媒体失败: 发送已成功的部分, 再发送一条完整错误提示
        if error.partial_messages:
            try:
                await _send_messages(error.partial_messages)
            except Exception:  # noqa: BLE001 - 不覆盖原始失败原因
                logger.exception("发送部分解析结果失败")
        raise TipException(
            format_parse_error(error, parser.platform.display_name)
        ) from error
    except ParseException as error:
        raise TipException(
            format_parse_error(error, parser.platform.display_name)
        ) from error
    except MatcherException:
        raise
    except Exception as error:
        logger.opt(exception=error).error("media parser handling failed")
        raise TipException(
            format_parse_error(error, parser.platform.display_name)
        ) from error

    await _send_messages(prepared.messages)


@on_command("bm", priority=3, block=True).handle()
@UniHelper.with_processing_reply
async def _(message: Message = CommandArg()):
    text = message.extract_plain_text()
    matched = re.search(r"(BV[A-Za-z0-9]{10})(\s\d{1,3})?", text)
    if not matched:
        await UniHelper.reply_to_current_event("请发送正确的 BV 号").finish()

    bvid, page_num = matched.group(1), matched.group(2)
    page_idx = int(page_num) - 1 if page_num else 0

    parser = get_parser_by_type(BilibiliParser)

    _, audio_url = await parser.extract_download_urls(bvid=bvid, page_index=page_idx)
    if not audio_url:
        await UniHelper.reply_to_current_event("未找到可下载的音频").finish()

    audio_path = await parser.downloader.download_audio(
        audio_url, audio_name=f"{bvid}-{page_idx}.mp3", ext_headers=parser.headers
    )
    await UniHelper.reply_to_current_event(
        UniMessage(UniHelper.record_seg(audio_path))
    ).send()

    if pconfig.need_upload:
        await UniHelper.reply_to_current_event(
            UniMessage(UniHelper.file_seg(audio_path))
        ).send()


from ..download import yt_dlp_downloader

if yt_dlp_downloader is not None:
    from ..parsers import YouTubeParser

    @on_command("ym", priority=3, block=True).handle()
    @UniHelper.with_processing_reply
    async def _(message: Message = CommandArg()):
        text = message.extract_plain_text()
        parser = get_parser_by_type(YouTubeParser)
        _, matched = parser.search_url(text)
        if not matched:
            await UniHelper.reply_to_current_event("请发送正确的油管链接").finish()

        url = matched.group(0)

        audio_path = await yt_dlp_downloader.download_audio(url, parser.cookie_file)
        await UniHelper.reply_to_current_event(
            UniMessage(UniHelper.record_seg(audio_path))
        ).send()

        if pconfig.need_upload:
            await UniHelper.reply_to_current_event(
                UniMessage(UniHelper.file_seg(audio_path))
            ).send()
