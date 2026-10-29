"""Llama Spark via api.meta.ai/v1: materiales -> planeacion 3 actividades SEP."""

from __future__ import annotations

import logging

from openai import OpenAI

from src.config import Settings

MODEL_SPARK = "muse-spark-1.3"
SYSTEM_PROMPT = (
    "Eres educadora SEP experta. Responde siempre en markdown con 3 actividades."
)
SPARK_TIMEOUT = 60
SPARK_MAX_TOKENS = 2500
SPARK_RETRIES = 2
MIN_CONTENT_LEN = 100

logger = logging.getLogger(__name__)


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
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_planeacion_prompt(materials)},
    ]
    for attempt in range(SPARK_RETRIES + 1):
        try:
            resp = client.chat.completions.create(
                model=MODEL_SPARK,
                messages=messages,
                max_tokens=SPARK_MAX_TOKENS,
                temperature=0.7,
                timeout=SPARK_TIMEOUT,
            )
            text = (resp.choices[0].message.content or "").strip()
            if len(text) >= MIN_CONTENT_LEN:
                return text
            logger.warning(
                "Spark intento %d: respuesta corta (%d chars), reintentando",
                attempt + 1,
                len(text),
            )
        except Exception as exc:
            logger.warning("Spark intento %d fallo: %s", attempt + 1, exc)
    raise ValueError(f"Spark sin respuesta util tras {SPARK_RETRIES + 1} intentos.")
