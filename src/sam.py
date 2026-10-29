"""SAM 3.1 via api.meta.ai/v1: foto del salon -> materiales detectados."""

from __future__ import annotations

import base64
import logging
import re
import time
from pathlib import Path
from typing import Any

from openai import OpenAI

from src.config import Settings

MODEL_SAM = "sam-3.1"
MODEL_SPARK_VISION = "muse-spark-1.3"
SAM_TIMEOUT = 30
SAM_RETRIES = 3
SAM_BACKOFFS = (2, 4, 8)
SAM_PROMPT = (
    "Detecta: bloques, tapete, juguetes, "
    "materiales didácticos de maternal. Lista corta."
)
VISION_PROMPT = (
    "Lista en coma los materiales didácticos visibles en este salón: "
    "bloques, tapete, pelotas, libros, etc."
)
FALLBACK_MATERIALS = [
    "bloques de madera de colores",
    "tapete de foami multicolor",
    "canasta de pelotas suaves",
    "libros infantiles de tela",
    "rompecabezas de figuras geométricas",
    "estante de madera",
]

logger = logging.getLogger(__name__)


def build_sam_payload(image_bytes: bytes) -> dict:
    """Payload JSON serializable para tests sin red."""
    return {"image_b64": base64.b64encode(image_bytes).decode("ascii")}


def _field(item: Any, name: str) -> Any:
    if isinstance(item, dict):
        return item.get(name)
    return getattr(item, name, None)


def clean_special_tokens(raw: str) -> str:
    """Quita tokens especiales <|...|> del output crudo."""
    return re.sub(r"<\|.*?\|>", " ", raw)


def split_materials_text(text: str) -> list[str]:
    """Parte texto libre en nombres de materiales limpios."""
    materials: list[str] = []
    for chunk in clean_special_tokens(text).replace("\n", ",").split(","):
        name = chunk.strip().lstrip("-•*0123456789. ").strip()
        if name:
            materials.append(name)
    return materials


def parse_materials(output: Any) -> list[str]:
    """Extrae materiales de resp.output; [] si no hay texto aprovechable."""
    materials: list[str] = []
    for item in output or []:
        if _field(item, "type") != "message":
            continue
        for part in _field(item, "content") or []:
            if _field(part, "type") == "output_text":
                text = _field(part, "text")
                if text and str(text).strip():
                    materials.extend(split_materials_text(str(text)))
    return materials


def _call_sam(client: Any, b64: str) -> Any:
    """Llama a sam-3.1 con 3 reintentos y backoff 2s/4s/8s."""
    last_exc: Exception | None = None
    for attempt in range(SAM_RETRIES + 1):
        try:
            return client.responses.create(
                model=MODEL_SAM,
                input=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": SAM_PROMPT},
                            {
                                "type": "input_image",
                                "image_url": f"data:image/jpeg;base64,{b64}",
                            },
                        ],
                    }
                ],
                timeout=SAM_TIMEOUT,
            )
        except Exception as exc:
            last_exc = exc
            if attempt < SAM_RETRIES:
                delay = SAM_BACKOFFS[attempt]
                logger.warning(
                    "SAM intento %d fallo (%s), reintentando en %ss",
                    attempt + 1,
                    exc,
                    delay,
                )
                time.sleep(delay)
    assert last_exc is not None
    raise last_exc


def detect_materials(image_path: str | Path, settings: Settings) -> list[str]:
    path = Path(image_path)
    if not path.is_file():
        raise FileNotFoundError(f"No existe la foto: {path}")
    b64 = build_sam_payload(path.read_bytes())["image_b64"]
    try:
        client = OpenAI(base_url=settings.base_url, api_key=settings.api_key)
    except Exception as exc:
        logger.warning("Sin cliente OpenAI (%s), usando lista fija", exc)
        return list(FALLBACK_MATERIALS)
    try:
        resp = _call_sam(client, b64)
        materials = parse_materials(resp.output)
        if materials:
            return materials
        logger.warning("SAM sin texto aprovechable, probando Spark Vision")
    except Exception as exc:
        logger.warning("SAM fallo (%s), probando Spark Vision", exc)
    try:
        resp = client.chat.completions.create(
            model=MODEL_SPARK_VISION,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": VISION_PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{b64}",
                            },
                        },
                    ],
                }
            ],
        )
        materials = split_materials_text(resp.choices[0].message.content or "")
        if materials:
            return materials
        logger.warning("Spark Vision sin texto aprovechable, usando lista fija")
    except Exception as exc:
        logger.warning("Spark Vision fallo (%s), usando lista fija", exc)
    return list(FALLBACK_MATERIALS)
