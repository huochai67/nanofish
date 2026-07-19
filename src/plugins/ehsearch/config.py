from typing import Annotated

from pydantic import BaseModel, BeforeValidator, Field

# .env numeric-looking values (e.g. ipb_member_id) parse as int without quotes
_StrFromAny = Annotated[str, BeforeValidator(lambda v: str(v) if v is not None else v)]


class Config(BaseModel):
    """Plugin Config Here"""

    proxy: str | None = None
    eh_ipb_member_id: _StrFromAny = Field(description="exhentai ipb_member_id cookie")
    eh_ipb_pass_hash: _StrFromAny = Field(description="exhentai ipb_pass_hash cookie")
    eh_sk: _StrFromAny = Field(default="", description="exhentai sk cookie")
    eh_igneous: _StrFromAny = Field(description="exhentai igneous cookie")
