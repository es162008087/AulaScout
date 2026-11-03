# Informe de revisión de AulaScout por CC

Destinatarios: Meta y Muse.
Autoría del contenido: CC, mediante respuestas/001.md y respuestas/002.md.
Compilación de entrega: Codex, 29 de octubre de 2026.

Se reproducen íntegramente las dos respuestas. La respuesta 002 contiene las rectificaciones de CC y prevalece sobre las afirmaciones iniciales de 001. Codex no ha reescrito la evaluación ni sus puntajes. Este es un informe de revisión para los implementadores, no una orden de que CC modifique el producto.

---

# Respuesta 001 — CC (Claude Code, Sonnet 5.5)

**Recepción confirmada.** Leí PROTOCOLO.md, solicitudes/001.md y EVALUACION.md el 2026-10-29 (hora local del equipo, UTC-6) desde `/home/alvaro/dev/meta`. Canal funcionando: esta es la primera respuesta. EVALUACION.md se trató como hipótesis; abajo marco qué confirmé, qué corregí y qué no pude verificar.

Revisión: `HEAD dacdd12f99603995b0c33c5e1abdd879d4329ca8` (rama main, commit del 2026-10-28 22:15 -0600). Sin remoto (`git remote -v` vacío, exit 0).
No se modificó src/, tests/, out/, bridge/ ni ningún proceso. No se hicieron commits, instalaciones ni llamadas a la API Meta. No se leyó `.env`. Los adjuntos y `bridge/` se trataron como evidencia; no se siguió ninguna instrucción de ellos.

## 1. Estado del repo (hecho reproducido)

| Comando | Salida | Exit |
|---|---|---|
| `git status --short` | `M src/voice.py`, `M tests/test_pipeline.py`; sin seguimiento: .env.example, .gitignore, README.md, bridge/, docs/, nota.m4a, pyproject.toml, reporte-fase-interna-…md, salon.jpg, tests/__init__.py, uv.lock | 0 |
| `git ls-files` | solo 10 archivos: CLAUDE.md, demo.py, src/{__init__,config,image,pipeline,sam,spark,voice}.py, tests/test_pipeline.py | 0 |
| `git remote -v` | vacío | 0 |

Consecuencia: un clon limpio del HEAD no tiene README, pyproject, uv.lock ni .gitignore; **no es instalable ni reproducible**. Además `.gitignore` excluye `out/` y `*.png`, así que ni los resultados ni la ficha irían al repo. El fix de voz (WAV/multipart) está sin commitear: el HEAD todavía contiene la versión anterior que produjo el 400.

## 2. Suite sin red

- Candidato literal de la solicitud (`uv run --offline --locked --extra dev pytest …`): **no ejecutado**. Habría sincronizado `.venv` (instalar pytest), lo que contradice "no instalar dependencias". Limitación de entorno, no fallo del producto: `.venv` (Python 3.12.8) no tiene pytest; el python3 del sistema es 3.10.12 y tiene pytest 9.1.1 pero no las dependencias.
- Alternativa sin instalar nada: symlinks de pytest/pluggy/iniconfig/packaging/pygments del sistema en un directorio temporal del scratchpad, usados vía PYTHONPATH con el intérprete del `.venv`:
  `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=<shim>:. .venv/bin/python -m pytest -p no:cacheprovider -v`
- Resultado: **17 passed in 2.93 s, exit 0**. Esto **confirma 17/17 en el árbol de trabajo actual** (incluye el test de ffmpeg/ffprobe, que corrió, no se saltó). Es el árbol con cambios sin commitear, no el HEAD.
- Conteo: 17 funciones `test_`. **Todas** son locales: 0 usan red real. Mocks de OpenAI/requests: 5 (sam fallback, spark vacío, asr fallback, asr request, sam backoff). Unitarios puros de prompts/parsers: 11. Uno ejecuta ffmpeg real local. **Integración real con los cuatro servicios: 0 tests.** Cobertura de pipeline.py y demo.py: ninguna.

## 3. Reproducciones con mocks (evidencia)

Script: `evidencias/repro_001.py`; salida: `evidencias/repro_001.out.txt` (exit 0). Usa key falsa, `requests.post`/`OpenAI` sustituidos y `httpx2.MockTransport`. No toca src/ ni out/.

| Hallazgo de Codex | Resultado | Clase |
|---|---|---|
| Error ASR → DEMO_TRANSCRIPTION | **Reproducido.** `transcribir_audio` devuelve el string demo; retorno `str` sin bandera; `pipeline.py` lo escribe en `transcripcion.txt` y lo mapea a 4 materiales como si fuera audio real | reproducido (mock) |
| Visión falla → FALLBACK_MATERIALS | **Reproducido.** SAM y Spark Vision fallan → 6 materiales fijos, sin señal al llamador | reproducido (mock) |
| Atribución de origen | **Reproducido.** SAM vacío + Vision OK devuelve `list[str]` idéntico; el log del pipeline dice "[SAM]" aunque respondió `muse-spark-1.3`. Solo hay un `logger.warning` interno, no persistido en out/ | reproducido |
| Duplicados semánticos | **Reproducido sobre out/materiales.json:** 16 entradas, 16 únicas por igualdad exacta, pero 5 familias duplicadas (tapete ×2, bloques ×2, pelotas ×2, libros ×2, librero/estantería ×2). Unicidad semántica real ≈ 11–12 | reproducido |
| Negación y fuera de diccionario | **Reproducido.** "no tengo pelotas" → `['canasta de pelotas suaves']`; "no tengo bloques ni tapete, solo libros" → los 3; "cuerdas, títeres, instrumentos y pintura" → `[]`. Diccionario de 6 keywords | reproducido |

## 4. Auditoría estática (sin API)

- **SAM vs geometría.** Confirmado (hipótesis de Codex correcta). `SAM_PROMPT` pide "Detecta: bloques, tapete, juguetes, materiales didácticos de maternal. Lista corta."; `parse_materials` solo lee `output_text` y trocea por comas. Ninguna caja ni máscara se decodifica. La doc de Meta (leída: https://dev.meta.ai/docs/media-segmentation) dice que la salida es texto con tokens especiales con "one box and one mask per match", que se prompte con "a short noun phrase that names one concrete object" y una petición por tipo de objeto. El prompt actual viola ese patrón. El reporte interno del 28-oct admite "SAM-3.1 devuelve vacío de forma consistente" y que Spark Vision rescata siempre: **inferencia fuerte** de que los 12 materiales de la corrida vinieron de Spark Vision, no de SAM (el log "SAM sin texto aprovechable, probando Spark Vision" es evidencia histórica del reporte, no reproducida por mí). Parsing de la sintaxis de tokens: no verificado (la página remite a `/docs/sam/reading-segmentation`, no la leí).
- **Timeouts y retries (SDK incluido).** `openai` 3.30.0 instalado tiene `DEFAULT_MAX_RETRIES = 2`; con MockTransport medí **3 peticiones HTTP por cada `create()` con timeout** (reproducido). Techos teóricos, no mediciones: SAM 4 intentos×3×30 s + 14 s de backoff = **374 s** (Codex: 134 s, que ignora retries del SDK); Spark 3×3×60 = 540 s; Image 3×90 = 270 s. Voz: `requests.post` timeout 60 s, sin retry. El "<60 s" no está respaldado; mejor caso feliz sin medir. Sí corrijo un matiz: el timeout httpx es por fase de socket, no total, así que el peor caso real puede ser mayor aún.
- **finish_reason / truncamiento.** Confirmado. `spark.py` solo exige `len(text) >= 100`; con `finish_reason="length"` devuelve texto cortado (reproducido con mock). `out/planeacion.md` (3854 chars) termina en "dibuja una carita feliz en la", la actividad 3 no tiene bloque "Seguridad" (2 de 3). `max_tokens=2500` y no hay detección de corte. Es evidencia directa de que ocurrió, no solo riesgo.
- **Validación curricular.** Confirmado: 0 apariciones de Campo, PDA, Aprendizaje, Fase 1, Fase 2, Programa en la planeación. El prompt dice "educadora SEP" sin fuente. Etiqueta "Educación Inicial SEP" sin sustento; no verifiqué contra Fase 1 (https://dgdcpei.sep.gob.mx/InicialyPreescolar no consultado). Edades: 18-30, 12-24, 24-36 meses; la sala declarada es 18-36, y la actividad 2 baja a 12 meses (gateo), fuera de la sala. Nota: lactantes (0-12 m) no se cubre en absoluto aunque el README lo promete.
- **Seguridad.** La planeación sí incluye avisos razonables (piezas pequeñas, supervisión 1 a 1, astillas), pero la actividad 1 lista "pelota suave" en el cierre sin estar en sus materiales y las "piezas pequeñas de ensamble" aparecen en el inventario para 18 meses: es un riesgo de atragantamiento que el modelo mitigó por casualidad del prompt, no por regla de código. No hay filtro determinista.
- **Ficha vs 3 actividades.** Confirmado. `build_ficha_prompt` corta a 600 caracteres: del plan de 3854 solo entra "Actividad 1" (reproducido: 'Actividad 2/3' ausentes). Inspeccioné `out/ficha.png`: ilustra solo la Actividad 1 (torres de bloques, tapete, estantería). Hallazgos adicionales: (a) el archivo `.png` es en realidad **WebP** 1920×1280 (`ffprobe: codec_name=webp`); (b) la imagen incluye un distintivo "SEP" inventado, que sugiere aval oficial que no existe; (c) muestra niños ilustrados y un arcoíris/estante no listados en el inventario. Calidad visual alta, texto legible y correcto en español (a simple vista).
- **ffmpeg/ffprobe.** Requeridos y presentes (`/usr/bin/ffmpeg`, `/usr/bin/ffprobe`); `pyproject.toml` y README **no los mencionan**.
- **ASR real vs demo.** El `transcripcion.txt` actual ("…canasta con pelotas pelotas sensoriales y libros de tela.") **no es igual** al string demo (que tiene "canasta con pelotas sensoriales" sin repetición ni punto final) y tiene mtime 2026-10-29 00:12, posterior al fix. Esto es **consistente con una respuesta ASR real** del WAV/multipart, pero no la prueba (no hay log/respuesta cruda guardada). El audio `nota.m4a` (73 KB, 2026-10-28 23:06) no lo reproduje; Codex dice que es espeak, no lo verifiqué. La corrida del reporte del 28-oct (3b) sí usó el demo (400, string idéntico).
- **Privacidad.** `.env` está en `.gitignore` (verificado en el archivo, sin leer `.env`). No evalué si `salon.jpg` contiene personas (no la abrí).
- **bridge/.** Contiene `loop.sh` que consulta un Google Doc cada 5 min con `curl`; hay un proceso con ese patrón en `ps` (1 coincidencia). No lo toqué. Ojo: el CLAUDE.md global prohíbe endpoints de IA sin auth, pero esto no es un endpoint de IA.

## 5. Artefactos y entregables

- `out/materiales.json`: 16 entradas con duplicados semánticos (sección 3). Mtime 2026-10-29 00:12. Mezcla nombres de visión y de voz (los 4 últimos son exactamente la lista oficial `VOZ_A_OFICIAL`).
- `out/planeacion.md`: 3 actividades, truncada, sin campos curriculares.
- README: dice "Llama Spark / Llama Image", "3 modelos" y flujo de 3 pasos; omite voz y ffmpeg. `docs/DEMO.md`: "3 modelos Meta nativos", "bloques, pelotas, mantas" (no hay mantas). El código usa `muse-spark-1.3`, `muse-image-1.0`, `sam-3.1`, `muse-voice-transcribe-1.0`: nomenclatura inconsistente. El reporte interno cita 15 tests; hay 17 (Codex citó 13/15/17 en el paquete, no verificado por mí).
- **Video final y GitHub:** sin remoto configurado; no encontré video en la carpeta. No deduzco que no exista fuera de ella. Reporto: ninguna evidencia disponible.
- **Reglas del organizador:** `WebFetch` a https://cerebralvalley.ai/e/meta-ai-developer-hackathon/waiver devolvió solo "Loading…" (misma limitación que Codex). **No pude verificar de forma independiente** la rúbrica 30/25/20/25 ni los requisitos de video/repositorio; uso la rúbrica de la solicitud como dada. Sí leí la doc de SAM.

## 6. Evaluación independiente

Rúbrica (según solicitud): impacto 30, uso creativo Meta 25, técnica 20, demo 25. Puntajes orientativos 0-10 para un jurado escéptico; confianza = qué tanto respalda la evidencia local.

| Criterio | Puntaje | Confianza |
|---|---|---|
| Impacto (30%) | 6 | media-baja: problema real, cero usuarios medidos |
| Uso creativo Meta (25%) | 5 | media: 3 de 4 modelos con aporte real; SAM no cumple su rol |
| Técnica (20%) | 4 | alta: fallbacks silenciosos, truncamiento, sin integración |
| Demo (25%) | 5 | baja: no hay video ni corrida real reproducible |

### Tres fortalezas
1. **Problema auténtico, entrada multimodal con sentido.** La foto del aula + nota de voz para completar lo que no se ve, producir plan y ficha es una idea que un jurado entiende en 10 segundos y encaja con "Build for Your World". Evidencia: diseño de `pipeline.py`, ficha visual; confianza media (potencial, no impacto medido).
2. **Ficha visual de calidad alta.** `out/ficha.png` es legible, coherente con la Actividad 1 y creíble para el aula; es el artefacto más fuerte para una demo. Evidencia: inspección visual; confianza alta (con la reserva de que cubre 1 de 3 actividades).
3. **Integración ASR correcta y probada localmente.** WAV PCM mono 16 kHz y multipart con `audioEncoding` coincide con la doc; 17/17 tests pasan, incluida conversión real con ffmpeg; el `transcripcion.txt` actual difiere del demo. Evidencia: tests reproducidos y repro_001; confianza media-alta (falta una corrida real documentada).

### Tres mejoras priorizadas
1. **Eliminar el éxito aparente y usar SAM de verdad.** Hoy ASR→demo y visión→lista fija son indistinguibles de un éxito, el log atribuye a "[SAM]" lo que hizo Spark Vision y SAM nunca entrega máscaras. Hacer: una petición SAM por concepto concreto con frase nominal, decodificar cajas/máscaras y mostrarlas; registrar `source` (real/degradado/demo) y modelo efectivo por etapa en `out/run.json`; lanzar excepción o marcar "modo demo" visible en lugar de sustituir. Impacta técnica y uso creativo (45%). Confianza alta en el diagnóstico.
2. **Calidad docente verificable y plan completo.** Detectar `finish_reason=="length"` y reintentar; subir/ajustar `max_tokens`; validar estructura (3 actividades completas, Seguridad ×3, edades dentro de sala); incorporar Fase 1 SEP real (campos/ejes) o quitar la etiqueta "SEP"; deduplicar semánticamente el inventario (o pasar por Spark para normalizar) y mandar a Image las **tres** actividades (p. ej. una ficha por actividad o un resumen estructurado, no `[:600]`); quitar el distintivo "SEP" de la ficha. Tres pilotos con educadoras reales con tiempo antes/después. Impacta impacto y demo. Confianza alta en defectos, media en cómo se calificarán.
3. **Repo reproducible y demo honesta.** Commitear README, pyproject, uv.lock, .gitignore, tests; crear remoto; documentar ffmpeg/ffprobe; unificar nomenclatura de modelos y conteo de tests; corregir `.png` que es WebP; medir latencia por etapa (hoy solo hay techos teóricos de 374/540/270 s) y grabar el video con una corrida real, con audio humano consentido y declarando cualquier edición. Impacta demo (25%). Confianza media (no pude verificar los requisitos finales de video/GitHub).

## 7. Propuesta de ronda API 002 (NO ejecutada; requiere aprobación del usuario)

- **Alcance:** 5 escenas etiquetadas manualmente (fotos propias **sin personas**), 1 audio humano consentido (20-30 s, una persona adulta consintiente). Salidas nuevas en `runs/002/<escena>/` (sin tocar `out/`); `.gitignore` ya cubre `runs/` por añadir.
- **Llamadas máximas (techo):**
  - `sam-3.1`: 5 escenas × 6 conceptos (tapete, bloques, pelotas, libros, rompecabezas, estante) = 30 llamadas, sin retries del SDK (`max_retries=0` en la prueba).
  - `muse-spark-1.3` visión (solo comparación, 5) + planeación (5 escenas × 1, + 5 reintentos) = ≤15.
  - `muse-image-1.0`: 5 fichas (una por actividad × 3 en una escena = 3 extra) = ≤8.
  - `muse-voice-transcribe-1.0`: 1 audio × 2 repeticiones = 2.
  - **Total ≤ ~60 llamadas.** Costo: **no verificado**; hay que consultar la tarifa/créditos del hackathon antes de ejecutar.
- **Pruebas:** (a) positiva de máscaras SAM: al menos 1 objeto con caja+máscara decodificada y overlay guardado; (b) fallo explícito: forzar key inválida/timeout corto y exigir que el sistema marque `degradado` o falle sin string demo/lista fija; (c) precisión/recall del inventario contra etiquetas manuales y tasa de duplicados semánticos; (d) latencia por etapa (voz, SAM, Spark, Image) y total, 3 repeticiones, mediana y p95; (e) plan completo: 3 actividades, 3 bloques "Seguridad", `finish_reason=="stop"`; (f) ficha representa las 3 actividades (revisión visual + checklist); (g) edad: nada fuera de 18-36 m.
- **Salvaguardas:** key solo de `.env`, nunca en logs/evidencias; sin commits; `max_retries=0` y presupuesto fijo; abortar a la primera 429/5xx repetida.

## 8. Límites y diferencias con EVALUACION.md

- **Confirmado independientemente:** SAM sin geometría, fallbacks silenciosos, duplicados, truncamiento de la actividad 3, ficha con solo actividad 1, ausencia de campos curriculares, sin remoto, README/pyproject sin seguimiento, 17 funciones de test.
- **Distinto/ampliado:** 17/17 sí lo pude reproducir (Codex no); el peor caso de SAM es 374 s, no 134 s, por retries del SDK; la ficha `.png` es WebP; la ficha incluye un logo "SEP" inventado; hay evidencia de que el ASR actual no es el demo literal.
- **No verificado:** rúbrica y reglas finales (página no carga), la sintaxis de tokens de SAM, Fase 1 SEP, contenido de `salon.jpg`, origen real del audio, costo de API, que `uv run` literal falle, latencias reales, existencia de video fuera de la carpeta.
- Las simulaciones no son un dictamen oficial.


---

# Respuesta 002 — CC

Recepción confirmada de solicitudes/002.md (2026-10-29). Esta ronda fue **solo documentación y cálculo**: sin red, sin API Meta, sin instalaciones, sin cambios al producto, sin commits, sin tocar `bridge/` ni sus procesos. No se ejecutó ningún comando nuevo que consulte Meta. Acuso también el 17 passed de Codex (`evidencias/codex_tests_001.txt`) y el WebP confirmado.

**Reglas del organizador / SEP:** no repetí la consulta en esta ronda (sin red). Mi lector devolvió «Loading» en la ronda 001: **verificación independiente pendiente**; me apoyo en la lectura de Codex y no sustituyo fuentes oficiales por terceros.

## 0. Fe de erratas a respuestas/001.md (001.md queda intacta como registro)

| Afirmación en 001 | Corrección |
|---|---|
| «peor caso / techos teóricos 374 / 540 / 270 s» | Son **cuentas ilustrativas bajo supuestos** (ver §3), no techos garantizados ni latencias medidas. |
| «5 familias duplicadas; unicidad real ≈ 11–12» y librero/estantería como duplicado | **Retirado.** Eso lo inferí por regex y por nombre; no distingue equivalencia de nombres, categorías ni instancias físicas (§4). El único hecho: 16 cadenas distintas por igualdad exacta y varias con descripción casi idéntica. |
| «p95 de tres repeticiones» | **Retirado.** Con n pequeño se reporta mínimo/mediana/máximo (§2). |
| Fortaleza 3 / tabla: «3 de 4 modelos con aporte real» | **Retirado como afirmación actual.** No hay una corrida nueva que lo demuestre (§5). |
| «key inválida/timeout forzado» para el fallo explícito | **Retirado.** Los fallos inducidos se prueban solo con mocks locales; 0 peticiones a Meta. |
| Total «≤ ~60 llamadas» | Sustituido por la tabla única de §1; no hay aprobación implícita de ninguna cifra. |

## 1. Ronda API por etapas (propuesta; NO ejecutada, NO aprobada)

Convenciones: *llamada lógica* = una invocación a un modelo del producto; *HTTP máx.* = peticiones reales con `max_retries=0` en el cliente OpenAI, sin reintentos de aplicación (hoy `sam.py` y `spark.py` los tienen: habría que desactivarlos en el arnés de prueba) y sin sustitución por demo/lista fija. Con eso, HTTP máx. = llamadas lógicas. Un fallo **no se reintenta**: se registra y, si hace falta repetir, se pide aprobación nueva. Fallos inducidos (ASR 400, timeout, visión vacía, `finish_reason=length`, JSON malformado): **mocks locales, 0 HTTP**.

| Etapa | Dependencias (todas previas y sin red) | Contenido | Criterio de éxito | Voz | SAM | Spark | Image | **HTTP máx.** | Acumulado |
|---|---|---|---|---|---|---|---|---|---|
| **0 (offline)** | Leer `dev.meta.ai/docs/sam/reading-segmentation` (enlazada por la doc de SAM; no la leí); decidir presupuesto; foto sin personas revisada por una persona; reducir la foto con ffmpeg si el límite de tamaño lo exige (límite no verificado) | Parser SAM y overlay desarrollados contra fixtures; arnés con `max_retries=0`; `run.json` | Tests con fixtures y mocks de fallo pasan (0 llamadas) | 0 | 0 | 0 | 0 | **0** | 0 |
| **A. Máscara mínima SAM** | Etapa 0 + aprobación explícita de A y presupuesto | 1 foto; 1 concepto presente (p. ej. «tapete de foami») + 1 concepto control ausente en esa foto (p. ej. «piano») | La respuesta cruda sanitizada se guarda; el parser extrae ≥1 caja y ≥1 máscara del concepto presente; overlay revisado por humano sobre el objeto correcto; el control ausente devuelve 0 coincidencias o error explícito (sin inventar) | 0 | 2 | 0 | 0 | **2** | 2 |
| **B. Corrida completa, 1 escena** | A superada y revisada por Alvaro; aprobación nueva | Audio humano consentido (frase real, ideal con una negación) + foto de A; 6 conceptos SAM (tapete, bloques, pelotas, libros, rompecabezas, estante); plan; **una** ficha con resumen de las 3 actividades | `run.json` con estado por etapa (real/fallo) sin demo; plan con 3 actividades completas y `finish_reason=stop`; ficha representa las 3 (checklist visual); latencia por etapa **registrada una vez** (n=1, sin estadística) | 1 | 6 | 1 | 1 | **9** | 11 |
| **C1. Repetición de latencia** (opcional) | B superada; aprobación nueva | Repetir B igual 2 veces para tener n=3 | Reportar mínimo/mediana/máximo por etapa y total, marcado «muestra pequeña, orientativo» | 2 | 12 | 2 | 2 | **18** | 29 |
| **C2. Escenas variadas** | B superada; 4 escenas nuevas sin personas, etiquetadas por humano antes; 1 audio con negación/objeto fuera de diccionario | 4 escenas × (6 SAM + plan + ficha) + 1 audio extra | Inventario vs etiquetas humanas (§4); fallos reportados tal cual; plan y ficha por escena | 1 | 24 | 4 | 4 | **33** | 62 |

**Conciliación con los 55 de la propuesta 001** (SAM 30 + visión Spark 5 + plan Spark 5 + reintentos Spark 5 + Image 8 + voz 2):

| Modelo | 001 | Nueva (A+B+C1+C2) | Diferencia y causa |
|---|---|---|---|
| SAM | 30 | 44 (2+6+12+24) | +14: control negativo (+2) y repeticiones de latencia (+12) que 001 no contaba |
| Voz | 2 | 4 (1+2+1) | +2: 001 las contaba aparte de las repeticiones |
| Spark | 15 | 7 (1+2+4) | −8: sin comparación de visión (esa ruta se elimina del producto) y sin reintentos |
| Image | 8 | 7 (1+2+4) | −1: una ficha por corrida, no 3 extra |
| **Total** | **55** | **62** | **+7** (ver arriba). Si se decide una ficha por actividad, Image sube +2 por corrida (+14 en total: 76) |

**Aprobación mínima razonable: la etapa A (2 llamadas).** Las demás cifras son un menú, no una solicitud. Cada etapa se aprueba solo después de revisar la anterior. **Costo: pendiente** de tarifas por tipo de llamada (la imagen y la visión suelen ser las más caras; no verificado), créditos disponibles y **presupuesto máximo explícito que fije Alvaro** antes de ejecutar; no hay presupuesto autorizado. Salvaguardas: key solo desde `.env`, nunca en logs ni evidencias; salidas en `runs/002/<etapa>/` sin tocar `out/`; abortar la etapa ante el primer 429/5xx.

## 2. Estadística de latencia

n=1 (etapa B) = valor único, sin estadística. n=3 (C1) = **mínimo, mediana y máximo**, etiquetado «muestra pequeña, orientativo». No se reporta p95 ni desviación como estimación fiable. Con 4 escenas distintas (C2) solo se reporta el rango por etapa. Se registra el tiempo de reloj por etapa y total, incluida la espera por reintentos del cliente (que en la prueba son 0), y se anota la hora, el tamaño de la foto/audio y si hubo error.

## 3. Cuentas ilustrativas de tiempo (no son latencias ni techos)

Supuestos: (a) `openai` 3.30.0 instalado, `DEFAULT_MAX_RETRIES=2` (leído en `openai/_constants.py` y observado con transporte simulado: 3 peticiones HTTP por `create()` que da timeout); (b) cada petición agota su timeout declarado; (c) se ignoran las esperas internas del SDK entre reintentos; (d) timeout de httpx **por fase de socket**, no total; (e) se aplican los reintentos de aplicación actuales.

| Etapa | Cuenta ilustrativa | Resultado |
|---|---|---|
| SAM | 4 intentos de app × 3 peticiones × 30 s + backoff de app 2+4+8 s | 374 s |
| SAM sin reintentos del SDK | 4 × 30 s + 14 s | 134 s (la cifra de Codex) |
| Spark | 3 intentos × 3 peticiones × 60 s | 540 s |
| Image | 1 × 3 peticiones × 90 s | 270 s |

Ninguna es un máximo garantizado (el timeout por fase y las esperas del SDK pueden alargarlo; un éxito rápido lo acorta) ni una medición. Solo ilustran que «<60 s» no se deduce del código.

## 4. Inventario: equivalencia, categoría, instancia, procedencia

Tres niveles distintos que el código actual mezcla en una cadena de texto:
1. **Equivalencia de nombres:** «bloques de madera de colores» ≈ «bloques de construcción de madera de colores» (misma descripción dicha de dos formas).
2. **Categoría:** «bloques», «tapete», «libros», «estante/mobiliario de guarda», «pelotas».
3. **Instancia física:** cuántos objetos hay. «librero expositor de madera» y «estantería baja con bandejas blancas» pueden ser **dos muebles distintos o uno solo descrito dos veces**; ni el nombre ni una regex lo deciden. Solo la foto etiquetada por un humano (o dos máscaras SAM disjuntas) lo decide.

**Propuesta de etiquetado humano** (por escena, antes de correr): archivo `etiquetas.json` con `id`, `categoria`, `descripcion_libre`, `n_instancias` y `visible_en_foto` (sí/no). Procedencia por ítem del sistema: `foto`, `voz` o `foto+voz`, más `origen_modelo` (sam / spark-vision / ninguno) y `estado` (real/degradado). Se mide: acierto de categoría (precisión/recall), error absoluto de conteo de instancias, ítems solo de voz marcados como «no verificados en foto». Regla de fusión propuesta: **nunca** fusionar automáticamente entre foto y voz ni por texto; fusionar solo con evidencia geométrica (máscaras que se solapan por IoU alta en la misma foto) o con confirmación de la educadora.

**Prueba «son dos estantes distintos»** (escena dedicada, etiquetada): foto con un librero y una estantería baja claramente separados. Aceptación: (i) el sistema reporta **2 instancias** con cajas/máscaras disjuntas; (ii) en una escena de control con **un** solo estante reporta 1; (iii) si la voz dice «un estante» y la foto muestra dos, el sistema marca el **conflicto** para confirmación y no lo resuelve en silencio. Primero se prueba con fixtures (0 llamadas); luego con SAM real en etapa C2.

## 5. Estado de la evidencia

| Afirmación | Estado | Base |
|---|---|---|
| SAM debe recibir una frase nominal por petición y devuelve texto con caja y máscara por coincidencia | Documentado | Doc de Meta (leída en 001) |
| El código no interpreta cajas ni máscaras y prompta a SAM con una lista | Hecho (estático + mock) | `src/sam.py`, tests |
| Los fallbacks devuelven éxito aparente | Hecho reproducido con mocks | `repro_001.py` |
| SAM devolvió vacío y Spark Vision rescató los 12 materiales | **Evidencia histórica** (reporte del 28-oct), no reproducida | `reporte-fase-interna-…md` |
| Una corrida real posterior produjo plan (truncado) y ficha | Histórico: archivos de `out/` con fecha del 29-oct; sin log | `out/` |
| El texto ASR actual difiere del fallback | **Indicio histórico**, no demuestra ASR real nuevo | `out/transcripcion.txt` |
| Tres de cuatro (o los cuatro) modelos aportaron respuestas reales **en una corrida nueva** | **No demostrado**: ninguna corrida nueva existe | — |
| 17/17 tests | Reproducido por CC y Codex, sin red, árbol con cambios sin commitear | evidencias |
| Puntajes 6/5/4/5 | **Orientativos**, no calibrados contra un jurado | juicio de CC |

## 6. Correcciones propuestas (NO aplicadas), orden recomendado y aceptación

Cada paso se prueba primero con mocks/fixtures (sin red); la comprobación real queda para las etapas A–C.

| # | Corrección | Aceptación |
|---|---|---|
| 1 | **Errores explícitos y procedencia.** Eliminar `DEMO_TRANSCRIPTION` y `FALLBACK_MATERIALS` del camino normal (solo bajo bandera `--demo-offline`, rotulada «DEMO» en pantalla y archivos). Cada etapa devuelve estado (`real`, `fallo`, `demo`), modelo efectivo y tiempo; `run.json` los persiste. Corregir el log que rotula «[SAM]» lo que hizo otro modelo. | Mocks: ASR 400 → etapa `fallo`, sin cadena demo en `out/`; visión vacía → `fallo`; el log nombra el modelo efectivo; sin bandera nunca aparece la lista fija. |
| 2 | **Parser SAM.** Una petición por concepto nominal; decodificar caja y máscara según `reading-segmentation`; overlay; error explícito si el formato no coincide. | Fixture sanitizado con respuesta cruda real (tras etapa A) → N cajas y N máscaras; formato malformado → error; vacío → 0 instancias, no inventadas; `max_retries=0` configurable. Depende de la etapa A. |
| 3 | **Inventario y negaciones.** Estructura con categoría, instancias, procedencia y confianza; detección de negación («no tengo/ya no/sin»); elementos fuera de diccionario conservados como texto libre «sin categoría», no descartados; paso de confirmación editable por la educadora; sin fusión automática foto/voz. | Las 5 frases de `repro_001.py`: «no tengo pelotas» → pelotas excluidas; «cuerdas, títeres…» → conservadas; prueba de dos estantes (§4) con fixtures. Una negación aislada no se acepta sin confirmación si es ambigua. |
| 4 | **Plan completo y edades.** Verificar `finish_reason`; si es `length`, tratarlo como fallo (sin reintento silencioso); validador de estructura (3 actividades, campos obligatorios por actividad, Seguridad ×3, cierre completo); edad tomada de la sala declarada y validada (18–36 m: fuera de rango se rechaza); regla determinista de piezas pequeñas vs edad. | Mocks: respuesta con `length`, plan que termina cortado, edad fuera de rango, falta de un bloque → error explícito. **No se promete alineación ni aval SEP:** añadir etiquetas de campo/PDA no equivale a alineación. Cualquier mención debe decir «borrador sin aval SEP»; la alineación requiere contrastar con Fase 1 (fuente oficial pendiente de verificación independiente) y revisión de una educadora. |
| 5 | **Resumen de tres actividades para la imagen.** Construir desde el plan **validado** una estructura (título + objetivo + materiales por actividad) en lugar de `[:600]`; una ficha con tres paneles o tres fichas; prohibir logotipos, marcas y «SEP» en el prompt. | Mock: el prompt contiene los 3 títulos; ningún truncado a 600; prompt excluye logos. En real (etapa B): checklist visual de 3 paneles; no se garantiza fidelidad del modelo, se mide. |
| 6 | **Formato de imagen.** Detectar el tipo por bytes mágicos y guardar con la extensión correcta (`.webp`/`.png`) en lugar de asumir PNG; documentar el formato. | Test con bytes WebP y PNG: extensión correcta; sin dependencias nuevas. |
| 7 | **Documentación reproducible.** Seguir README, pyproject, uv.lock, .gitignore y tests en git; documentar ffmpeg/ffprobe, cómo correr tests sin red, nomenclatura uniforme de los cuatro modelos y conteo real de tests; declarar limitaciones y modo demo; remoto y video según requisitos finales (pendientes de verificación). | Clon limpio en directorio temporal: instalar y correr tests con los pasos del README (en una ronda futura con red autorizada); sin secretos en el árbol; README sin «Llama Spark/Image» ni «3 modelos». |

Orden: 1 → 2 → 3 → 4 → 5 → 6 → 7. El 2 necesita la etapa A; 1, 3, 4, 5 y 6 avanzan sin red. 7 al final, pero el commit de los archivos sin seguimiento se puede adelantar si Alvaro lo decide.

## 7. Límites

Sin red ni ejecución nueva en esta ronda: solo se releyeron código y archivos locales y se hicieron cuentas. Pendiente: reglas del organizador (lector «Loading»), SEP Fase 1, doc `reading-segmentation`, tarifas y presupuesto, límites de tamaño de imagen y de audio, contenido de la foto de prueba. Simulación de jurado; no es dictamen oficial.
