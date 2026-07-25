from typing import Annotated

from pydantic import BaseModel, BeforeValidator, Field

_StrFromAny = Annotated[str, BeforeValidator(lambda v: str(v) if v is not None else v)]


class Config(BaseModel):
    """Plugin Config Here"""

    proxy: str | None = None
    sightengine_api_user: _StrFromAny = Field(description="Sightengine API user")
    sightengine_api_secret: _StrFromAny = Field(description="Sightengine API secret")
    c2pa_timeout: float = Field(default=15.0, ge=1.0, description="C2PA 图片下载超时秒")
    c2pa_max_file_size: int = Field(
        default=8 * 1024 * 1024,
        ge=1,
        description="C2PA 图片最大字节数",
    )
    c2pa_trust_list_refresh: int = Field(
        default=24 * 60 * 60,
        ge=60,
        description="C2PA 官方信任列表刷新间隔秒",
    )
