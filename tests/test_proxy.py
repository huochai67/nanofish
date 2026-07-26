from pathlib import Path

from pydantic import BaseModel
from pytest import MonkeyPatch

from src import plugin_config
from src.proxy import (
    get_http_proxy_for_url,
    get_http_proxy_from_env,
    should_bypass_proxy,
)


class _PluginConfig(BaseModel):
    proxy: str | None = None


def test_proxy_environment_priority(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("HTTPS_PROXY", "http://https-proxy:443")
    monkeypatch.setenv("HTTP_PROXY", "http://http-proxy:8080")
    monkeypatch.setenv("PROXY", "http://proxy:23333")

    assert get_http_proxy_from_env() == "http://proxy:23333"


def test_proxy_environment_falls_back_to_standard_names(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.delenv("PROXY", raising=False)
    monkeypatch.setenv("HTTPS_PROXY", "http://https-proxy:443")
    monkeypatch.setenv("HTTP_PROXY", "http://http-proxy:8080")

    assert get_http_proxy_from_env() == "http://http-proxy:8080"


def test_yaml_plugin_config_receives_environment_proxy(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PROXY", "http://sing-box:23333")
    monkeypatch.setattr(plugin_config, "_CONFIG_PATH", tmp_path / "config.yaml")
    (tmp_path / "config.yaml").write_text("example: {}\n", encoding="utf-8")
    plugin_config._load_config.cache_clear()

    try:
        config = plugin_config.get_yaml_plugin_config(_PluginConfig, "example")
    finally:
        plugin_config._load_config.cache_clear()

    assert config.proxy == "http://sing-box:23333"


def test_no_proxy_matches_standard_host_rules(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv(
        "NO_PROXY",
        "example.com,.internal.test,127.0.0.1,10.0.0.0/8,api.test:8443",
    )

    assert should_bypass_proxy("https://example.com/path")
    assert should_bypass_proxy("https://cdn.example.com/path")
    assert should_bypass_proxy("https://api.internal.test/path")
    assert should_bypass_proxy("http://127.0.0.1:3000")
    assert should_bypass_proxy("http://10.2.3.4")
    assert should_bypass_proxy("https://api.test:8443/path")
    assert not should_bypass_proxy("https://api.test:443/path")
    assert not should_bypass_proxy("https://not-example.com/path")


def test_no_proxy_bypasses_explicit_proxy(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("PROXY", "http://proxy:7890")
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.setenv("no_proxy", "localhost")

    assert get_http_proxy_for_url("http://localhost:3000") is None
    assert get_http_proxy_for_url("https://example.com") == "http://proxy:7890"
