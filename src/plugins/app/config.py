from pydantic import BaseModel


class Config(BaseModel):
    """Plugin Config Here"""

    app_api_base: str
    app_viewport_width: int = 1366
    app_viewport_height: int = 768
    app_page_timeout_ms: int = 30000
