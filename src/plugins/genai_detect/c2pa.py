"""C2PA image download helpers for the genai plugin."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from time import monotonic
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from nonebot import logger

from ..utils import HttpRequestError, http_get
from .c2pa_validation import C2paResult, C2paStatus, inspect_embedded_c2pa

if TYPE_CHECKING:
    from .config import Config

_C2PA_TRUST_LIST_URL = (
    "https://raw.githubusercontent.com/c2pa-org/conformance-public/refs/heads/main/"
    "trust-list/C2PA-TRUST-LIST.pem"
)
_C2PA_TSA_TRUST_LIST_URL = (
    "https://raw.githubusercontent.com/c2pa-org/conformance-public/refs/heads/main/"
    "trust-list/C2PA-TSA-TRUST-LIST.pem"
)
_TRUST_LIST_RETRY_SECONDS = 60


@dataclass(slots=True)
class _TrustAnchorCache:
    anchors: str | None = None
    refresh_at: float = 0.0


_trust_anchor_cache = _TrustAnchorCache()
_trust_anchors_lock = asyncio.Lock()


def _is_http_url(url: str) -> bool:
    return urlsplit(url).scheme in {"http", "https"}


async def _official_trust_anchors(config: Config) -> str | None:
    now = monotonic()
    if now < _trust_anchor_cache.refresh_at:
        return _trust_anchor_cache.anchors

    async with _trust_anchors_lock:
        now = monotonic()
        if now < _trust_anchor_cache.refresh_at:
            return _trust_anchor_cache.anchors
        try:
            trust_list, tsa_trust_list = await asyncio.gather(
                http_get(
                    _C2PA_TRUST_LIST_URL,
                    proxy=config.proxy,
                    timeout=config.c2pa_timeout,
                ),
                http_get(
                    _C2PA_TSA_TRUST_LIST_URL,
                    proxy=config.proxy,
                    timeout=config.c2pa_timeout,
                ),
            )
            trust_anchors = f"{trust_list.text}\n{tsa_trust_list.text}"
        except HttpRequestError as exc:
            logger.warning("C2PA official trust list update failed: %s", exc)
            _trust_anchor_cache.refresh_at = now + _TRUST_LIST_RETRY_SECONDS
            return _trust_anchor_cache.anchors

        if "-----BEGIN CERTIFICATE-----" not in trust_anchors:
            logger.warning("C2PA official trust lists did not contain certificates")
            _trust_anchor_cache.refresh_at = now + _TRUST_LIST_RETRY_SECONDS
            return _trust_anchor_cache.anchors

        _trust_anchor_cache.anchors = trust_anchors
        _trust_anchor_cache.refresh_at = now + config.c2pa_trust_list_refresh
        return _trust_anchor_cache.anchors


async def inspect_image_url(url: str, config: Config) -> C2paResult:
    """Download one image and verify only its embedded C2PA manifest."""
    if not _is_http_url(url):
        return C2paResult(C2paStatus.DOWNLOAD_FAILED)
    try:
        response = await http_get(url, proxy=config.proxy, timeout=config.c2pa_timeout)
    except HttpRequestError as exc:
        logger.debug("C2PA image download failed: %s", exc.message)
        return C2paResult(C2paStatus.DOWNLOAD_FAILED)

    content_length = response.headers.get("content-length")
    try:
        if content_length and int(content_length) > config.c2pa_max_file_size:
            return C2paResult(C2paStatus.TOO_LARGE)
    except ValueError:
        logger.debug("C2PA image returned invalid content-length: %r", content_length)

    image = response.content
    if len(image) > config.c2pa_max_file_size:
        return C2paResult(C2paStatus.TOO_LARGE)
    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip()
    if not content_type.startswith("image/"):
        return C2paResult(C2paStatus.UNSUPPORTED)
    trust_anchors = await _official_trust_anchors(config)
    return await asyncio.to_thread(
        inspect_embedded_c2pa,
        image,
        content_type,
        trust_anchors,
    )
