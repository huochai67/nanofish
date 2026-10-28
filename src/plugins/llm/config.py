from typing import Annotated, Literal, Self

from pydantic import BaseModel, BeforeValidator, Field, model_validator


def _empty_str_to_none(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return value


OptionalStr = Annotated[str | None, BeforeValidator(_empty_str_to_none)]


ImageCapability = Literal["text_to_image", "image_to_image"]
DEFAULT_IMAGE_CAPABILITIES: tuple[ImageCapability, ...] = (
    "text_to_image",
    "image_to_image",
)


class ImageModelConfig(BaseModel):
    model: str
    api_key: str
    api_base: str
    capabilities: list[ImageCapability] = Field(
        default_factory=lambda: list(DEFAULT_IMAGE_CAPABILITIES),
    )
    size: OptionalStr = None
    response_format: OptionalStr = "b64_json"
    timeout: float = Field(default=120.0, ge=1.0)

    @model_validator(mode="after")
    def _validate_capabilities(self) -> Self:
        if not self.capabilities:
            msg = "生图档案 capabilities 不能为空"
            raise ValueError(msg)
        self.capabilities = list(dict.fromkeys(self.capabilities))
        return self


class Config(BaseModel):
    """Plugin Config Here"""

    # Image generation profiles (OpenAI-compatible /v1/images/*)
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
        for alias in self.image_models:
            if (
                not alias
                or any(char.isspace() for char in alias)
                or alias.startswith("@")
            ):
                msg = f"非法生图模型别名: {alias!r}"
                raise ValueError(msg)
        return self
