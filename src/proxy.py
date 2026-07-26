"""Shared HTTP proxy environment resolution."""

from __future__ import annotations

import os
from ipaddress import ip_address, ip_network
from urllib.parse import urlsplit

_PROXY_ENV_NAMES = ("PROXY", "HTTP_PROXY", "HTTPS_PROXY")
_NO_PROXY_ENV_NAMES = ("NO_PROXY", "no_proxy")


def get_http_proxy_from_env() -> str | None:
    """Return the first configured HTTP proxy in documented priority order."""
    return next(
        (proxy for name in _PROXY_ENV_NAMES if (proxy := os.getenv(name))),
        None,
    )


def get_no_proxy_from_env() -> str | None:
    """Return the standard proxy exclusion list, preserving its original syntax."""
    return next(
        (value for name in _NO_PROXY_ENV_NAMES if (value := os.getenv(name))),
        None,
    )


def _no_proxy_parts(rule: str) -> tuple[str, int | None]:
    if rule.startswith("["):
        host, separator, port = rule[1:].partition("]")
        if separator and port.startswith(":") and port[1:].isdigit():
            return host, int(port[1:])
        return host, None
    host, separator, port = rule.rpartition(":")
    if separator and port.isdigit() and ":" not in host:
        return host, int(port)
    return rule, None


def _matches_no_proxy_rule(host: str, port: int | None, rule: str) -> bool:
    rule_host, rule_port = _no_proxy_parts(rule.strip().lower())
    if not rule_host or (rule_port is not None and port != rule_port):
        return False
    if rule_host == "*":
        return True
    try:
        return ip_address(host) in ip_network(rule_host, strict=False)
    except ValueError:
        pass
    rule_host = rule_host.lstrip(".")
    return host == rule_host or host.endswith(f".{rule_host}")


def should_bypass_proxy(url: str) -> bool:
    """Whether a URL matches the standard NO_PROXY exclusion list."""
    no_proxy = get_no_proxy_from_env()
    if not no_proxy:
        return False
    parsed = urlsplit(url)
    host = parsed.hostname
    if not host:
        return False
    return any(
        _matches_no_proxy_rule(host.lower(), parsed.port, rule)
        for rule in no_proxy.split(",")
    )


def get_http_proxy_for_url(url: str, proxy: str | None = None) -> str | None:
    """Return a proxy for URL unless its host is excluded by NO_PROXY."""
    resolved_proxy = get_http_proxy_from_env() if proxy is None else proxy
    if resolved_proxy and should_bypass_proxy(url):
        return None
    return resolved_proxy


def configure_proxy_environment() -> None:
    """Expose PROXY and NO_PROXY through standard variable names for SDKs."""
    if proxy := get_http_proxy_from_env():
        for name in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            os.environ[name] = proxy
    if no_proxy := get_no_proxy_from_env():
        os.environ["NO_PROXY"] = no_proxy
        os.environ["no_proxy"] = no_proxy


configure_proxy_environment()
