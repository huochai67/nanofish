"""Hermes Agent plugin configuration."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class Config(BaseModel):
    """Configuration for the `/agent` command."""

    agent_endpoint: str = Field(
        default="http://hermes-agent:8642",
        description="Hermes Agent API 根地址",
    )
    agent_api_key: str = Field(
        default="",
        description="默认 profile 的 Hermes API Key",
    )
    agent_default_profile: str = Field(
        default="",
        description="未指定 @profile 时使用的 profile；空或 default 表示默认 profile",
    )
    agent_profiles: dict[str, str] = Field(
        default_factory=dict,
        description="profile 名称到独立 API Key 的映射；未配置时回退到 agent_api_key",
    )
    agent_timeout: float = Field(
        default=300.0,
        gt=0,
        description="Hermes 单轮请求超时（秒）",
    )
    agent_lock_timeout: float = Field(
        default=30.0,
        gt=0,
        description="同一会话等待上一轮结束的最长时间（秒）",
    )
    agent_outgoing_max_chars: int = Field(
        default=1800,
        ge=100,
        description="单条 QQ 消息的最大字符数，超出时分段发送",
    )
    agent_reference_max_chars: int = Field(
        default=12_000,
        ge=100,
        description=(
            "引用文本与文件文本注入 prompt 的最大字符数；"
            "文本文件无法完整放入时改为提供下载地址"
        ),
    )
    agent_file_max_bytes: int = Field(
        default=8 * 1024 * 1024,
        ge=1,
        description="引用文件下载上限（字节）",
    )
    agent_image_max_bytes: int = Field(
        default=4 * 1024 * 1024,
        ge=1,
        description="引用图片内联为 data URL 的上限（字节）",
    )
    agent_max_attachments: int = Field(
        default=4,
        ge=0,
        description="单次引用最多处理的内联附件数量",
    )
    agent_upload_dir: str = Field(
        default="",
        description="可选：二进制附件的本地暂存目录",
    )
    agent_remote_upload_dir: str = Field(
        default="",
        description="可选：暂存目录在 Hermes 容器内的可见路径",
    )
    agent_db_path: str = Field(
        default="",
        description="可选：消息与会话映射数据库路径；空表示使用 localstore",
    )

    @field_validator("agent_endpoint")
    @classmethod
    def _strip_endpoint(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if not value:
            msg = "agent_endpoint must not be empty"
            raise ValueError(msg)
        return value

    @field_validator(
        "agent_default_profile",
        "agent_upload_dir",
        "agent_remote_upload_dir",
    )
    @classmethod
    def _strip_optional(cls, value: str) -> str:
        return value.strip()

    @field_validator("agent_profiles")
    @classmethod
    def _strip_profiles(cls, value: dict[str, str]) -> dict[str, str]:
        return {key.strip(): secret.strip() for key, secret in value.items()}
