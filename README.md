# Planeaciones didácticas — Hackathon Meta Global AI 2026

Track indie: **Build for Your World**.
Asistente de planeaciones para lactantes y maternal alineadas a la SEP.

## Flujo

Foto del salón → **SAM 3.1** detecta materiales →
**Llama Spark** genera planeación de 3 actividades SEP →
**Llama Image** genera ficha visual.

Todo el consumo de modelos va por `https://api.meta.ai/v1`.
La key vive solo en `.env` (`MODEL_API_KEY`), nunca en el repo.

## Demo URL oficial

**https://aulascout-demo-389771440223.us-central1.run.app** (Google Cloud Run, pública, sin Tailscale).

Sube una foto del salón (sin personas) y una nota de voz de 15-20 s; corre el pipeline real
Voice + SAM 3.1 + Spark 1.3 + Image 1.0 (~1-2 min por corrida). Demo con tope: 5 corridas/hora
por IP y 20/día global (`Límite de demo alcanzado` al excederlo). AulaScout es planeación
educativa, no consejo médico.

Despliegue: `gcloud run deploy aulascout-demo --source . --region us-central1 --allow-unauthenticated
--memory 1Gi --cpu 1 --no-cpu-throttling --timeout 300 --max-instances 1 --concurrency 10
--set-secrets MODEL_API_KEY=MODEL_API_KEY:latest` (Dockerfile en la raíz; la key vive en Secret Manager).

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
