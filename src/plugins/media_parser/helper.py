from collections.abc import Awaitable, Callable, Sequence
from functools import wraps
from pathlib import Path
from typing import Any

from nonebot import logger
from nonebot.matcher import current_bot, current_event
from nonebot.exception import FinishedException
from nonebot_plugin_alconna import uniseg
from nonebot_plugin_alconna.uniseg import (
    CustomNode,
    File,
    Image,
    Reference,
    Segment,
    Text,
    UniMessage,
    Video,
    Voice,
)

from .config import pconfig
from .exception import TipException

ForwardNodeInner = str | Segment | UniMessage
"""转发消息节点内部允许的类型"""


class UniHelper:
    @classmethod
    def reply_to_current_event(cls, message: UniMessage[Any] | str) -> UniMessage[Any]:
        """Build a message that quotes the event currently being handled."""
        message_id = uniseg.get_message_id(current_event.get())
        return UniMessage.reply(str(message_id)) + message

    @staticmethod
    def construct_forward_message(
        segments: Sequence[ForwardNodeInner],
        user_id: str | None = None,
    ) -> Reference:
        """构造转发消息"""
        if user_id is None:
            user_id = current_bot.get().self_id

        nodes: list[CustomNode] = []
        for seg in segments:
            if isinstance(seg, str):
                content = UniMessage([Text(seg)])
            elif isinstance(seg, Segment):
                content = UniMessage([seg])
            else:
                content = seg
            node = CustomNode(uid=user_id, name=pconfig.nickname, content=content)
            nodes.append(node)

        return Reference(nodes=nodes)

    @staticmethod
    def img_seg(
        file: Path | bytes,
    ) -> Image:
        """图片 Seg"""
        if isinstance(file, bytes):
            return Image(raw=file)

        if pconfig.use_base64:
            return Image(raw=file.read_bytes())
        else:
            return Image(path=file)

    @staticmethod
    def record_seg(audio_path: Path) -> Voice:
        """语音 Seg"""
        if pconfig.use_base64:
            return Voice(raw=audio_path.read_bytes())
        else:
            return Voice(path=audio_path)

    @classmethod
    def video_seg(
        cls,
        video_path: Path,
        thumbnail: Path | None = None,
    ) -> Video | File | Text:
        """视频 Seg"""
        # 检测文件大小
        file_size_byte_count = int(video_path.stat().st_size)
        if file_size_byte_count == 0:
            return Text("视频为空文件")
        elif file_size_byte_count > 100 * 1024 * 1024:
            # 转为文件 Seg
            return cls.file_seg(video_path, display_name=video_path.name)
        else:
            if pconfig.use_base64:
                video = Video(raw=video_path.read_bytes())
                if thumbnail and thumbnail.stat().st_size > 0:
                    video.thumbnail = cls.img_seg(thumbnail.read_bytes())
                return video
            else:
                video = Video(path=video_path)
                if thumbnail and thumbnail.stat().st_size > 0:
                    video.thumbnail = cls.img_seg(thumbnail)
                return video

    @staticmethod
    def file_seg(
        file: Path,
        display_name: str | None = None,
    ) -> File:
        """文件 Seg"""
        if not display_name:
            display_name = file.name

        if pconfig.use_base64:
            return File(raw=file.read_bytes(), name=display_name)
        else:
            return File(path=file, name=display_name)

    @classmethod
    def with_processing_reply(cls, func: Callable[..., Awaitable[Any]]):
        """Reply with a temporary processing message and retract it after handling."""

        @wraps(func)
        async def wrapper(*args, **kwargs):
            processing = await cls.reply_to_current_event("正在解析，请稍候…").send()

            try:
                return await func(*args, **kwargs)
            except TipException as e:
                await cls.reply_to_current_event(e.message).send()
                return None
            except FinishedException:
                raise
            except Exception:
                logger.exception("media parser handling failed")
                await cls.reply_to_current_event("解析失败，请稍后重试").send()
                return None
            finally:
                try:
                    await processing.recall()
                except Exception:  # noqa: BLE001
                    logger.exception("failed to retract parser processing reply")

        return wrapper
