"""Tests for core.config — Settings singleton and path constants."""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest


def test_base_paths_exist():
    from core.config import BASE_DIR, DATA_DIR, POI_PATH, INDEX_DIR, PROFILE_DB_PATH, PROFILE_IMPORTS_PATH

    assert BASE_DIR.name == "smartroute-main" or BASE_DIR.name == "smartroute"
    assert DATA_DIR == BASE_DIR / "data"
    assert POI_PATH == DATA_DIR / "pois.json"
    assert INDEX_DIR == DATA_DIR / "local_index"
    assert PROFILE_DB_PATH == DATA_DIR / "user_profiles.db"
    assert PROFILE_IMPORTS_PATH == DATA_DIR / "profile_imports.json"


def test_settings_defaults():
    """Settings should return sensible defaults when no env vars are set."""
    from core.config import Settings

    with patch.dict(os.environ, {}, clear=False):
        # Remove relevant env vars to test defaults
        for key in ["DEEPSEEK_API_KEY", "AMAP_WEB_SERVICE_KEY", "CORS_ORIGINS", "PORT", "HOST", "LOG_LEVEL"]:
            os.environ.pop(key, None)
        settings = Settings()

    assert settings.deepseek_api_key == ""
    assert settings.deepseek_chat_model == "deepseek-chat"
    assert settings.deepseek_route_model == "deepseek-reasoner"
    assert settings.deepseek_base_url == "https://api.deepseek.com"
    assert settings.amap_web_service_key == ""
    assert settings.host == "127.0.0.1"
    assert settings.port == 8000
    assert settings.log_level == "INFO"
    assert "http://127.0.0.1:5173" in settings.cors_origins


def test_deepseek_enabled_false_when_no_key():
    from core.config import Settings

    with patch.dict(os.environ, {"DEEPSEEK_API_KEY": ""}, clear=False):
        settings = Settings()
    assert settings.deepseek_enabled is False


def test_deepseek_enabled_true_when_key_set():
    from core.config import Settings

    with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key-123"}, clear=False):
        settings = Settings()
    assert settings.deepseek_enabled is True


def test_amap_enabled_false_when_no_key():
    from core.config import Settings

    with patch.dict(os.environ, {"AMAP_WEB_SERVICE_KEY": ""}, clear=False):
        settings = Settings()
    assert settings.amap_enabled is False


def test_amap_enabled_true_when_key_set():
    from core.config import Settings

    with patch.dict(os.environ, {"AMAP_WEB_SERVICE_KEY": "test-amap-key"}, clear=False):
        settings = Settings()
    assert settings.amap_enabled is True


def test_cors_origins_parsing():
    from core.config import Settings

    with patch.dict(os.environ, {"CORS_ORIGINS": "https://a.com, https://b.com , https://c.com"}, clear=False):
        settings = Settings()
    assert settings.cors_origins == ["https://a.com", "https://b.com", "https://c.com"]


def test_cors_origins_strips_empty_entries():
    from core.config import Settings

    with patch.dict(os.environ, {"CORS_ORIGINS": "https://a.com,,https://b.com,"}, clear=False):
        settings = Settings()
    assert "https://a.com" in settings.cors_origins
    assert "https://b.com" in settings.cors_origins
    assert "" not in settings.cors_origins


def test_port_parsing():
    from core.config import Settings

    with patch.dict(os.environ, {"PORT": "9000"}, clear=False):
        settings = Settings()
    assert settings.port == 9000


def test_get_settings_singleton():
    """get_settings() should return the same instance on repeated calls."""
    import core.config as config_module

    # Reset singleton
    config_module._settings = None

    s1 = config_module.get_settings()
    s2 = config_module.get_settings()
    assert s1 is s2

    # Clean up
    config_module._settings = None
