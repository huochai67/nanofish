from pydantic import BaseModel, Field


class Config(BaseModel):
    """Plugin Config Here"""

    proxy: str | None = Field(
        default=None,
        description="全局 HTTP 代理（PROXY）；优先于 HTTP_PROXY",
    )
    http_proxy: str | None = Field(
        default=None,
        description="全局 HTTP 代理（HTTP_PROXY，兼容旧配置）",
    )
    http_timeout: float = Field(
        default=30.0,
        description="全局 HTTP 超时（秒）",
        gt=0,
    )
    http_trace: bool = Field(
        default=False,
        description="输出脱敏的 HTTP 请求与响应追踪日志",
    )
