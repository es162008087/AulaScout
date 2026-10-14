"""Settings: toda la config sale de entorno/.env. Sin key no hay llamadas."""

from __future__ import annotations

import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dotenv es dependencia declarada
    def load_dotenv(*args, **kwargs):
        return False

DEFAULT_BASE_URL = "https://api.meta.ai/v1"


@dataclass(frozen=True)
class Settings:
    api_key: str
    base_url: str = DEFAULT_BASE_URL
    timeout_s: float = 60.0


def load_settings() -> Settings:
    load_dotenv()
    api_key = os.environ.get("MODEL_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "Falta MODEL_API_KEY. Copia .env.example a .env y pon tu key."
        )
    base_url = os.environ.get("META_API_BASE_URL", DEFAULT_BASE_URL).strip() or DEFAULT_BASE_URL
    return Settings(api_key=api_key, base_url=base_url.rstrip("/"))


def auth_headers(settings: Settings) -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.api_key}"}
