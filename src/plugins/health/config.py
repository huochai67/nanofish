from pydantic import BaseModel, Field


class Config(BaseModel):
    """Plugin Config Here"""

    health_http_timeout: float = Field(
        default=5.0,
        description="前端 HTTP 探测超时（秒）",
        gt=0,
    )
