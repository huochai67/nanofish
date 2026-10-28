from pytest import MonkeyPatch

from src.plugins.genai_detect import plugin_config as genai_config
from src.plugins.health import Status, check_llm, check_sightengine
from src.plugins.llm import config as llm_config


def test_check_sightengine_reports_configured(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(genai_config, "sightengine_api_user", "user")
    monkeypatch.setattr(genai_config, "sightengine_api_secret", "secret")

    result = check_sightengine()

    assert result.status is Status.OK


def test_check_sightengine_reports_missing_credentials(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(genai_config, "sightengine_api_user", "")
    monkeypatch.setattr(genai_config, "sightengine_api_secret", "")

    result = check_sightengine()

    assert result.status is Status.FAIL
    assert "sightengine_api_user" in result.detail
    assert "sightengine_api_secret" in result.detail


def test_check_llm_reports_configured() -> None:
    result = check_llm()

    assert result.status is Status.OK
    assert "model=" in result.detail


def test_check_llm_reports_missing_credentials(monkeypatch: MonkeyPatch) -> None:
    default_profile = llm_config.image_models[llm_config.image_default_model]
    monkeypatch.setattr(default_profile, "api_key", "")

    result = check_llm()

    assert result.status is Status.FAIL
    assert "api_key" in result.detail
