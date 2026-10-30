"""Voz via api.meta.ai/v1: audio -> transcripcion -> materiales."""

from __future__ import annotations

import json
import logging
import subprocess
import tempfile
from pathlib import Path

import requests

from src.config import Settings

VOICE_URL = "https://api.meta.ai/v1/asr/transcribe"
MODEL_VOICE = "muse-voice-transcribe-1.0"
VOICE_LANGUAGE = "es"
ASR_SAMPLE_RATE = 16000
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


def convertir_a_wav_16k(audio_path: str | Path, dest_dir: str | Path) -> Path:
    """Convierte cualquier audio a WAV PCM mono 16kHz (formato del ASR)."""
    src = Path(audio_path)
    wav = Path(dest_dir) / f"{src.stem}_16k.wav"
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error", "-i", str(src),
            "-ac", "1", "-ar", str(ASR_SAMPLE_RATE),
            "-c:a", "pcm_s16le", str(wav),
        ],
        check=True,
        timeout=120,
    )
    return wav


def build_asr_request_part() -> str:
    return json.dumps(
        {
            "model": MODEL_VOICE,
            "language": VOICE_LANGUAGE,
            "audioEncoding": "WAV",
        }
    )


def transcribir_audio(audio_path: str | Path, settings: Settings) -> str:
    path = Path(audio_path)
    if not path.is_file():
        raise FileNotFoundError(f"No existe el audio: {path}")
    try:
        with tempfile.TemporaryDirectory(prefix="asr_") as tmp:
            wav = convertir_a_wav_16k(path, tmp)
            with open(wav, "rb") as fh:
                resp = requests.post(
                    VOICE_URL,
                    headers={"Authorization": f"Bearer {settings.api_key}"},
                    files={
                        "request": (None, build_asr_request_part(), "application/json"),
                        "audio": (wav.name, fh, "audio/wav"),
                    },
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
