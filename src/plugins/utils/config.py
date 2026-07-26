from pydantic import AliasChoices, BaseModel, Field


class Config(BaseModel):
    """Plugin Config Here"""

    proxy: str | None = Field(
        default=None,
        validation_alias=AliasChoices("PROXY", "HTTP_PROXY", "HTTPS_PROXY"),
        description="全局 HTTP 代理（PROXY；兼容 HTTP_PROXY / HTTPS_PROXY）",
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
    flaresolverr_url: str = Field(
        default="http://flaresolverr:8191/v1",
        description="FlareSolverr API 地址（留空时禁用）",
    )
