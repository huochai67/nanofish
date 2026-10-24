"""Collect quoted QQ messages, images, and files for a Hermes prompt."""

from __future__ import annotations

import asyncio
import base64
import mimetypes
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
from nonebot import logger
from nonebot.adapters.onebot.v11 import GroupMessageEvent, Message, MessageSegment

from ..utils import get_replyid, http_client
from .client import normalize_profile

if TYPE_CHECKING:
    from nonebot.adapters.onebot.v11 import Bot, MessageEvent

    from .config import Config
    from .store import AgentStore, MessageRecord

_TEXT_EXTENSIONS = {
    ".cfg",
    ".conf",
    ".css",
    ".csv",
    ".env",
    ".go",
    ".h",
    ".html",
    ".ini",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".log",
    ".lua",
    ".md",
    ".mjs",
    ".php",
    ".py",
    ".rb",
    ".rs",
    ".sh",
    ".sql",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
_DEFAULT_FILENAME = {
    "image": "image.jpg",
    "file": "attachment",
    "record": "record.amr",
    "video": "video.mp4",
}
_MAX_FILENAME_CHARS = 120
_KIB = 1024
_MIB = _KIB * _KIB


@dataclass(frozen=True, slots=True)
class ImageAttachment:
    filename: str
    data_url: str


@dataclass(slots=True)
class ReferenceContext:
    """Quoted context plus attachments from the user's current message."""

    text_parts: list[str] = field(default_factory=list)
    images: list[ImageAttachment] = field(default_factory=list)
    current_text_parts: list[str] = field(default_factory=list)
    current_images: list[ImageAttachment] = field(default_factory=list)
    session_id: str | None = None
    profile: str = ""
    failed: bool = False

    @property
    def has_content(self) -> bool:
        return bool(
            self.text_parts
            or self.images
            or self.current_text_parts
            or self.current_images
        )

    @property
    def all_images(self) -> list[ImageAttachment]:
        return [*self.images, *self.current_images]

    def render(self) -> str:
        sections: list[str] = []
        if self.text_parts or self.images:
            lines = ["<reference>", *self.text_parts]
            lines.extend(f"[引用图片: {image.filename}]" for image in self.images)
            lines.append("</reference>")
            sections.append("\n".join(lines))
        if self.current_text_parts or self.current_images:
            lines = [*self.current_text_parts]
            lines.extend(f"[图片: {image.filename}]" for image in self.current_images)
            sections.append("\n".join(lines))
        return "\n\n".join(sections)


class _ReferenceBuilder:
    def __init__(self, config: Config) -> None:
        self.context = ReferenceContext()
        self._config = config
        self._chars = 0
        self._attachments = 0

    def add_text(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        remaining = self._config.agent_reference_max_chars - self._chars
        if remaining <= 0:
            return
        if len(text) > remaining:
            text = f"{text[:remaining]}\n…（已截断）"
        self.context.text_parts.append(text)
        self._chars += len(text)

    def add_note(self, note: str) -> None:
        self.add_text(note)

    @property
    def remaining_chars(self) -> int:
        return self._config.agent_reference_max_chars - self._chars

    def add_forced_note(self, note: str) -> None:
        """Add a URL/pointer even when the text budget is already exhausted."""
        text = note.strip()
        if not text:
            return
        self.context.text_parts.append(text)
        self._chars += len(text)

    def add_file_text(self, filename: str, text: str) -> None:
        text = text.strip()
        if not text:
            return
        self.add_text(f"[引用文件: {filename}]\n{text}\n[/引用文件]")

    def add_image(self, filename: str, data_url: str) -> None:
        if not self.can_add_attachment():
            self.add_note(f"[图片: {filename}]（超过附件数量上限）")
            return
        self.context.images.append(ImageAttachment(filename, data_url))
        self._attachments += 1

    def can_add_attachment(self) -> bool:
        return self._attachments < self._config.agent_max_attachments


async def collect_reference(
    bot: Bot,
    event: MessageEvent,
    store: AgentStore,
    config: Config,
    *,
    scope: str,
) -> ReferenceContext:
    """Resolve the replied-to message, session relation, and attachments."""
    reply_id = get_replyid(event.original_message)
    if reply_id is None:
        return ReferenceContext()

    builder = _ReferenceBuilder(config)
    record = await store.lookup_message(
        bot_id=str(bot.self_id),
        message_id=str(reply_id),
    )
    if record is not None:
        if record.role == "assistant" and record.scope == scope:
            builder.context.session_id = record.session_id
            builder.context.profile = normalize_profile(record.profile)
        if record.content.strip():
            builder.add_text(record.content)
            return builder.context

    try:
        raw = await bot.call_api("get_msg", message_id=reply_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[hermes_agent] failed to fetch replied message {}: {}",
            reply_id,
            type(exc).__name__,
        )
        builder.context.failed = True
        return builder.context
    if not isinstance(raw, dict):
        builder.context.failed = True
        return builder.context

    segments = _as_message(raw.get("message"))
    if not segments:
        builder.context.failed = True
        return builder.context
    await _collect_segments(
        bot,
        event,
        config,
        builder,
        segments,
    )
    return builder.context


async def lookup_session_reply(
    bot: Bot,
    event: MessageEvent,
    store: AgentStore,
    *,
    scope: str,
) -> MessageRecord | None:
    """Return the recorded assistant message quoted by ``event``, if any."""
    reply_id = get_replyid(event.original_message)
    if reply_id is None:
        return None
    record = await store.lookup_message(
        bot_id=str(bot.self_id),
        message_id=str(reply_id),
    )
    if record is None or record.role != "assistant" or record.scope != scope:
        return None
    return record


async def collect_current_attachments(
    bot: Bot,
    event: MessageEvent,
    config: Config,
) -> ReferenceContext:
    """Collect attachments sent in the current message, ignoring its text."""
    builder = _ReferenceBuilder(config)
    for segment in event.original_message:
        if segment.type == "image":
            await _collect_image(bot, config, builder, segment)
        elif segment.type in {"file", "record", "video"}:
            await _collect_file(bot, event, config, builder, segment)
        elif segment.type == "forward":
            await _collect_forward(bot, event, config, builder, segment, 0)
    context = builder.context
    context.current_text_parts = context.text_parts
    context.current_images = context.images
    context.text_parts = []
    context.images = []
    return context


async def _collect_segments(
    bot: Bot,
    event: MessageEvent,
    config: Config,
    builder: _ReferenceBuilder,
    segments: Message,
    *,
    depth: int = 0,
) -> None:
    for segment in segments:
        segment_type = segment.type
        if segment_type == "text":
            builder.add_text(str(segment.data.get("text") or ""))
        elif segment_type == "at":
            name = segment.data.get("name") or segment.data.get("qq") or ""
            if name:
                builder.add_text(f"@{name}")
        elif segment_type == "image":
            await _collect_image(bot, config, builder, segment)
        elif segment_type in {"file", "record", "video"}:
            await _collect_file(bot, event, config, builder, segment)
        elif segment_type == "forward" and depth == 0:
            await _collect_forward(bot, event, config, builder, segment, depth)
        elif segment_type in {"face", "mface"}:
            builder.add_note("[表情]")


async def _collect_forward(
    bot: Bot,
    event: MessageEvent,
    config: Config,
    builder: _ReferenceBuilder,
    segment: MessageSegment,
    depth: int,
) -> None:
    forward_id = str(segment.data.get("id") or "").strip()
    if not forward_id:
        return
    try:
        raw = await bot.call_api("get_forward_msg", id=forward_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[hermes_agent] failed to fetch forward {}: {}",
            forward_id,
            type(exc).__name__,
        )
        builder.add_note("[合并转发消息无法读取]")
        return
    nodes = (
        (raw.get("message") or raw.get("messages")) if isinstance(raw, dict) else None
    )
    if not isinstance(nodes, list):
        builder.add_note("[合并转发消息为空]")
        return
    for node in nodes:
        if not isinstance(node, dict):
            continue
        sender = node.get("sender")
        nickname = ""
        if isinstance(sender, dict):
            nickname = str(sender.get("card") or sender.get("nickname") or "").strip()
        if nickname:
            builder.add_text(f"{nickname}:")
        await _collect_segments(
            bot,
            event,
            config,
            builder,
            _as_message(node.get("message")),
            depth=depth + 1,
        )


async def _collect_image(
    bot: Bot,
    config: Config,
    builder: _ReferenceBuilder,
    segment: MessageSegment,
) -> None:
    filename = _segment_filename(segment, "image")
    if not builder.can_add_attachment():
        builder.add_note(f"[图片: {filename}]（超过附件数量上限）")
        return
    ref = _existing_ref(segment.data)
    if not ref:
        ref = await _resolve_image_ref(bot, segment.data)
    if not ref:
        builder.add_note(f"[图片: {filename}]（无法获取下载地址）")
        return
    try:
        data, content_type = await _load_ref(ref, config.agent_image_max_bytes)
    except (ValueError, httpx.HTTPError, OSError) as exc:
        logger.warning(
            "[hermes_agent] failed to download image {}: {}",
            filename,
            type(exc).__name__,
        )
        builder.add_note(f"[图片: {filename}]（下载失败）")
        return
    mime = _image_mime(data, content_type)
    if not mime:
        builder.add_note(f"[图片: {filename}]（不是可识别的图片）")
        return
    encoded = base64.b64encode(data).decode("ascii")
    builder.add_image(filename, f"data:{mime};base64,{encoded}")


async def _collect_file(
    bot: Bot,
    event: MessageEvent,
    config: Config,
    builder: _ReferenceBuilder,
    segment: MessageSegment,
) -> None:
    filename = _segment_filename(segment, segment.type)
    data = segment.data
    url = _existing_ref(data)
    if not url:
        url = await _resolve_file_url(bot, event, data)
    declared_size = _int_or_none(data.get("file_size"))
    mime = mimetypes.guess_type(filename)[0] or ""

    if not url:
        builder.add_note(
            f"[文件: {filename}]（无下载地址，{_size_text(declared_size)}）",
        )
        return
    try:
        raw, content_type = await _load_ref(url, config.agent_file_max_bytes)
    except (ValueError, httpx.HTTPError, OSError) as exc:
        logger.warning(
            "[hermes_agent] failed to download file {}: {}",
            filename,
            type(exc).__name__,
        )
        builder.add_note(
            f"[文件: {filename}]（下载失败，{_size_text(declared_size)}）\n{url}",
        )
        return

    mime = mime or _content_type(content_type)
    if image_mime := _image_mime(raw, content_type):
        if builder.can_add_attachment():
            encoded = base64.b64encode(raw).decode("ascii")
            builder.add_image(filename, f"data:{image_mime};base64,{encoded}")
            return
        builder.add_note(f"[图片: {filename}]（超过附件数量上限）")
        return

    if _is_text_like(filename, mime, raw):
        text = _decode_text(raw).strip()
        if text:
            wrapped = f"[引用文件: {filename}]\n{text}\n[/引用文件]"
            if len(wrapped) <= builder.remaining_chars:
                builder.add_file_text(filename, text)
                builder.add_note(f"[文件来源: {url}]")
            else:
                builder.add_forced_note(
                    f"[文件: {filename}]（文本过长，未内联；"
                    f"{_size_text(len(raw))}）\n下载地址: {url}",
                )
            return

    note = f"[文件: {filename}]（{mime or '未知类型'}，{_size_text(len(raw))}）"
    note += f"\n下载地址: {url}"
    staged = await _stage_file(config, filename, raw)
    if staged:
        note += f"\n本地路径: {staged}"
    builder.add_note(note)


async def _stage_file(config: Config, filename: str, data: bytes) -> str:
    if not (config.agent_upload_dir and config.agent_remote_upload_dir):
        return ""
    try:
        stored_name = await asyncio.to_thread(
            _write_staged,
            Path(config.agent_upload_dir),
            filename,
            data,
        )
    except OSError as exc:
        logger.warning(
            "[hermes_agent] failed to stage {}: {}",
            filename,
            type(exc).__name__,
        )
        return ""
    return f"{config.agent_remote_upload_dir.rstrip('/')}/{stored_name}"


def _write_staged(directory: Path, filename: str, data: bytes) -> str:
    directory.mkdir(parents=True, exist_ok=True)
    safe = _safe_name(filename)
    target = directory / f"{int(time.time())}-{uuid.uuid4().hex[:8]}-{safe}"
    target.write_bytes(data)
    return target.name


async def _resolve_image_ref(bot: Bot, data: dict[str, Any]) -> str:
    file_value = str(data.get("file") or data.get("file_id") or "").strip()
    if not file_value:
        return ""
    try:
        result = await bot.call_api("get_image", file=file_value)
    except Exception as exc:  # noqa: BLE001
        logger.debug("[hermes_agent] get_image failed: {}", type(exc).__name__)
        return ""
    return _existing_ref(result) if isinstance(result, dict) else ""


async def _resolve_file_url(
    bot: Bot,
    event: MessageEvent,
    data: dict[str, Any],
) -> str:
    file_id = str(data.get("file_id") or data.get("file") or "").strip()
    if not file_id:
        return ""
    url = await _file_api_url(bot, file_id)
    if url:
        return url
    if isinstance(event, GroupMessageEvent):
        url = await _group_file_url(bot, event, data, file_id)
        if url:
            return url
    return await _private_file_url(bot, file_id)


async def _file_api_url(bot: Bot, file_id: str) -> str:
    for kwargs in ({"file_id": file_id}, {"file": file_id}):
        try:
            result = await bot.call_api("get_file", **kwargs)
        except Exception as exc:  # noqa: BLE001
            logger.debug("[hermes_agent] get_file failed: {}", type(exc).__name__)
            continue
        url = _existing_ref(result) if isinstance(result, dict) else ""
        if url:
            return url
    return ""


async def _group_file_url(
    bot: Bot,
    event: GroupMessageEvent,
    data: dict[str, Any],
    file_id: str,
) -> str:
    busid = _int_or_none(data.get("busid"))
    if busid is None:
        return ""
    try:
        result = await bot.call_api(
            "get_group_file_url",
            group_id=int(event.group_id),
            file_id=file_id,
            busid=busid,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug(
            "[hermes_agent] get_group_file_url failed: {}",
            type(exc).__name__,
        )
        return ""
    return _existing_ref(result) if isinstance(result, dict) else ""


async def _private_file_url(bot: Bot, file_id: str) -> str:
    try:
        result = await bot.call_api("get_private_file_url", file_id=file_id)
    except Exception as exc:  # noqa: BLE001
        logger.debug(
            "[hermes_agent] get_private_file_url failed: {}",
            type(exc).__name__,
        )
        return ""
    return _existing_ref(result) if isinstance(result, dict) else ""


async def _load_ref(ref: str, max_bytes: int) -> tuple[bytes, str]:
    if ref.startswith(("http://", "https://")):
        return await _download(ref, max_bytes)
    if ref.startswith("base64://"):
        data = base64.b64decode(ref[9:])
        content_type = ""
    elif ref.startswith("data:"):
        header, _, payload = ref.partition(",")
        meta = header[5:].split(";")
        content_type = meta[0] if meta else ""
        data = (
            base64.b64decode(payload) if "base64" in meta else payload.encode("utf-8")
        )
    else:
        msg = "unsupported attachment reference"
        raise ValueError(msg)
    if len(data) > max_bytes:
        msg = "attachment exceeds the inline size limit"
        raise ValueError(msg)
    return data, content_type


async def _download(url: str, max_bytes: int) -> tuple[bytes, str]:
    async with (
        http_client(url=url, timeout=30.0) as client,
        client.stream("GET", url) as response,
    ):
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        declared = _int_or_none(response.headers.get("content-length"))
        if declared is not None and declared > max_bytes:
            msg = "attachment exceeds the download size limit"
            raise ValueError(msg)
        buffer = bytearray()
        async for chunk in response.aiter_bytes():
            buffer.extend(chunk)
            if len(buffer) > max_bytes:
                msg = "attachment exceeds the download size limit"
                raise ValueError(msg)
        return bytes(buffer), content_type


def _existing_ref(data: dict[str, Any]) -> str:
    for key in ("url", "download_url", "file_url"):
        value = str(data.get(key) or "").strip()
        if value.startswith(("http://", "https://", "data:", "base64://")):
            return value
    value = str(data.get("file") or "").strip()
    if value.startswith(("http://", "https://", "data:", "base64://")):
        return value
    return ""


def _segment_filename(segment: MessageSegment, default_prefix: str) -> str:
    for key in ("file_name", "name", "file"):
        value = segment.data.get(key)
        if isinstance(value, str) and value.strip():
            name = _safe_name(value)
            if Path(name).suffix:
                return name
    return _DEFAULT_FILENAME.get(default_prefix, "attachment")


def _safe_name(name: str) -> str:
    name = Path(name.replace("\\", "/")).name
    name = re.sub(r"[\x00-\x1f\x7f]+", "", name).strip()
    if name in {"", ".", ".."}:
        return "attachment"
    return name[:_MAX_FILENAME_CHARS]


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def _size_text(size: int | None) -> str:
    if size is None:
        return "大小未知"
    if size < _KIB:
        return f"{size} 字节"
    if size < _MIB:
        return f"{size / _KIB:.1f} KiB"
    return f"{size / _MIB:.1f} MiB"


def _content_type(raw: str) -> str:
    return raw.partition(";")[0].strip().lower()


def _image_mime(data: bytes, content_type: str) -> str:
    mime = _content_type(content_type)
    if mime.startswith("image/"):
        return mime
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    for signature, detected in (
        (b"\x89PNG\r\n\x1a\n", "image/png"),
        (b"\xff\xd8\xff", "image/jpeg"),
        (b"GIF87a", "image/gif"),
        (b"GIF89a", "image/gif"),
        (b"BM", "image/bmp"),
    ):
        if data.startswith(signature):
            return detected
    return ""


def _is_text_like(filename: str, mime: str, data: bytes) -> bool:
    if mime.startswith("text/"):
        return True
    if Path(filename).suffix.lower() in _TEXT_EXTENSIONS:
        return True
    return _looks_like_text(data)


def _looks_like_text(data: bytes) -> bool:
    if not data or b"\x00" in data[:4096]:
        return False
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        try:
            data.decode("gb18030")
        except UnicodeDecodeError:
            return False
    return True


def _decode_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _as_message(raw: object) -> Message:
    if isinstance(raw, Message):
        return raw
    if isinstance(raw, str):
        return Message(raw)
    if isinstance(raw, list):
        segments: list[MessageSegment] = []
        for item in raw:
            if isinstance(item, MessageSegment):
                segments.append(item)
            elif isinstance(item, dict) and isinstance(item.get("type"), str):
                data = item.get("data")
                segments.append(
                    MessageSegment(
                        type=item["type"],
                        data=data if isinstance(data, dict) else {},
                    ),
                )
        return Message(segments)
    return Message()


__all__ = [
    "ImageAttachment",
    "ReferenceContext",
    "collect_current_attachments",
    "collect_reference",
    "lookup_session_reply",
]
