from typing import Annotated

from pydantic import BaseModel, BeforeValidator, Field

_StrFromAny = Annotated[str, BeforeValidator(lambda v: str(v) if v is not None else v)]


class Config(BaseModel):
    """Plugin Config Here"""

    proxy: str | None = None
    sightengine_api_user: _StrFromAny = Field(description="Sightengine API user")
    sightengine_api_secret: _StrFromAny = Field(description="Sightengine API secret")
