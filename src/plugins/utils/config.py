from pydantic import BaseModel, Field


class Config(BaseModel):
    """Plugin Config Here"""

    http_proxy: str | None = Field(
        default=None,
        description="全局 HTTP 代理，插件未指定 proxy 时使用",
    )
    http_timeout: float = Field(
        default=30.0,
        description="全局 HTTP 超时（秒）",
        gt=0,
    )
