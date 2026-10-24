"""`/agent` command: forward QQ messages to a Hermes Agent session."""

import asyncio
import re
from pathlib import Path
from typing import Any

from nonebot import get_driver, logger, on_command, on_message, require
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, Message, MessageEvent
from nonebot.exception import FinishedException
from nonebot.matcher import Matcher
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata

from src.plugin_config import get_yaml_plugin_config

require("acl")
require("utils")
require("nonebot_plugin_localstore")

import nonebot_plugin_localstore as localstore

from ..acl import consume_quota, require_command
from ..utils import (
    ProcessingReply,
    get_plaintext,
    get_replyid,
    reply_to_event,
    send_processing_reply,
)
from .client import (
    ChatResult,
    HermesAuthError,
    HermesBusyError,
    HermesClient,
    HermesError,
    HermesMissingKeyError,
    HermesSessionNotFoundError,
    HermesTimeoutError,
    normalize_profile,
    valid_profile,
)
from .config import Config
from .reference import (
    ReferenceContext,
    collect_current_attachments,
    collect_reference,
    lookup_session_reply,
)
from .store import AgentStore

__plugin_meta__ = PluginMetadata(
    name="hermes_agent",
    description="通过 Hermes Agent 会话处理 QQ 消息，支持引用消息/文件作为上下文",
    usage=(
        "/agent [@profile] <消息>（可引用一条消息附加文本或文件）；"
        "引用机器人回复后可直接发送内容继续会话"
    ),
    config=Config,
)

config: Config = get_yaml_plugin_config(Config, "agent")

_PROFILE_ARG = re.compile(
    r"^@([A-Za-z0-9][A-Za-z0-9_.-]{0,63})(?:\s+|$)(.*)$",
    re.DOTALL,
)
_TITLE_MAX_CHARS = 80
_EMPTY_REPLY = "（Hermes 未返回文本内容）"
_ATTACHMENT_TYPES = {"image", "file", "record", "video", "forward"}

agent = on_command(
    "agent",
    priority=10,
    block=True,
    permission=require_command("agent"),
)

agent_reply = on_message(
    priority=11,
    block=True,
    permission=require_command("agent"),
)

hermes_client = HermesClient(config)
_session_locks: dict[str, asyncio.Lock] = {}


def _database_path() -> Path:
    if config.agent_db_path:
        return Path(config.agent_db_path).expanduser()
    return localstore.get_plugin_data_file("agent.sqlite3")


agent_store = AgentStore(_database_path())


def parse_agent_args(arg: Message) -> tuple[str | None, str]:
    """Split an optional leading ``@profile`` from the command argument."""
    text = get_plaintext(arg).strip()
    if not text:
        return None, ""
    match = _PROFILE_ARG.match(text)
    if match is None:
        return None, text
    return match.group(1), match.group(2).strip()


def event_scope(event: MessageEvent) -> str:
    if isinstance(event, GroupMessageEvent):
        return f"group:{event.group_id}"
    return f"private:{event.user_id}"


def _has_attachment(message: Message) -> bool:
    return any(segment.type in _ATTACHMENT_TYPES for segment in message)


def _is_command_text(text: str) -> bool:
    stripped = text.lstrip()
    if not stripped:
        return False
    prefixes = {
        prefix
        for prefix in (get_driver().config.command_start or set())
        if prefix
    }
    return any(stripped.startswith(prefix) for prefix in prefixes)


async def _with_current_attachments(
    bot: Bot,
    event: MessageEvent,
    reference: ReferenceContext,
) -> ReferenceContext:
    current = await collect_current_attachments(bot, event, config)
    reference.current_text_parts.extend(current.current_text_parts)
    reference.current_images.extend(current.current_images)
    allowed = max(0, config.agent_max_attachments - len(reference.images))
    del reference.current_images[allowed:]
    return reference


def build_message_content(
    reference: ReferenceContext,
    message: str,
) -> str | list[dict[str, Any]]:
    text = reference.render()
    if message:
        text = f"{text}\n\n{message}" if text else message
    images = reference.all_images
    if not images:
        return text
    parts: list[dict[str, Any]] = []
    if text.strip():
        parts.append({"type": "text", "text": text})
    parts.extend(
        {"type": "image_url", "image_url": {"url": image.data_url}}
        for image in images
    )
    return parts


def split_text(text: str, limit: int) -> list[str]:
    """Split a final answer into QQ-sized chunks, preferring line boundaries."""
    text = text.strip()
    if not text:
        return [_EMPTY_REPLY]
    limit = max(100, limit)
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    remaining = text
    while len(remaining) > limit:
        cut = remaining.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = remaining.rfind(" ", 0, limit)
        if cut < limit // 2:
            cut = limit
        chunk = remaining[:cut].rstrip()
        if chunk:
            chunks.append(chunk)
        remaining = remaining[cut:].lstrip("\n")
    if remaining.strip():
        chunks.append(remaining.strip())
    return chunks or [_EMPTY_REPLY]


def _message_id(result: object) -> str | None:
    if not isinstance(result, dict):
        return None
    value = result.get("message_id")
    if isinstance(value, int | str):
        return str(value)
    return None


def _session_title(message: str, reference: ReferenceContext) -> str:
    source = message.strip()
    if not source:
        source = next(
            (
                part
                for part in (*reference.text_parts, *reference.current_text_parts)
                if part.strip()
            ),
            "",
        )
    source = " ".join(source.split())
    return source[:_TITLE_MAX_CHARS] or "QQ /agent"


def _profile_label(profile: str) -> str:
    return profile or "default"


def _auth_message(exc: HermesAuthError, profile: str) -> str:
    if isinstance(exc, HermesMissingKeyError):
        if profile:
            return (
                f"未配置 Hermes Agent profile `{profile}` 的 API Key：请在 "
                f"config.yaml 的 agent.agent_profiles.{profile} 填入该 profile 的 "
                "API_SERVER_KEY。"
            )
        return (
            "未配置 Hermes Agent API Key：请在 config.yaml 的 "
            "agent.agent_api_key 填入 API Key。"
        )
    if profile:
        return (
            f"Hermes 拒绝了 profile `{profile}` 的请求（{exc.message}）。"
            f"请确认 agent.agent_profiles.{profile} 与 Hermes 该 profile 的 "
            "API_SERVER_KEY 一致。"
        )
    return f"Hermes 鉴权失败：{exc.message}。请检查 agent.agent_api_key。"


async def _finish_error(
    matcher: type[Matcher],
    processing: ProcessingReply,
    event: MessageEvent,
    text: str,
) -> None:
    try:
        await matcher.send(reply_to_event(event, text))
    finally:
        await processing.retract()
    await matcher.finish()


async def _chat_locked(
    session_id: str,
    profile: str,
    content: str | list[dict[str, Any]],
) -> ChatResult:
    lock = _session_locks.setdefault(session_id, asyncio.Lock())
    try:
        await asyncio.wait_for(lock.acquire(), timeout=config.agent_lock_timeout)
    except TimeoutError as exc:
        msg = "该会话正在处理上一条消息，请稍后再试"
        raise HermesBusyError(msg) from exc
    try:
        return await hermes_client.chat(
            profile=profile,
            session_id=session_id,
            message=content,
        )
    finally:
        lock.release()


async def _create_session(profile: str, title: str) -> str:
    try:
        return await hermes_client.create_session(profile, title)
    except HermesError as exc:
        if exc.code != "invalid_title":
            raise
        logger.info("[hermes_agent] title conflict; creating session without title")
        return await hermes_client.create_session(profile, None)


async def _run_turn(
    matcher: type[Matcher],
    bot: Bot,
    event: MessageEvent,
    *,
    message: str,
    profile: str,
    session_id: str | None,
    reference: ReferenceContext,
    scope: str,
    processing: ProcessingReply,
) -> None:
    try:
        content = build_message_content(reference, message)
        title = _session_title(message, reference)

        if session_id is None:
            session_id = await _create_session(profile, title)
        try:
            result = await _chat_locked(session_id, profile, content)
        except HermesSessionNotFoundError:
            logger.info(
                "[hermes_agent] session {} disappeared; starting a new session",
                session_id,
            )
            session_id = await _create_session(profile, title)
            result = await _chat_locked(session_id, profile, content)

        session_id = result.session_id
        user_content = message or reference.render() or "[附件]"
        await agent_store.register_session(
            session_id=session_id,
            profile=profile,
            scope=scope,
            owner_id=int(event.user_id),
        )
        sent: list[str] = []
        for chunk in split_text(result.content, config.agent_outgoing_max_chars):
            response = await matcher.send(reply_to_event(event, chunk))
            message_id = _message_id(response)
            if message_id is not None:
                sent.append(message_id)
        full_content = result.content.strip() or _EMPTY_REPLY
        await agent_store.record_messages(
            bot_id=str(bot.self_id),
            session_id=session_id,
            profile=profile,
            scope=scope,
            messages=[
                (str(event.message_id), "user", user_content),
                *((message_id, "assistant", full_content) for message_id in sent),
            ],
        )
        logger.info(
            "[hermes_agent] profile={} session={} status={} chunks={}",
            _profile_label(profile),
            session_id,
            result.status,
            len(sent),
        )
    except HermesAuthError as exc:
        await _finish_error(
            matcher,
            processing,
            event,
            _auth_message(exc, profile),
        )
    except HermesTimeoutError:
        await _finish_error(
            matcher,
            processing,
            event,
            "Hermes 响应超时，请稍后重试。",
        )
    except HermesBusyError:
        await _finish_error(
            matcher,
            processing,
            event,
            "Hermes 当前繁忙或该会话正在处理，请稍后重试。",
        )
    except HermesError as exc:
        await _finish_error(matcher, processing, event, exc.message)
    except Exception:  # noqa: BLE001
        logger.exception("[hermes_agent] unexpected failure")
        await _finish_error(
            matcher,
            processing,
            event,
            "Hermes 请求失败，请稍后重试。",
        )

    await processing.retract()
    await matcher.finish()


@agent.handle()
async def handle_agent(
    bot: Bot,
    event: MessageEvent,
    arg: Message = CommandArg(),
) -> None:
    if not config.agent_api_key and not config.agent_profiles:
        await agent.finish(
            "Hermes Agent 未配置：请在 config.yaml 的 agent.agent_api_key "
            "填入 API Key。",
        )

    profile_arg, message = parse_agent_args(arg)
    if profile_arg is not None and not valid_profile(profile_arg):
        await agent.finish(
            "profile 名称无效：仅允许字母、数字、点、下划线和连字符。",
        )
    reply_id = get_replyid(event.original_message)
    if (
        not message
        and reply_id is None
        and not _has_attachment(event.original_message)
    ):
        await agent.finish(
            "用法：/agent [@profile] <消息>（可引用一条消息附加文本或文件）",
        )

    quota = consume_quota(event, "agent")
    if not quota.allowed:
        await agent.finish(quota.message or "请求过于频繁，请稍后再试")

    processing = await send_processing_reply(
        agent,
        bot,
        event,
        "Hermes 正在处理，请稍候…",
    )
    scope = event_scope(event)
    explicit_profile = profile_arg is not None
    requested_profile = normalize_profile(profile_arg or config.agent_default_profile)
    profile = requested_profile

    try:
        record = await lookup_session_reply(bot, event, agent_store, scope=scope)
        reference = (
            ReferenceContext()
            if record is not None
            else await collect_reference(
                bot,
                event,
                agent_store,
                config,
                scope=scope,
            )
        )
        reference = await _with_current_attachments(bot, event, reference)
        if reference.failed and not message and not reference.has_content:
            await _finish_error(
                agent,
                processing,
                event,
                "无法读取引用的消息（可能已撤回或过期）。",
            )
        if not message and not reference.has_content:
            await _finish_error(
                agent,
                processing,
                event,
                "请提供消息内容，或附带图片/文件。",
            )

        session_id = record.session_id if record is not None else None
        if record is not None:
            if explicit_profile and profile != record.profile:
                session_id = None
            elif not explicit_profile:
                profile = record.profile or requested_profile
        profile = normalize_profile(profile)
    except FinishedException:
        raise
    except Exception:  # noqa: BLE001
        logger.exception("[hermes_agent] failed to prepare reference")
        await _finish_error(
            agent,
            processing,
            event,
            "读取引用消息失败，请稍后重试。",
        )
        return

    await _run_turn(
        agent,
        bot,
        event,
        message=message,
        profile=profile,
        session_id=session_id,
        reference=reference,
        scope=scope,
        processing=processing,
    )


@agent_reply.handle()
async def handle_agent_reply(bot: Bot, event: MessageEvent) -> None:
    text = get_plaintext(event.original_message).strip()
    if (
        not (config.agent_api_key or config.agent_profiles)
        or get_replyid(event.original_message) is None
        or _is_command_text(text)
        or (not text and not _has_attachment(event.original_message))
    ):
        return

    scope = event_scope(event)
    try:
        record = await lookup_session_reply(bot, event, agent_store, scope=scope)
    except Exception:  # noqa: BLE001
        logger.exception("[hermes_agent] failed to look up replied message")
        return
    if record is None:
        return

    quota = consume_quota(event, "agent")
    if not quota.allowed:
        await agent_reply.send(
            reply_to_event(event, quota.message or "请求过于频繁，请稍后再试"),
        )
        return

    processing = await send_processing_reply(
        agent_reply,
        bot,
        event,
        "Hermes 正在处理，请稍候…",
    )
    try:
        reference = await collect_current_attachments(bot, event, config)
    except Exception:  # noqa: BLE001
        logger.exception("[hermes_agent] failed to collect current attachments")
        await processing.retract()
        await agent_reply.send(
            reply_to_event(event, "无法读取消息附件，请稍后重试。"),
        )
        return
    if not text and not reference.has_content:
        await processing.retract()
        return

    await _run_turn(
        agent_reply,
        bot,
        event,
        message=text,
        profile=normalize_profile(record.profile),
        session_id=record.session_id,
        reference=reference,
        scope=scope,
        processing=processing,
    )


__all__ = [
    "build_message_content",
    "config",
    "event_scope",
    "parse_agent_args",
    "split_text",
]
