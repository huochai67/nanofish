from pydantic import BaseModel, Field


class Config(BaseModel):
    """Reverse image search plugin configuration."""

    proxy: str | None = None
    imgsearch_timeout: float = Field(default=30.0, gt=0)
    imgsearch_max_file_size: int = Field(default=8 * 1024 * 1024, gt=0)
    imgsearch_result_limit: int = Field(default=5, ge=1, le=10)
    imgsearch_saucenao_api_key: str = ""
    imgsearch_soutubot_api_key: str = ""
    imgsearch_soutubot_factor: float = Field(default=1.2, gt=0)
