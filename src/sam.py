"""SAM 3.1 via api.meta.ai/v1: foto del salon -> materiales detectados."""

from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any

from openai import OpenAI

from src.config import Settings

MODEL_SAM = "sam-3.1"
SAM_PROMPT = (
    "Detecta: bloques, tapete, juguetes, "
    "materiales didácticos de maternal. Lista corta."
)
FALLBACK_MATERIALS = ["bloques", "tapete", "juguetes", "libros infantiles"]

logger = logging.getLogger(__name__)


def build_sam_payload(image_bytes: bytes) -> dict:
    """Payload JSON serializable para tests sin red."""
    return {"image_b64": base64.b64encode(image_bytes).decode("ascii")}


def _field(item: Any, name: str) -> Any:
    if isinstance(item, dict):
        return item.get(name)
    return getattr(item, name, None)


def parse_materials(output: Any) -> list[str]:
    """Extrae materiales de resp.output; [] si no hay texto aprovechable."""
    texts: list[str] = []
    for item in output or []:
        if _field(item, "type") != "message":
            continue
        for part in _field(item, "content") or []:
            if _field(part, "type") == "output_text":
                text = _field(part, "text")
                if text and str(text).strip():
                    texts.append(str(text))
    materials: list[str] = []
    for text in texts:
        for chunk in text.replace("\n", ",").split(","):
            name = chunk.strip().lstrip("-•*0123456789. ").strip()
            if name:
                materials.append(name)
    return materials


def detect_materials(image_path: str | Path, settings: Settings) -> list[str]:
    path = Path(image_path)
    if not path.is_file():
        raise FileNotFoundError(f"No existe la foto: {path}")
    b64 = build_sam_payload(path.read_bytes())["image_b64"]
    client = OpenAI(base_url=settings.base_url, api_key=settings.api_key)
    try:
        resp = client.responses.create(
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
            timeout=10,
        )
        materials = parse_materials(resp.output)
        if not materials:
            raise ValueError("SAM devolvio output sin texto aprovechable.")
        return materials
    except Exception as exc:
        logger.warning("SAM fallo, usando fallback: %s", exc)
        return list(FALLBACK_MATERIALS)
