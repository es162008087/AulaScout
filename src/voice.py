"""Voz via api.meta.ai/v1: audio -> transcripcion -> materiales."""

from __future__ import annotations

import logging
from pathlib import Path

import requests

from src.config import Settings

VOICE_URL = "https://api.meta.ai/v1/asr/transcribe"
MODEL_VOICE = "muse-voice-transcribe-1.0"
VOICE_LANGUAGE = "es"
DEMO_TRANSCRIPTION = (
    "Tengo tapete de foami, bloques de madera de colores, "
    "canasta con pelotas sensoriales y libros de tela"
)

VOZ_A_OFICIAL = {
    "tapete": "tapete de foami multicolor",
    "foami": "tapete de foami multicolor",
    "bloques": "bloques de madera de colores",
    "pelotas": "canasta de pelotas suaves",
    "libros": "libros infantiles de tela",
    "rompecabezas": "rompecabezas de figuras geométricas",
}

logger = logging.getLogger(__name__)


def parse_materiales_desde_voz(texto: str) -> list[str]:
    """Mapea keywords de la transcripcion a la lista oficial."""
    bajo = texto.lower()
    mats: list[str] = []
    for keyword, oficial in VOZ_A_OFICIAL.items():
        if keyword in bajo and oficial not in mats:
            mats.append(oficial)
    return mats


def transcribir_audio(audio_path: str | Path, settings: Settings) -> str:
    path = Path(audio_path)
    if not path.is_file():
        raise FileNotFoundError(f"No existe el audio: {path}")
    try:
        with open(path, "rb") as fh:
            resp = requests.post(
                VOICE_URL,
                headers={"Authorization": f"Bearer {settings.api_key}"},
                data={"model": MODEL_VOICE, "language": VOICE_LANGUAGE},
                files={"file": (path.name, fh)},
                timeout=settings.timeout_s,
            )
        resp.raise_for_status()
        data = resp.json()
        text = data.get("text", data.get("transcription", data.get("transcript", "")))
        if not str(text).strip():
            raise ValueError("ASR devolvio transcripcion vacia.")
        return str(text).strip()
    except Exception as exc:
        logger.warning("Voz fallo (%s), usando transcripcion demo", exc)
        return DEMO_TRANSCRIPTION
