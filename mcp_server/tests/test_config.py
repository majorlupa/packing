import pytest

from mcp_server.config import Settings


def test_defaults_are_local_and_english(monkeypatch):
    for name in ("PACKING_API_URL", "PACKING_ACCESS_TOKEN", "PACKING_LANGUAGE", "PACKING_PRINTER",
                 "PACKING_LABEL_DIR", "PACKING_API_TIMEOUT"):
        monkeypatch.delenv(name, raising=False)
    settings = Settings.from_env()
    assert settings.api_url == "http://127.0.0.1:3001"
    assert settings.access_token == ""
    assert settings.language == "en"
    assert settings.printer == ""
    assert settings.label_dir == ""
    assert settings.timeout == 60.0


def test_environment_is_read_and_trailing_slash_removed(monkeypatch):
    monkeypatch.setenv("PACKING_API_URL", "http://box.local:3001/")
    monkeypatch.setenv("PACKING_ACCESS_TOKEN", "t" * 40)
    monkeypatch.setenv("PACKING_LANGUAGE", "PL")
    monkeypatch.setenv("PACKING_PRINTER", "Office")
    monkeypatch.setenv("PACKING_LABEL_DIR", "/tmp/labels")
    monkeypatch.setenv("PACKING_API_TIMEOUT", "12.5")
    settings = Settings.from_env()
    assert settings.api_url == "http://box.local:3001"
    assert settings.language == "pl"
    assert settings.printer == "Office"
    assert settings.label_dir == "/tmp/labels"
    assert settings.timeout == 12.5


@pytest.mark.parametrize("value", ["de", "english", "1"])
def test_unsupported_language_is_rejected(monkeypatch, value):
    monkeypatch.setenv("PACKING_LANGUAGE", value)
    with pytest.raises(ValueError, match="PACKING_LANGUAGE"):
        Settings.from_env()


def test_invalid_api_url_is_rejected(monkeypatch):
    monkeypatch.setenv("PACKING_API_URL", "packing:3001")
    with pytest.raises(ValueError, match="PACKING_API_URL"):
        Settings.from_env()


@pytest.mark.parametrize("value", ["abc", "0", "-3"])
def test_invalid_timeout_is_rejected(monkeypatch, value):
    monkeypatch.setenv("PACKING_API_TIMEOUT", value)
    with pytest.raises(ValueError, match="PACKING_API_TIMEOUT"):
        Settings.from_env()


def test_token_never_appears_in_repr():
    settings = Settings(access_token="super-secret-value")
    assert "super-secret-value" not in repr(settings)
    assert "super-secret-value" not in str(settings)
