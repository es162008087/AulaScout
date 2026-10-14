"""Orquesta foto -> materiales -> planeacion -> ficha."""

from __future__ import annotations

import json
from pathlib import Path

from src.config import Settings, load_settings
from src.image import generate_ficha
from src.sam import detect_materials
from src.spark import generate_planeacion


def run_pipeline(
    foto: str | Path,
    salida: str | Path,
    settings: Settings | None = None,
) -> dict[str, str]:
    settings = settings or load_settings()
    out_dir = Path(salida)
    out_dir.mkdir(parents=True, exist_ok=True)

    materials = detect_materials(foto, settings)
    (out_dir / "materiales.json").write_text(
        json.dumps(materials, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    planeacion = generate_planeacion(materials, settings)
    (out_dir / "planeacion.md").write_text(planeacion, encoding="utf-8")

    ficha = generate_ficha(planeacion, settings, out_dir / "ficha.png")

    return {
        "materiales": str(out_dir / "materiales.json"),
        "planeacion": str(out_dir / "planeacion.md"),
        "ficha": str(ficha),
    }
