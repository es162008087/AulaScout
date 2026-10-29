"""Orquesta foto (+audio?) -> materiales -> planeacion -> ficha."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from src.config import Settings, load_settings
from src.image import generate_ficha
from src.sam import detect_materials
from src.spark import generate_planeacion
from src.voice import parse_materiales_desde_voz, transcribir_audio

logger = logging.getLogger(__name__)


def run_pipeline(
    foto: str | Path,
    audio: str | Path | None = None,
    salida: str | Path = "out",
    settings: Settings | None = None,
) -> dict[str, str]:
    settings = settings or load_settings()
    out_dir = Path(salida)
    out_dir.mkdir(parents=True, exist_ok=True)
    result: dict[str, str] = {}

    voz_mats: list[str] = []
    if audio:
        logger.info("[Voice] transcribiendo %s", audio)
        transcription = transcribir_audio(audio, settings)
        (out_dir / "transcripcion.txt").write_text(transcription, encoding="utf-8")
        result["transcripcion"] = str(out_dir / "transcripcion.txt")
        voz_mats = parse_materiales_desde_voz(transcription)
        logger.info("[Voice] %d materiales desde voz", len(voz_mats))

    logger.info("[SAM] detectando materiales en %s", foto)
    sam_mats = detect_materials(foto, settings)

    materials = list(dict.fromkeys([*sam_mats, *voz_mats]))
    logger.info(
        "[Merge] sam=%d voz=%d total=%d",
        len(sam_mats),
        len(voz_mats),
        len(materials),
    )
    (out_dir / "materiales.json").write_text(
        json.dumps(materials, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    result["materiales"] = str(out_dir / "materiales.json")

    planeacion = generate_planeacion(materials, settings)
    (out_dir / "planeacion.md").write_text(planeacion, encoding="utf-8")
    result["planeacion"] = str(out_dir / "planeacion.md")

    ficha = generate_ficha(planeacion, settings, out_dir / "ficha.png")
    result["ficha"] = str(ficha)

    return result
