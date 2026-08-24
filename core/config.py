"""Centralized configuration for SmartRoute.

Single source of truth for all paths, environment variables, and settings.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


# ── Base paths ──────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
POI_PATH = DATA_DIR / "pois.json"
INDEX_DIR = DATA_DIR / "local_index"
PROFILE_DB_PATH = DATA_DIR / "user_profiles.db"
PROFILE_IMPORTS_PATH = DATA_DIR / "profile_imports.json"

# Load .env from project root
load_dotenv(BASE_DIR / ".env")


class Settings:
    """Application settings loaded from environment variables.

    Usage::

        from core.config import get_settings
        settings = get_settings()
        if settings.deepseek_enabled:
            ...
    """

    def __init__(self) -> None:
        # DeepSeek LLM
        self.deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
        self.deepseek_chat_model: str = os.getenv("DEEPSEEK_CHAT_MODEL", "deepseek-chat")
        self.deepseek_route_model: str = os.getenv("DEEPSEEK_ROUTE_MODEL", "deepseek-reasoner")
        self.deepseek_base_url: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

        # AMap
        self.amap_web_service_key: str = os.getenv("AMAP_WEB_SERVICE_KEY", "")

        # Database
        self.user_db_path: str = os.getenv("USER_DB_PATH", str(PROFILE_DB_PATH))

        # Server
        self.host: str = os.getenv("HOST", "127.0.0.1")
        self.port: int = int(os.getenv("PORT", "8000"))

        # CORS
        origins_raw = os.getenv("CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173")
        self.cors_origins: list[str] = [o.strip() for o in origins_raw.split(",") if o.strip()]

        # Logging
        self.log_level: str = os.getenv("LOG_LEVEL", "INFO")

    @property
    def deepseek_enabled(self) -> bool:
        """Whether DeepSeek API key is configured."""
        return bool(self.deepseek_api_key)

    @property
    def amap_enabled(self) -> bool:
        """Whether AMap Web Service key is configured."""
        return bool(self.amap_web_service_key)


# ── Singleton ───────────────────────────────────────────────────────────
_settings: Settings | None = None


def get_settings() -> Settings:
    """Return the application settings singleton."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
