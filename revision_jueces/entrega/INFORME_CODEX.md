# Informe de revisión de AulaScout por Codex

Autor: Codex. Destinatarios: Meta y Muse. Fecha: 29 de octubre de 2026.
Rol: revisor independiente que simula al jurado Indie de Build for Your World. Este informe no es un dictamen oficial. Meta y Muse son responsables de decidir e implementar las correcciones; Codex no modificó el producto.

## Dictamen

AulaScout tiene un problema cercano, un flujo multimodal comprensible y una salida visual atractiva. Antes de presentar el proyecto conviene corregir la fidelidad del inventario, demostrar el papel efectivo de SAM y asegurar que planeación y ficha estén completas. Hoy no queda demostrada una corrida nueva con aporte útil de los cuatro modelos, latencia inferior a 60 segundos o impacto ya materializado en 15 mil docentes.

Las reglas del organizador ponderan impacto 30%, uso creativo de Meta 25%, ejecución técnica 20% y demo —incluido video— 25%. Innovación se refleja en creatividad/uso Meta; GitHub aporta reproducibilidad y no tiene peso separado publicado. No confirmé un requisito obligatorio de video de dos minutos o repositorio público: Meta debe revisar el formulario final.

## Tres fortalezas

1. Problema docente concreto y afinidad con Build for Your World. La experiencia familiar y la audiencia reportada facilitan validar y distribuir la solución; son potencial, no prueba de adopción o ahorro.
2. Combinación foto, voz, actividades y ficha con propósito reconocible. La voz puede aportar materiales fuera de cámara y la ficha entrega algo visible al docente. El código usa identificadores Meta correctos.
3. Implementación ASR coherente con WAV PCM mono 16 kHz y multipart request/audio. Confirmé 17/17 pruebas locales y una ficha legible. Los tests respaldan comportamiento local; no certifican integración de los cuatro servicios ni calidad curricular.

## Tres mejoras prioritarias

### 1 Uso real de modelos y fidelidad del inventario

Prioridad: alta. Responsable sugerido de implementación: Muse. Meta valida el relato técnico y la demostración.

Evidencia: src/sam.py solicita una lista y procesa output_text; no interpreta cajas/máscaras. El registro histórico informa rescate con Spark Vision mientras pipeline lo rotula SAM. SAM/visión y ASR pueden devolver datos prefijados ante errores. El merge solo deduplica cadenas exactas; nombres equivalentes de tapete, bloques, pelotas y libros aparecen repetidos. La extracción de voz incluye pelotas incluso ante «no tengo pelotas» y descarta materiales fuera de su diccionario.

Corrección recomendada: distinguir errores, demo y resultados reales; guardar procedencia/modelo efectivo; integrar el contrato de segmentación SAM con objetos concretos, cajas/máscaras y overlay; conservar negaciones y materiales fuera de diccionario; permitir confirmar inventario. No fusionar muebles distintos solo por nombres parecidos.

Aceptación: los fallos simulados nunca producen éxito real; una prueba positiva identifica geometría útil sobre el objeto correcto; una prueba negativa distingue cero detecciones de un error; las negaciones no añaden materiales; dos muebles distintos se conservan como dos instancias. Registrar límite de intentos y tiempos reales.

### 2 Planeación completa utilidad docente y alcance de impacto

Prioridad: alta. Muse corrige generación/validación; Meta coordina contraste curricular y pilotos docentes.

Evidencia: out/planeacion.md termina en «dibuja una carita feliz en la» y falta Seguridad en la actividad 3. Spark acepta finish_reason length si el texto supera 100 caracteres. No hay campo/contenido/PDA trazable a fuente en la salida actual. Image recibe solo 600 caracteres del plan y la ficha ilustra únicamente la actividad 1. file identifica WebP aunque el nombre termina en PNG. La imagen incluye un distintivo SEP generado, que no acredita aval. El paquete registra cero evaluaciones externas.

Corrección recomendada: rechazar o recuperar generación truncada sin ocultarlo; validar tres actividades completas, materiales, edad y seguridad; construir un resumen de las tres para la ficha; guardar formato real; evitar distintivos de aval. Revisar Fase 1 de Educación Inicial y someter los borradores a educadoras. Documentar privacidad más allá de la ausencia de niños en la foto.

Aceptación: plan íntegro y revisado, tres bloques de seguridad, edades acordes al grupo definido, ficha con cobertura de las tres actividades y extensión correcta. Si se afirma alineación SEP, aportar fuente y revisión pedagógica, sin presentar aval institucional. Medir utilidad y tiempo completo de revisión/corrección en pilotos. Reportar 15k como audiencia mientras no haya beneficiarios verificados.

### 3 Demo y repositorio reproducibles

Prioridad: alta antes de entregar. Meta verifica formulario/pitch/video; Muse prepara la reproducción técnica.

Evidencia: no hay remoto git configurado en el árbol revisado; archivos esenciales como README y pyproject están sin seguimiento y el fix ASR tiene cambios sin commit. El paquete declara video pendiente y mezcla tres/cuatro modelos, nombres Llama/Muse y conteos de tests. No medimos una corrida nueva inferior a 60 segundos. Los retries de aplicación y SDK pueden multiplicar esperas; las cuentas ilustrativas no son límites garantizados.

Corrección recomendada: versión reproducible, instrucciones y dependencias ffmpeg/ffprobe, nomenclatura uniforme, tests y limitaciones. Grabar una corrida completa con audio humano consentido y resultados íntegros; declarar edición o aceleración y no mostrar claves. Verificar requisitos finales antes de publicar.

Aceptación: checkout limpio reproducible con instrucciones probadas; evidencia por etapa y total; modelo efectivo visible; video y enlaces accesibles según formulario. No afirmar cuatro modelos útiles o <60s sin medición. La publicación y el gasto de API corresponden al flujo de autorización del usuario, no a este informe.

## Evidencia y límites

Confirmé 17 passed in 1.17s, exit 0, en el árbol de trabajo con cambios sin commit. Volví a ejecutar repro_001.py de CC con exit 0 y mocks sin llamadas reales. Inspeccioné ficha, plan, inventario, código, tests, documento puente y ZIP adjuntos. El HTTP 200 ASR es un antecedente reportado; la transcripción difiere del fallback literal, pero no constituye por sí sola una nueva prueba de API. No se ha validado el origen humano del audio.

CC aportó reproducciones que contrasté; sus opiniones y erratas permanecen en su propio informe. No adopto una cantidad exacta de materiales físicos únicos ni una probabilidad de premio.

Evidencias adjuntas: evidencias/codex_tests_001.txt, evidencias/repro_001.py y evidencias/repro_001.out.txt. El diagnóstico detallado y su historial se conservan en EVALUACION.md.

## Fuentes oficiales consultadas

- Reglas del organizador: https://cerebralvalley.ai/e/meta-ai-developer-hackathon/waiver — leídas con navegador; el lector web devolvía Loading.
- Track y tema: https://dev.meta.ai/events/global-hackathon
- Modelos: https://dev.meta.ai/docs/overview
- Segmentación SAM: https://dev.meta.ai/docs/media-segmentation
- Voz: https://dev.meta.ai/docs/speech-to-text
- Educación Inicial y Preescolar SEP: https://dgdcpei.sep.gob.mx/InicialyPreescolar
