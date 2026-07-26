"""Shared HTTP proxy environment resolution."""

from __future__ import annotations

import os

_PROXY_ENV_NAMES = ("PROXY", "HTTP_PROXY", "HTTPS_PROXY")


def get_http_proxy_from_env() -> str | None:
    """Return the first configured HTTP proxy in documented priority order."""
    return next(
        (proxy for name in _PROXY_ENV_NAMES if (proxy := os.getenv(name))),
        None,
    )
