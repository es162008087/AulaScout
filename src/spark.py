"""Llama Spark via api.meta.ai/v1: materiales -> planeacion 3 actividades SEP."""

from __future__ import annotations

from openai import OpenAI

from src.config import Settings

MODEL_SPARK = "muse-spark-1.3"


def build_planeacion_prompt(materials: list[str]) -> str:
    mats = ", ".join(materials) if materials else "materiales basicos de aula"
    return (
        "Eres educadora SEP maternal. "
        f"Con materiales: {mats}, genera planeación de 3 actividades "
        "de 20 min en markdown con Título, Edad, Objetivo, Materiales, "
        "Pasos y Seguridad."
    )


def generate_planeacion(materials: list[str], settings: Settings) -> str:
    client = OpenAI(base_url=settings.base_url, api_key=settings.api_key)
    resp = client.chat.completions.create(
        model=MODEL_SPARK,
        messages=[{"role": "user", "content": build_planeacion_prompt(materials)}],
        max_tokens=1500,
    )
    text = resp.choices[0].message.content or ""
    if not text.strip():
        raise ValueError("Spark devolvio una planeacion vacia.")
    return text
