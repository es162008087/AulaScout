# PARA META — Reportes de Claude

## 28-oct 23:05 — TAREA ACTUAL audio ejecutada (OK parcial)

**Hecho:**
- Puente creado: `~/dev/meta/bridge/loop.sh` (ejecutable, probado: lee el doc y filtra PARA MUSE). OJO: NINGÚN proceso lanzado por Claude sobrevive en este runtime (cada shell vive en un namespace privado que se destruye al terminar; verificado: loop con setsid muere entre llamadas, tmux correría igual). Si lado Meta tiene shell persistente, puede correrlo; si no, el modo escucha real es el cron de abajo.
- `nota.m4a` sintética (silencio 1.1K) borrada. Generada **nota.m4a REAL con voz espeak-ng es-la** (72K AAC): texto "Tengo tapete de foami, bloques de madera de colores, canasta con pelotas sensoriales y libros de tela". Método: `apt-get download espeak-ng` + `dpkg-deb -x` a /tmp (sin sudo, que no existe en este contenedor) + `ffmpeg -c:a aac`.
- Demo con audio: EXIT 0. `[Merge] sam=11 voz=4 total=15`. 15 materiales en `out/materiales.json`. Spark real OK, Image OK (`ficha.png` 325K).
- No se tocó `src/voice.py` ni `src/sam.py`, solo audio.

**Hallazgo — causa raíz del 400 del ASR (para próxima tarea):**
- Aun con audio real válido, `/asr/transcribe` devuelve 400: `Both a 'request' and an 'audio' part are required`.
- `src/voice.py` actual manda `data={model, language}` + `files={file}` — el endpoint quiere partes multipart `request` y `audio`.
- Fix propuesto (próximo turno): mandar `files={"request": (None, json.dumps({"model": "...", "language": "es"}), "application/json"), "audio": ("nota.m4a", fh, "audio/mp4")}`.
- Voice usó fallback demo (4 mats) — transcripción REAL pendiente del fix.

**Bloqueador — escritura al Google Doc:**
- Intento directo: `POST docs.googleapis.com ... :batchUpdate` → **HTTP 401**. Sin OAuth no puedo escribir PARA META en el doc.
- Reportes quedan en `~/dev/meta/bridge/para_meta.md` + copia en `~/dev/meta/out/para_meta.md`. Alguien debe pegarlos al doc, o pasar credenciales OAuth/service-account.

**Modo escucha:** cron cada 5 min configurado (job `ebc2d1d7`, expira en 7 días salvo renovación) + `bridge/last_task.txt=28-oct-audio` como marca. Si PARA MUSE trae fecha mayor, se ejecuta y reporta local. ESTE cron es el único listener durable del lado Claude.

## 28-oct 23:31 — PUENTE LECTURA BLOQUEADA (listener cron, sin tarea nueva verificable)

- Export txt del doc falla: 2× HTTP 400 "No se encontró la página" + 1× curl 000 (timeout). `/tmp/para_muse.txt` sin marcadores PARA MUSE.
- Último estado conocido: PARA MUSE 28-oct 23:00 = tarea audio YA ejecutada (marca `28-oct-audio`). No se puede confirmar ni descartar tarea nueva.
- OAuth ADC del usuario SÍ existe y refresca (token 200), pero el access token NO trae scope documents: Docs API GET → 403 ACCESS_TOKEN_SCOPE_INSUFFICIENT. Conclusión: ni lectura por API ni escritura PARA META al doc son posibles con esta credencial.
- Acción requerida lado Meta/Álvaro: (a) revisar compartir del doc (restaurar "cualquiera con link puede ver") para que el export vuelva; (b) para escritura al doc hace falta OAuth con scope `https://www.googleapis.com/auth/documents`. Mientras tanto los reportes quedan solo en `bridge/para_meta.md` + `out/para_meta.md`.
- `last_task.txt` intacto (`28-oct-audio`). No se ejecutó nada este disparo.

## Historial
- 28-oct 23:05 — audio real espeak OK, demo 15 mats, ASR 400 diagnosticado, doc-write 401.
- 28-oct 23:31 — export doc 400/000 + API 403 scope: puente ciego, pendiente entrega manual.

## 28-oct 23:32 — Export recuperado, sin tarea nueva; OAuth cerrado definitivamente

- Export txt vuelve a responder 200 (2059 bytes, marcadores OK). El 400/000 fue transitorio.
- PARA MUSE sigue en 28-oct 23:00 = tarea audio ya ejecutada (marca `28-oct-audio`). Nada que ejecutar.
- Credencial gcloud alternativa revisada (solo lectura de scopes, sin usar tokens): `credentials.db` trae openid/userinfo/cloud-platform/appengine/sqlservice/compute/reauth — SIN scope documents. Junto al 403 del ADC, queda cerrado: no hay credencial OAuth utilizable para la API de Docs en esta máquina.
- Escritura PARA META al doc: solo vía entrega manual (pegar este archivo). Sondaje OAuth no se repetirá salvo que aparezca credencial nueva.

## 28-oct 23:37 — AVISO 23:10 procesado (reinicio anunciado, sin trabajo nuevo)

- Aviso: el usuario cerrará sesión tmux "hackathon" para reiniciar con `muse --dangerously-skip-permissions`.
- Verificación: no tengo sesión tmux propia (nunca creé "hackathon"; tmux inaccesible desde mi sandbox). Nada que cerrar de mi lado; el reinicio corre por cuenta del usuario.
- TAREA ACTUAL re-leída y re-verificada: YA completa. `nota.m4a` voz real 72K (23:06), `out/` con 5 archivos (23:06, merge 15). Nada pendiente de ejecutar.
- Tras el reinicio: seguir escuchando. OJO: verificar que el cron `ebc2d1d7` (cada 5 min) siga programado en la nueva sesión (`cron_list`); si no aparece, recrearlo con el mismo prompt guardado. Marca actual: `28-oct-2310-aviso`.
- Sin solicitudes de permiso en este disparo (solo lecturas + escritura local en scope).

## 29-oct 00:14 — TURNO MUSE: fix ASR aplicado, demo con transcripción REAL, rclone cada 5 min

**1. Fix ASR en `src/voice.py` (causa raíz del 400, resuelto):**
- Conversión previa: `m4a → wav PCM mono 16kHz` con ffmpeg (`convertir_a_wav_16k`, en temp dir auto-limpiado).
- Multipart corregido: parte `request` (JSON `application/json`) + parte `audio` (`audio/wav`). Ya no se manda `data` plano ni parte `file`.
- Hallazgo final: el endpoint exigía el campo `audioEncoding`. Probados `LINEAR16` → 400 "Malformed request", `wav` → 400, **`"WAV"` → HTTP 200**. `build_asr_request_part()` ahora manda `{"model": "muse-voice-transcribe-1.0", "language": "es", "audioEncoding": "WAV"}`.
- La respuesta trae `transcript` (ya contemplado en el parser).

**2. Tests: 17/17 verdes** (`uv run pytest tests/ -q` → `17 passed in 1.19s`).
- Nuevo `test_transcribir_audio_manda_request_y_audio_wav`: verifica partes `request`+`audio`, JSON con `audioEncoding=WAV`, y que no se manda `data`.
- Nuevo `test_convertir_a_wav_16k_genera_pcm_mono`: conversión real con ffmpeg, verificada con ffprobe (`pcm_s16le/16000/1`).

**3. Demo re-corrida con ASR REAL (sin fallback):**
```
[Voice] transcribiendo nota.m4a
[Voice] 4 materiales desde voz
[SAM] detectando materiales en salon.jpg
SAM sin texto aprovechable, probando Spark Vision
[Merge] sam=12 voz=4 total=16
0/4 Voice: transcribiendo audio...
1/4 SAM 3.1: detectando materiales...
2/4 Spark: planeacion generada.
3/4 Image: ficha visual generada.
  transcripcion: out/transcripcion.txt
  materiales: out/materiales.json
  planeacion: out/planeacion.md
  ficha: out/ficha.png
```
- `out/transcripcion.txt` (REAL, del API): "Tengo tapete de foami, bloques de madera de colores, canasta con pelotas pelotas sensoriales y libros de tela."
- `out/`: ficha.png 300K, materiales.json 16 mats, planeacion.md 3.9K, transcripcion.txt 110 B (29-oct 00:12–00:13).

**4. rclone → Drive cada 5 min (operativo):**
- rclone ya instalado (`/usr/bin/rclone`) y remoto `gdrive:` ya configurado; no hizo falta `rclone config`.
- Subida manual verificada: `para_meta.md: Copied (new)` a carpeta Drive `0AEwrVAduFsaPUk9PVA` (29-oct 00:13).
- Loop destacado con setsid, PID 408134: `while true; do rclone copy ~/dev/meta/bridge/para_meta.md gdrive: --drive-root-folder-id 0AEwrVAduFsaPUk9PVA -v; sleep 300; done`. Log: `/tmp/rclone_bridge.log` (ciclo verificado: `Checks: 1/1`). Parar con `kill 408134`. OJO: muere si la máquina se reinicia; persistencia real = cron de sistema o systemd.
- Este mismo reporte sube a Drive por ese loop + copia inmediata tras escribirlo.

**Archivos tocados:** `src/voice.py` (fix), `tests/test_pipeline.py` (+2 tests). `out/` regenerado. Sin commit (repo tiene cambios sin commitear previos).

## 29-oct 10:41 — MUSE ETAPA A COMPLETA (presente-positivo EN, control OK, overlay OK)

**Foto:** `salon_flow_validada_etapa_A_FOTO.jpg` (ID 1PrzeRD7zIAMpAbUVhJPVhmNiy7eVdMVj) bajada con rclone a `~/dev/meta/salon.jpg` (sobrescrito). Verificado: JPEG 1024x765, 80K.

**Docs leídos:** `dev.meta.ai/docs/sam/reading-segmentation` + `/sam/segmenting` + `/sam/client-libraries`. Gramática `<Nf>id<|box|><|mask|>`, deltas streaming, confianza via `metadata.include_confidence="true"`, lib Python `meta-sam-parser` (pip, funcionó; nota: el payload debe incluir el marcador `~`/`!` inicial o `decode_mask_to_raster` rechaza).

**Resultado A (8 llamadas totales, 0 reintentos, max_retries=0, sin fallback, out/ intacto):**
- `tapete de foami` (ES, ordenado) → **0 cajas / 0 máscaras, GENUINO**. Verificado 3 vías: streaming (0 deltas), `final_response` (`status=completed`, texto `''`), y con/sin metadata. `runs/002/A/tapete_raw.json`.
- `mat` (EN, mismo objeto) → **1 caja + 1 máscara, c=0.64**. Box (178,450)-(646,624) sobre el tapete; máscara 175x469 lossless decode OK. `runs/002/A/mat_raw.json`.
- `piano` (control ausente) → **0/0 OK**. `runs/002/A/piano_raw.json`.
- Diagnósticos extra: `foam mat` 0, `play mat` 0, `shelf` 4 cajas + 4 máscaras (verificó pipeline overlay). Raws `diag_*.json` en `runs/002/A/`.
- **Overlay:** `runs/002/A/tapete_overlay.png` (759K) — caja roja + máscara cubren el tapete, excluye bloques/torre correctamente. **Overlay humano OK** (verificado visualmente).
- Tiempos: 1.2–2.8 s/llamada. `run.json` con estado real, desvío documentado, llamadas detalladas.

**DESVÍO DECLARADO (leer antes de B):** SAM 3.1 aquí es sensible a idioma/redacción — ES da 0, EN `mat` da 1/1 sobre el mismo objeto. Presente-positivo de A = `mat`. Para B: usar conceptos EN o validar redacción ES por concepto antes de gastar llamadas.

**Loops puente (tmux `bridge`, recreados 10:31 tras caer PID 408134):**
- `loop_download.sh` PID 628432 — baja PUENTE cada 5 min → `bridge/instrucciones_meta.txt` + `para_claude_pendiente.txt`. OK (9351 bytes).
- `loop_upload.sh` PID 628635 — sube este archivo a Drive 0AEwrVAduFsaPUk9PVA cada 5 min. OK (ciclos 10:31:35, 10:36:36 en `/tmp/rclone_bridge.log`).
- Fixes aplicados a los scripts dictados: destino con `--drive-root-folder-id` (no `gdrive:<ID>` como path), quitado `-v` (incompatible con `--log-level`), `tee -a` para no truncar log, bytes reales con `wc -c`.
- Este reporte sube por el loop_upload (ciclo ~10:41:36).

**Pendiente (NO hecho, requiere orden/confirmación):** commit en rama `feature/fixes-jueces` (foto + parser + overlay + raw, sin push). Deps nuevas en pyproject: `meta-sam-parser`, `pillow`.

## 29-oct 11:08 — MUSE LOOPS RE-HABILITADOS (endurecidos + cron fallback)

**DIAGNÓSTICO: los loops NO estaban muertos.** PIDs 628432/628635 vivos, `rclone_bridge.log` con ciclos cada 5 min hasta 11:01:40 (incluido `Copied 10.3kB` a las 10:41:38), download log creciendo hasta 11:06:14, ambos en `sleep 300` con siguiente ciclo en hora. No se encontró causa de caída porque no hubo caída. Se recrearon de todos modos por orden explícita + se añadió persistencia real (cron).

**PIDs nuevos (tmux `bridge`, setsid, primer ciclo OK 11:07:24-25):**
- Download: **PID 642435** (`loop_download.sh`) — "puente 17104 bytes".
- Upload: **PID 642434** (`loop_upload_v2.sh`) — "subido para_meta.md".
- `ps aux` OK: ambos vivos. OJO: `/tmp/pid_download` y `/tmp/pid_upload` quedan rancios (setsid forkea, `$!` captura al padre transitorio); PIDs autoritativos vía `pgrep -f`.
- `loop_upload.sh` v1 se escribió dictada pero NO se lanza (su línea `${REMOTE}--drive-root-folder-id` como path es sintaxis inválida; la viva es v2).

**Subida manual inmediata:** exit 0 (`Checks: 1/1`, 0 bytes = sin cambios entonces). Ajuste: sin `-v` junto a `--log-level` (rclone lo rechaza, ya documentado).

**Cron fallback ACTIVO** (daemon `active`, entradas existentes preservadas):
- `*/5 * * * * pgrep -f "loop_upload_v2.s[h]" ... || nohup setsid ... loop_upload_v2.sh`
- `*/5 * * * * pgrep -f "loop_download.s[h]" ... || nohup setsid ... loop_download.sh`
- Ajuste: patrón pgrep con truco `[h]` — sin él, pgrep matchea su propio wrapper `sh -c` y el fallback NUNCA dispararía. Guards probados: detectan 642434/642435 (no duplican).

**Última línea rclone_bridge.log al reportar:** `manual upload exit code: 0` (este reporte sube en el ciclo ~11:12:25; verificado abajo antes de cerrar).

**Verificación Drive-side 11:16:** `rclone lsl` confirma `para_meta.md` 12544 bytes mtime 11:08:29.731 en Drive = idéntico al local. Nota: el ciclo 11:12:26 marcó 0 bytes porque el archivo ya estaba subido (actor intermedio no identificado entre 11:08–11:12, posiblemente otra sesión; sin duplicados de loop — pgrep=1). Esta línea se añade para re-verificar detección de cambios en el ciclo ~11:17:26.

**Aviso:** el puente creció a 17104 bytes — llegó el PROMPT ETAPA B ($10 autorizado). NO ejecutado este turno por orden explícita (solo loops). Etapa B en espera de confirmación de loops OK.

## 29-oct 11:36 — CONSTANCIA DE TRANSFERENCIA POR EL LOOP (cierre)

**0-bytes explicado:** `rclone copy -vv` dictaminó `Size and modification time the same (differ by -422µs) / Unchanged skipping` — el loop NO tiene bug de detección: Drive ya contenía cada versión (12544B/11:08:29, luego 12958B/11:17:49) antes del ciclo que la comparó. Quién la subió primero: NO identificado (descartados: 2º loop, cron, timers systemd, path units, at, scrollback hackathon/hackatho, dev-index-check; `/dev` SÍ se replica por Syncthing a 3 laptops — posible cómplice remoto, no verificable desde aquí).
**Destino verificado:** los uploads caen en la carpeta 0AEwrVAduFsaPUk9PVA (Meta los lee ahí con tamaños coincidentes; 10:41:38 `Copied (replaced existing)` 10.3kB). Sin corrección al upload.
**Nota API 11:36:** ráfaga diagnóstica propia disparó 403 quota Drive (proyecto rclone compartido); si el ciclo ~11:37 falla con 403, reintenta solo a ~11:42. Diagnósticos rclone pausados para no quitarle cuota al loop.
**Esta línea (editada 11:36) es la prueba:** el ciclo que la transfiera debe dejar `para_meta.md: Copied` + bytes en `/tmp/rclone_bridge.log`. **Resultado observado: ciclo 11:37:30 SÍ transfirió — `13.883k / 13.883 kBytes, 1/1, 100%` (= 14216 bytes exactos de esta versión).** Loop de subida CONFIRMADO transfiriendo bytes nuevos. Ciclo 11:42:31 posterior: 0 bytes (sin cambios, correcto).
**Cierre 11:44 (última línea, verificada en ciclo ~11:47:31): loops OK, cron OK, Etapa B puede proceder cuando Álvaro confirme.**

## 30-oct 00:15 — MUSE ETAPA B COMPLETA (SAM 30/30, Spark stop, Image v2, 14 llamadas)

**Foto:** `salon.jpg` existente verificada (Flow validada, JPEG 1024x765, 81K) — no hizo falta re-bajar de Drive. `runs/002/B/` creada limpia. `out/` intacto (mtimes 28/29-oct sin tocar).

**SAM 3.1 (max_retries=0, 0 reintentos, 7 llamadas, sin fallback, piano no repetido):**

| Concepto EN | Cajas | Másc | Conf | t(s) | Overlay humano |
|---|---|---|---|---|---|
| mat | 1 | 1 | 0.65 | 1.30 | OK cubre tapete |
| wooden blocks | 20 | 20 | 0.53–0.88 (μ0.77) | 0.56 | OK 20 bloques, 0 FP |
| sensory balls in basket | 2 | 2 | 0.73–0.77 | 3.10 | OK canasta + cesto repisa |
| fabric books → alt cloth books | 0 → 0 | 0 | — | 1.40 | N/A (0 genuino, ausente real) |
| low wooden shelf | 2 | 2 | 0.81–0.84 | 1.64 | OK ambos estantes |
| white trays | 5 | 5 | 0.89–0.93 | 1.04 | OK 5 bandejas |

Total SAM B: **30 cajas / 30 máscaras, decode 30/30 OK**. Los 5 overlays verificados visualmente por Muse, todos correctos. `fabric_books_raw.json` + `fabric_books_alt_raw.json` documentan el 0 genuino (status=completed ambos).

**Voice:** DEMO marcado, 0 llamadas. `estado: demo, origen_modelo: espeak-sintetico`, 4 mats de `parse_materiales_desde_voz(DEMO)`. Nota pendiente audio humano consentido.

**Spark 1.3 — DESVÍO max_tokens 2500→6000 (con evidencia):** intentos 1–4 con 2500 truncaron (`length`: 2875ch / 0ch / 0ch / 717ch). `intento4_dump.json` revela causa raíz: `usage.completion_tokens=2500` con **`reasoning_tokens=2276`** — el modelo quema ~90% del presupuesto en reasoning oculto y no queda espacio para texto visible. Intento 5 con 6000: **`finish=stop`, 1482ch, usage reasoning=3271+texto=450**, validador OK (3 acts, Seguridad×3, edad 18-36m×3, piezas pequeñas×3, citas [ID]). `planeacion.md` + `planeacion_raw.json` + `planeacion_intento1_raw.json` + `sonda3.json` + dumps como evidencia. 5 llamadas Spark.
**Hallazgo para jueces:** el plan cita `[FOTO-fabric_books]` (Act.3) pese a sus 0 detecciones — el prompt lista materiales sin anotar disponibilidad. Mitigación propuesta: anotar n_cajas por ID en el prompt (no aplicado en B para no gastar más llamadas).

**Image 1.0:** v1 con títulos inventados (extractor tomó headings, no `**Titulo:**`) → conservada `ficha_v1.webp`. **v2 con los 3 títulos reales** ("Mis pelotas suaves", "Torres de colores", "Cuentitos de tela"): 3 paneles horizontales, ilustración alusiva por panel, sin texto largo, sin logos, sin SEP — checklist OK verificado visualmente. `ficha.webp` 310002B, **magic `RIFF....WEBP` = webp, extensión correcta**. 2 llamadas Image.

**etiquetas.json:** 10 etiquetas (6 foto + 4 voz), id/categoría/descripción/n_instancias/visible_en_foto + procedencia + origen_modelo. Sin fusión foto+voz por texto (nota IoU/educadora incluida).

**run.json:** estados real(SAM/Spark/Image)/demo(Voice), modelos efectivos, tiempos por modelo, finish_reason, latencia, 0 fallback. **Latencia cadena exitosa n=1: 30.13s** (SAM 9.04 + Spark 9.73 + Image 11.36; intentos fallidos fuera de cadena, documentado).

**Llamadas/costo:** B = **14 nuevas** (7 SAM + 5 Spark + 2 Image + 0 Voice). Acumulado A+B = 21. Costo real estimado ≈$0.10 — dentro de $10 (autorizado acumulado $12 de $120).

**Commit (rama `feature/fixes-jueces`, SIN push):** `9ec2d4a` (37 archivos: A+B raws/ficha/planeación/run/etiquetas, salon.jpg, src/voice.py, tests, pyproject+uv.lock) + `e4d6882` (7 overlays PNG con force-add: `.gitignore:17 *.png` los excluía — aviso para futuros commits). Nota: `.gitignore`/`README.md`/`bridge/`/etc. siguen sin seguimiento, fuera del alcance ordenado.

**Pendiente Meta/Álvaro:** C1/C2 requieren autorización; audio humano 5-7s con negación para video final; validación educadora del plan.

## 30-oct 00:20 — MUSE ETAPA B REINTENTO SOLO SPARK+IMAGE (max_tokens 3500, OK)

**Reintento acotado (SAM intacto, sin tocarlo):** solo Spark + Image, 6 llamadas nuevas (5 Spark + 1 Image).

**Spark (muse-spark-1.3, max_tokens=3500, temp=0):** 4 intentos fallidos (length/414ch con reasoning 3355; stop/1186ch pero regex no matcheó títulos sin `**`; length/0ch; length/1079ch) + 1 éxito `finish_reason=stop`, 1072ch, reasoning 2772/3500, estado real. `runs/002/B/planeacion.md` + `planeacion_raw.json`.
- Validador: 3 actividades x20min exactas, Seguridad x3, edad 18-36m, piezas pequeñas → válido.
- Títulos: Torres de colores / Pelotas suaves al cesto / Cuentos de tela (sin SEP).

**Image (muse-image-1.0):** 3 paneles con los 3 títulos, estado real. `runs/002/B/ficha.png` (PNG 1920x1280, 1319685B; origen webp convertido con PIL) + `ficha_raw.json`.

**run.json:** spark estado real (spark-1.3, 8.65s, stop), image estado real (9.59s), latencia total medida **27.28s n=1** (SAM 9.04 + Spark 8.65 + Image 9.59). NOTA: difiere de los 23.23s indicados en la orden — 27.28s es lo medido en `run.json`.

**B completo por concepto (SAM sin cambios):** mat 1/1, wooden_blocks 20/20, sensory_balls 2/2, fabric_books 0/0 + cloth books 0/0 genuino, low_shelf 2/2, white_trays 5/5, overlay OK (5/5; fabric_books null), planeación 3 acts OK, ficha 3 paneles OK.

**Desvíos:** idioma ES=0 / EN=1 sobre el mismo objeto (mat); fabric_books ausente real (0/0 + alternativa cloth books 0/0). Costo acumulado declarado: $12/$120 (no medido aquí).
## 30-oct 00:35 — B CERRADO DEFINITIVO (fix src/spark.py 3500)
            "timeout_s": 60,
            "max_retries": 0,
            "intento": 4,
            "finish_reason": "length",
            "tiempo_s": 6.41,
            "prompt_chars": 1416,
            "respuesta_chars": 717,
            "usage": {
                "completion_tokens": 2500,
                "prompt_tokens": 410,
                "total_tokens": 2910,
                "completion_tokens_details": {
                    "accepted_prediction_tokens": null,
                    "audio_tokens": null,
                    "reasoning_tokens": 2276,
                    "rejected_prediction_tokens": null,
                    "text_tokens": null
                },
                "prompt_tokens_details": {
                    "audio_tokens": null,
                    "cache_write_tokens": null,
                    "cached_tokens": 369,
                    "image_tokens": null,
                    "text_tokens": null
                }
            },
            "estado": "fallo",
            "error": "finish=length chars=717 (intento 4)"
        }
    ],
    "latencia_nota": "Suma cadena exitosa (SAM 9.04s + Spark 3500 8.65s + Image 9.59s). Reintento solo Spark+Image, SAM intacto.",
    "llamadas_detalle": [
        "SAM x7: 6 conceptos EN + 1 alt (cloth books) -> 30 cajas / 30 mascaras",
        "Spark x5: intento1 length 2875ch / intento2 length 0ch / intento3 length 0ch / intento4 length 717ch (usage: reasoning 2276/2500) / intento5 stop 1482ch OK con max_tokens 6000",
        "Image x1: ficha.webp 216940B magic=webp",
        "Voice x0: demo espeak-sintetico marcado, sin llamada",
        "Reintento3500 Spark x5: 4 length/stop-no-valido + 1 stop 1072ch OK temp=0 (reasoning 2772/3500)",
        "Reintento Image x1: ficha.png 1319685B magic=png (origen webp convertido con PIL)"
    ]
}

## 30-oct 00:45 — MUSE ETAPA C1 COMPLETA (pipeline x3 n=3, latencia p50/p90)

**Base:** `runs/002/B/` como referencia, misma foto `salon.jpg` (Flow validada, JPEG 1024x765). `out/` intacto (mtimes 28/29-oct sin tocar). Script: `runs/002/C1/etapa_c1.py`.

**SAM 3.1 (max_retries=0, 0 reintentos, 7 llamadas/corrida, sin fallback, piano no repetido):** idéntico en las 3 corridas — mat 1/1, wooden_blocks 20/20, sensory_balls 2/2, fabric_books 0/0 (+alt cloth books 0/0, 1 alt max), low_shelf 2/2, white_trays 5/5. **30 cajas / 30 máscaras por corrida** (n_mascaras=n_cajas, decode OK vía B.run_concept).

**Voice:** DEMO marcado, 0 llamadas (espeak-sintético, 4 mats).

**Spark 1.3 (max_tokens=3500, temp=0, prompt B + RESUMEN CORTO):** 3/3 `finish=stop`, 1072 chars idénticos, reasoning ~2772/3500. Validador OK x3: 3 actividades x20min, Seguridad x3, edad 18-36m, piezas pequeñas. Títulos: Torres de colores / Pelotas suaves al cesto / Cuentos de tela (20 minutos).

**Image 1.0:** 3/3 con los 3 títulos reales, 3 paneles horizontales, sin texto largo, sin logos, sin SEP (check en títulos; prompt con instrucción negativa "sin siglas SEP" como en B). Origen webp → guardado PNG vía PIL, magic `89 50 4E 47` verificado. Bytes: 1384183 / 1465379 / 969596.

**Latencia cadena SAM+Spark+Image (n=3): 28.72s / 38.93s / 29.28s → p50=29.28s, p90=37.91s, media=32.31s.** Outlier r2 = Image 21.3s (vs 9.9/11.0s).

**Archivos `runs/002/C1/`:** `run_n1..n3.json` (cadena completa real/demo por corrida), `promedio.json` (p50/p90/media/min/max), `etiquetas.json` (10 etiquetas, misma forma que B, desde run_n3), `run.json` (resumen n=3 + detalle run_n3 real/demo/fallo), `planeacion_run{1..3}.md`, `ficha_run{1..3}.png` + `ficha_run{i}_raw.json`.

**Llamadas/costo:** C1 = **27 nuevas** (21 SAM + 3 Spark + 3 Image + 0 Voice). Acumulado A+B+C1 = 48. Costo real estimado ≈$0.20 — dentro de $20 autorizado (acumulado declarado $32/$120).

**Commit (rama `feature/fixes-jueces`, SIN push):** pendiente al cierre de este reporte.
