"""Llama Image via api.meta.ai/v1: planeacion -> ficha visual PNG."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from openai import OpenAI

from src.config import Settings

MODEL_IMAGE = "muse-image-1.0"
IMAGE_TIMEOUT = 90


def build_ficha_prompt(planeacion_md: str) -> str:
    resumen = planeacion_md.strip().replace("\n", " ")[:600]
    return (
        "Ficha visual infantil para aula de maternal, estilo plano y alegre, "
        "sin texto largo, que ilustre estas actividades: " + resumen
    )


def _field(item: Any, name: str) -> Any:
    if isinstance(item, dict):
        return item.get(name)
    return getattr(item, name, None)


def extract_image_b64(output: Any) -> str:
    """Saca el base64 del item image_generation_call; "" si no hay."""
    for item in output or []:
        if _field(item, "type") != "image_generation_call":
            continue
        for name in ("result", "image"):
            value = _field(item, name)
            if value and str(value).strip():
                b64 = str(value).strip()
                if b64.startswith("data:"):
                    b64 = b64.split(",", 1)[1] if "," in b64 else ""
                return b64
    return ""


def generate_ficha(
    planeacion_md: str, settings: Settings, out_path: str | Path
) -> Path:
    client = OpenAI(base_url=settings.base_url, api_key=settings.api_key)
    resp = client.responses.create(
        model=MODEL_IMAGE,
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": build_ficha_prompt(planeacion_md)}
                ],
            }
        ],
        tools=[{"type": "image_generation"}],
        timeout=IMAGE_TIMEOUT,
    )
    b64 = extract_image_b64(resp.output)
    if not b64:
        raise ValueError("Image no devolvio imagen.")
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(base64.b64decode(b64))
    return out
