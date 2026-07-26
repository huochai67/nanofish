"""Load business plugin settings from the repository YAML configuration."""

from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import TypeVar

import yaml
from pydantic import BaseModel

from src.proxy import get_http_proxy_from_env

_CONFIG_PATH = Path("config.yaml")
ConfigModel = TypeVar("ConfigModel", bound=BaseModel)


@cache
def _load_config() -> dict[str, object]:
    try:
        raw = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        msg = f"business configuration file not found: {_CONFIG_PATH}"
        raise RuntimeError(msg) from exc
    except yaml.YAMLError as exc:
        msg = f"invalid YAML in {_CONFIG_PATH}: {exc}"
        raise RuntimeError(msg) from exc

    if raw is None:
        return {}
    if not isinstance(raw, dict) or not all(isinstance(key, str) for key in raw):
        msg = f"{_CONFIG_PATH} must contain a mapping with string keys"
        raise RuntimeError(msg)
    return raw


def get_yaml_plugin_config(model: type[ConfigModel], plugin: str) -> ConfigModel:
    """Build a plugin config from YAML and the shared environment proxy."""
    raw = _load_config().get(plugin, {})
    if not isinstance(raw, dict) or not all(isinstance(key, str) for key in raw):
        msg = f"{_CONFIG_PATH} section {plugin!r} must contain a mapping"
        raise RuntimeError(msg)
    values = raw.copy()
    if "proxy" in model.model_fields:
        values["proxy"] = get_http_proxy_from_env()
    return model.model_validate(values)
