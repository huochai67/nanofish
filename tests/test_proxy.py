from pathlib import Path

from pydantic import BaseModel
from pytest import MonkeyPatch

from src import plugin_config
from src.proxy import get_http_proxy_from_env


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
