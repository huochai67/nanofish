from pydantic import BaseModel


class Config(BaseModel):
    """Plugin Config Here"""

    app_api_base: str
