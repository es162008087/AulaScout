# Respuesta final a jueces — AULA-SCOUT (2026-10-30)

**Track:** Indie developer — Build for Your World · **Rama:** `feature/fixes-jueces` (sin push)

## Qué entregamos
Foto del salón + nota de voz real → **SAM 3.1** detecta materiales → **Spark 1.3** genera planeación de 3 actividades (18-36 meses, Seguridad x3) → **Image 1.0** genera la ficha visual de 3 paneles. Todo por `api.meta.ai/v1`.

## Verificación de artefactos finales (2026-10-30)
| Artefacto | Verificado |
|---|---|
| `out/demo_aulascout.mp4` | 14.0 s, 320 959 B (≈321K), 1280x720 h264 + aac (voz real `nota_humana.m4a`) |
| `runs/002/VIDEO/ficha.png` | 976 966 B (≈977K); 3 paneles "Actividad 1 / 2 / 3" revisados visualmente |
| `runs/002/VIDEO/planeacion.md` | 3 actividades x 20 min, Seguridad x3, edad 18-36 m |
| Validación humana | Álvaro validó el video con la ficha de 3 paneles |

## Resultados
- **96 llamadas** en total (A 8 · B 14 · C1 27 · C2 37 · VIDEO 11), costo real estimado de centavos de USD; acumulado autorizado $90/$120. Detalle y conciliación en `PRESUPUESTO_FINAL_90USD.md`.
- **SAM 3.1:** 30 cajas / 30 máscaras en cada corrida (mat 1, wooden_blocks 20, sensory_balls 2, low_shelf 2, white_trays 5, fabric_books 0).
- **Latencia cadena:** C1 **p50 29.28 s / p90 37.91 s** (n=3); C2 30–40 s por escena; VIDEO **55.69 s** (n=1, incluye Voice).
- **Voz real:** transcripción "Tengo tapete de foami y bloques de madera. Pero no tengo libros de tela. Tengo canasta con pelotas." La negación se conservó como `VOZ-NEG-01` (`material_voz_negado`, 0 instancias).

## Límites honestos
1. **Títulos genéricos:** Image/Spark devuelven "Actividad 1/2/3" (en e1/e4 de C2 y en VIDEO), con temperatura 0 (determinista); no se regeneró para no gastar llamadas.
2. **Actividad 3 usa `fabric_books` (0 detecciones) pese a la negación por voz `VOZ-NEG-01`:** Spark ignoró la nota de exclusión. Es una falla del plan generado, no un material presente.
3. **Ilustraciones de la ficha genéricas:** los paneles muestran figuras decorativas (formas, patitos, conejo) sin relación visible con los materiales del salón; la ficha cumple "3 paneles", no "ilustra los materiales".
4. **`nota_humana.m4a` dura 13.7 s**, fuera de la ventana 5-7 s prevista; se usó íntegra.
5. **Spark gasta reasoning oculto:** con `max_tokens` bajo trunca (`length`); se requirió 3500 y a veces reintentar (VIDEO: 2 intentos).
6. **SAM sensible a idioma:** conceptos en español dan 0, en inglés detectan el mismo objeto.
7. **Latencias con n pequeño** (n=1 en B, C2, VIDEO; n=3 en C1): orientativas.
8. **Conteo de llamadas:** 96 es la cifra del ledger; la suma aritmética de la tabla y el `run.json` de B difieren (ver conciliación en el presupuesto).

## Paquete
`paquete_final_AULA-SCOUT_2026-10-30.zip`: `runs/002/`, `out/`, `salon.jpg`, `nota_humana.m4a`, `bridge/para_meta.md`, `revision_jueces/`.
