import asyncio
import base64
import io
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock

from PIL import Image

from src.plugins.imgsearch import (
    _SOUTUBOT_USER_AGENT,
    ImageSearchClient,
    _preview_data_url,
    _soutubot_api_key,
)

if TYPE_CHECKING:
    from src.plugins.utils import CloudScraperClient


def test_soutubot_uses_flaresolverr_session_for_initialization() -> None:
    client = ImageSearchClient()
    solver = SimpleNamespace(
        get=AsyncMock(return_value=SimpleNamespace(text="window.config = {m: 123,};")),
        user_agent="FlareSolverr test browser",
    )
    client._soutubot_client = cast("CloudScraperClient", solver)

    headers = asyncio.run(client._soutubot_headers())

    solver.get.assert_awaited_once_with(
        "https://soutubot.moe/",
        timeout=30.0,
    )
    assert headers["user-agent"] == solver.user_agent
    assert headers["x-api-key"] == _soutubot_api_key(123, solver.user_agent)


def test_soutubot_uses_fallback_user_agent_without_flaresolverr() -> None:
    client = ImageSearchClient()
    direct_client = SimpleNamespace(
        get=AsyncMock(return_value=SimpleNamespace(text="window.config = {m: 123,};")),
        user_agent=None,
    )
    client._soutubot_client = cast("CloudScraperClient", direct_client)

    headers = asyncio.run(client._soutubot_headers())

    assert headers["user-agent"] == _SOUTUBOT_USER_AGENT
    assert headers["x-api-key"] == _soutubot_api_key(123, _SOUTUBOT_USER_AGENT)


def test_imgsearch_preview_is_resized_jpeg() -> None:
    source = io.BytesIO()
    Image.new("RGBA", (1600, 900), (20, 40, 60, 128)).save(source, format="PNG")

    preview = _preview_data_url(source.getvalue())

    assert preview.startswith("data:image/jpeg;base64,")
    encoded = preview.split(",", maxsplit=1)[1]
    with Image.open(io.BytesIO(base64.b64decode(encoded))) as image:
        assert image.format == "JPEG"
        assert image.mode == "RGB"
        assert image.size == (384, 216)
