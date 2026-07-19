from typing import Annotated

from pydantic import BaseModel, BeforeValidator, Field


def _empty_str_to_none(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return value


OptionalStr = Annotated[str | None, BeforeValidator(_empty_str_to_none)]


class Config(BaseModel):
    """Plugin Config Here"""

    model: str
    openai_api_key: str
    openai_api_base: str

    # Image generation (OpenAI-compatible /v1/images/*)
    image_model: str = Field(description="生图模型名，如 dall-e-3 / gpt-image-1")
    image_size: OptionalStr = Field(
        default=None,
        description="可选尺寸，如 1024x1024；空则不传",
    )
    image_response_format: OptionalStr = Field(
        default="b64_json",
        description="b64_json 或 url；空则不传",
    )
    image_timeout: float = Field(default=120.0, ge=1.0, description="生图请求超时秒")
