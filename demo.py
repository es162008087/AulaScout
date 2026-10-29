"""Entry point de la demo de 2 min: foto (+audio?) -> planeacion + ficha."""

from __future__ import annotations

import argparse
import logging

from src.pipeline import run_pipeline


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description="Demo: planeacion didactica")
    parser.add_argument("--foto", required=True, help="Foto del salon (jpg/png)")
    parser.add_argument("--audio", default=None, help="Nota de voz opcional (m4a/wav)")
    parser.add_argument("--salida", default="out", help="Directorio de salida")
    args = parser.parse_args()

    if args.audio:
        print("0/4 Voice: transcribiendo audio...")
    else:
        print("0/4 Voice: omitido (sin --audio).")
    print("1/4 SAM 3.1: detectando materiales...")
    result = run_pipeline(foto=args.foto, audio=args.audio, salida=args.salida)
    print("2/4 Spark: planeacion generada.")
    print("3/4 Image: ficha visual generada.")
    for name, path in result.items():
        print(f"  {name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
