# Planeaciones didácticas — Hackathon Meta Global AI 2026

Track indie: **Build for Your World**.
Asistente de planeaciones para lactantes y maternal alineadas a la SEP.

## Flujo

Foto del salón → **SAM 3.1** detecta materiales →
**Llama Spark** genera planeación de 3 actividades SEP →
**Llama Image** genera ficha visual.

Todo el consumo de modelos va por `https://api.meta.ai/v1`.
La key vive solo en `.env` (`MODEL_API_KEY`), nunca en el repo.

## Setup

```bash
cp .env.example .env   # pon tu key real
uv venv
uv pip install -e ".[dev]"
```

Sin `uv`:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Demo (2 min)

```bash
uv run python demo.py --foto salon.jpg --salida out/
# o con venv activado: python demo.py --foto salon.jpg --salida out/
```

Salida en `out/`: `materiales.json`, `planeacion.md`, `ficha.png`.

Guion detallado: [docs/DEMO.md](docs/DEMO.md).

## Estructura

```text
demo.py            # entry point de la demo
src/
  config.py        # settings desde .env (MODEL_API_KEY, base URL)
  sam.py           # SAM 3.1: foto -> materiales
  spark.py         # Spark: materiales -> planeacion 3 actividades SEP
  image.py         # Image: planeacion -> ficha visual
  pipeline.py      # orquesta el flujo completo
tests/             # pruebas sin red (prompts/payloads)
docs/DEMO.md       # guion de la demo de 2 min
```

## Reglas

- Todo via `api.meta.ai/v1`, sin llamadas directas desde frontend (no hay frontend).
- Sin key no hay demo: el pipeline falla con mensaje claro si falta `MODEL_API_KEY`.
- Commits pequeños.
