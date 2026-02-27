from pydantic import BaseModel


class Config(BaseModel):
    """Plugin Config Here"""

    proxy: str
    eh_db: str
