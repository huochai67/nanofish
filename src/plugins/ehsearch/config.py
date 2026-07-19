from pydantic import BaseModel, Field


class Config(BaseModel):
    """Plugin Config Here"""

    proxy: str | None = None
    eh_db: str = Field(description="E-Hentai 标签翻译数据库路径")
    eh_ipb_member_id: str = Field(description="exhentai ipb_member_id cookie")
    eh_ipb_pass_hash: str = Field(description="exhentai ipb_pass_hash cookie")
    eh_sk: str = Field(description="exhentai sk cookie")
    eh_igneous: str = Field(description="exhentai igneous cookie")
