from pydantic import BaseModel, Field


class Config(BaseModel):
    """Plugin Config Here"""

    proxy: str | None = None
    sightengine_api_user: str = Field(description="Sightengine API user")
    sightengine_api_secret: str = Field(description="Sightengine API secret")
