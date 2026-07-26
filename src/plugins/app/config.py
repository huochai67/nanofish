from pathlib import Path

from pydantic import BaseModel


class Config(BaseModel):
    """Plugin Config Here"""

    app_api_base: str
    app_viewport_width: int = 720
    app_viewport_height: int = 768
    app_page_timeout_ms: int = 30000
    app_debug_frontend_payload: bool = False
    app_debug_payload_dir: Path = Path(".cache/app-debug")
