from typing import Annotated, Literal, Self

from pydantic import BaseModel, BeforeValidator, Field, model_validator


def _empty_str_to_none(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return value


OptionalStr = Annotated[str | None, BeforeValidator(_empty_str_to_none)]

ImageBackend = Literal["openai", "grok", "gemini"]


def _validate_backend_fields(alias: str, profile: "ImageModelConfig") -> None:
    """Reject fields that a backend would silently ignore."""
    if profile.backend == "openai" and (profile.aspect_ratio or profile.resolution):
        msg = (
            f"生图档案 {alias!r}: openai 后端不支持 "
            "aspect_ratio 或 resolution"
        )
        raise ValueError(msg)
    if profile.backend == "grok":
        if profile.size:
            msg = f"生图档案 {alias!r}: grok 后端不支持 size"
            raise ValueError(msg)
        if profile.response_format not in (None, "b64_json", "url"):
            msg = (
                f"生图档案 {alias!r}: grok 后端 response_format "
                "仅支持 b64_json 或 url"
            )
            raise ValueError(msg)
    if profile.backend == "gemini":
        if profile.size:
            msg = f"生图档案 {alias!r}: gemini 后端不支持 size"
            raise ValueError(msg)
        if profile.response_format not in (None, "b64_json"):
            msg = (
                f"生图档案 {alias!r}: gemini 后端 response_format "
                "仅支持 b64_json"
            )
            raise ValueError(msg)


class ImageModelConfig(BaseModel):
    model: str
    api_key: str
    api_base: str
    backend: ImageBackend = "openai"
    size: OptionalStr = None
    response_format: OptionalStr = "b64_json"
    aspect_ratio: OptionalStr = None
    resolution: OptionalStr = None
    timeout: float = Field(default=120.0, ge=1.0)


class Config(BaseModel):
    """Plugin Config Here"""

    model: str
    openai_api_key: str
    openai_api_base: str

    # Image generation profiles: openai / grok / gemini native backends
    image_default_model: str
    image_models: dict[str, ImageModelConfig]

    @model_validator(mode="after")
    def _validate_image_models(self) -> Self:
        if not self.image_models:
            msg = "image_models 不能为空"
            raise ValueError(msg)
        if self.image_default_model not in self.image_models:
            msg = "image_default_model 必须是 image_models 中已配置的别名"
            raise ValueError(msg)
        for alias, profile in self.image_models.items():
            if (
                not alias
                or any(char.isspace() for char in alias)
                or alias.startswith("@")
            ):
                msg = f"非法生图模型别名: {alias!r}"
                raise ValueError(msg)
            _validate_backend_fields(alias, profile)
        return self
