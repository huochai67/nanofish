from pytest import MonkeyPatch

from src.plugins.genai_detect import plugin_config as genai_config
from src.plugins.health import Status, check_sightengine


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
