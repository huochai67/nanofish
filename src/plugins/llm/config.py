from pydantic import BaseModel


class Config(BaseModel):
    """Plugin Config Here"""

    model: str
    openai_api_key: str
    openai_api_base: str
