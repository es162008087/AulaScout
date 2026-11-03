# Guion demo 2 minutos

## 0:00–0:20 — Problema
Educadoras de lactantes/maternal pierden horas planeando con lo que hay en el salón.
Mostramos la foto del salón real.

## 0:20–0:50 — SAM 3.1
`demo.py` manda la foto a SAM 3.1 vía `api.meta.ai/v1`.
En pantalla: `materiales.json` con lo detectado (bloques, pelotas, mantas...).

## 0:50–1:30 — Spark
Spark genera la planeación de **3 actividades SEP** desde esos materiales.
En pantalla: `planeacion.md` (título, edad, duración, pasos, seguridad).

## 1:30–2:00 — Image + cierre
Image genera `ficha.png` lista para pegar en el aula.
Cierre: 3 modelos Meta nativos, un solo comando, caso real.

## Comando

```bash
uv run python demo.py --foto salon.jpg --salida out/
```

## Si algo falla en vivo
- Sin key: el error dice exactamente qué falta (`MODEL_API_KEY` en `.env`).
- Sin red: mostrar `out/` de un ensayo previo y narrar los 3 pasos.
