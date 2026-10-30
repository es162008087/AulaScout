# Presupuesto final — AULA-SCOUT (2026-10-30)

**Estado:** cerrado. Autorizado acumulado declarado **$90 de $120**; **$30 de reserva sin usar**.
Todo vía `api.meta.ai/v1`, `max_retries=0`, sin fallback, sin push.

## Llamadas por etapa

| Etapa | Llamadas | Composición | Costo real estimado |
|---|---|---|---|
| A | 8 | SAM (sondas ES/EN, shelf) | no registrado en `run.json` |
| B | 14 | 7 SAM + 5 Spark + 2 Image | ≈ $0.10 |
| C1 (pipeline x3, n=3) | 27 | 21 SAM + 3 Spark + 3 Image | ≈ $0.20 |
| C2 (robustez x4 escenas) | 37 | 28 SAM + 5 Spark + 4 Image | ≈ $0.27 |
| VIDEO (demo final, voz real) | 11 | 7 SAM + 1 Voice + 2 Spark + 1 Image | ≈ $0.35 |
| **Total declarado** | **96** | cifra del ledger acumulado en `bridge/para_meta.md` | **≈ $0.92 (suma de etapas con estimación) + A sin registrar** |

### Conciliación (declarada, no ocultada)
- La suma aritmética de la tabla (8+14+27+37+11) da **97**, no 96. El ledger de `para_meta.md` registra "A+B = 21" (no 22), de ahí el 96.
- `runs/002/B/run.json` registra **20** llamadas nuevas en B porque incluye el reintento Spark 3500 (+5 Spark, +1 Image = 6) hecho después del cierre de B original (commit `491e8db`). Con ese reintento el total sería 102–103.
- Por tanto **96 es la cifra del ledger; el conteo exacto está entre 96 y 103** y no se pudo cerrar con certeza desde los artefactos. Ningún valor cambia el límite: el gasto real está muy por debajo del tope.
- El costo "$0.35" corresponde a la etapa VIDEO, no al acumulado. Los costos son **estimaciones** por tarifa de llamada, no facturación de Meta.

## Latencias de cadena (SAM+Spark+Image)

| Etapa | Latencia |
|---|---|
| B (n=1) | 27.28 s |
| C1 (n=3) | 28.72 / 29.28 / 38.93 s — **p50 29.28 s, p90 37.91 s** |
| C2 (n=1 x4) | 36.42 / 30.36 / 40.33 / 30.14 s (suma 137.25 s) |
| VIDEO (n=1) | **55.69 s** (SAM ~9 + Voice 3.18 + Spark 12.41+11.62 + Image 16.61) |

Con n tan pequeño son cifras orientativas, no estadística.

## Reglas cumplidas
Sin gasto fuera de lo autorizado · `MODEL_API_KEY` solo en `.env` · commits en `feature/fixes-jueces` · **sin push**.
