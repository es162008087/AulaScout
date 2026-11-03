"""Reproducciones sin red de la solicitud 001 (CC). No modifica src/ ni out/.

Uso (desde /home/alvaro/dev/meta, venv del proyecto):
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. .venv/bin/python revision_jueces/evidencias/repro_001.py

Toda E/S de red está sustituida: requests.post, OpenAI(...) y httpx.MockTransport.
Se usa una API key falsa ("test-key"); nunca se lee .env.
"""

import json
import re
import tempfile
from pathlib import Path
from types import SimpleNamespace

try:
    import httpx
except ImportError:  # openai>=3 usa httpx2
    import httpx2 as httpx
import openai
from openai import OpenAI

import src.sam as sam
import src.spark as spark
import src.voice as voice
import src.image as image

SETTINGS = SimpleNamespace(base_url="https://x.invalid/v1", api_key="test-key", timeout_s=5)
tmp = Path(tempfile.mkdtemp(prefix="cc_repro_"))
foto = tmp / "salon.jpg"
foto.write_bytes(b"\xff\xd8fake")
audio = tmp / "nota.m4a"
audio.write_bytes(b"fake")


def head(t):
    print(f"\n=== {t}")


# 1. ASR falla -> DEMO_TRANSCRIPTION, sin ninguna señal para el llamador
head("1. ASR error -> transcripcion demo")
voice.requests.post = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("simulado 400"))
voice.convertir_a_wav_16k = lambda s, d: tmp / "x.wav"
(tmp / "x.wav").write_bytes(b"RIFF")
out = voice.transcribir_audio(audio, SETTINGS)
print("devuelve DEMO_TRANSCRIPTION:", out == voice.DEMO_TRANSCRIPTION)
print("tipo de retorno:", type(out).__name__, "(sin flag real/degradado)")
print("materiales derivados:", voice.parse_materiales_desde_voz(out))

# 2. Visión falla -> FALLBACK_MATERIALS; y atribución SAM vs Spark Vision
head("2a. SAM y Spark Vision fallan -> lista fija")
sam.time.sleep = lambda s: None


class Boom:
    def __init__(self, *a, **k):
        self.responses = SimpleNamespace(create=self._b)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._b))

    def _b(self, **k):
        raise RuntimeError("simulado")


sam.OpenAI = Boom
r = sam.detect_materials(foto, SETTINGS)
print("devuelve FALLBACK_MATERIALS:", r == sam.FALLBACK_MATERIALS, "| n =", len(r))

head("2b. SAM vacío, Spark Vision responde -> mismo tipo de retorno (list[str])")
calls = []


class SamEmptyVisionOk:
    def __init__(self, *a, **k):
        def rcreate(**kw):
            calls.append(kw["model"])
            return SimpleNamespace(output=[])

        def ccreate(**kw):
            calls.append(kw["model"])
            msg = SimpleNamespace(content="bloques, tapete, pelotas")
            return SimpleNamespace(choices=[SimpleNamespace(message=msg)])

        self.responses = SimpleNamespace(create=rcreate)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=ccreate))


sam.OpenAI = SamEmptyVisionOk
print("resultado:", sam.detect_materials(foto, SETTINGS))
print("modelos invocados:", calls, "-> pipeline.py rotula todo como '[SAM]'")

head("2c. SAM: se pide texto, no geometría")
print("SAM_PROMPT:", sam.SAM_PROMPT)
print("parse_materials solo lee type=message/output_text; ningún acceso a boxes/masks:",
      "mask" not in Path("src/sam.py").read_text().lower().replace("máscara", ""))

# 3. Duplicados semánticos en el merge (igualdad exacta de cadenas)
head("3. Merge: duplicados semánticos")
mats = json.loads(Path("out/materiales.json").read_text(encoding="utf-8"))
print("entradas:", len(mats), "| únicas por igualdad exacta:", len(set(mats)))
familias = {
    "tapete": "tapete", "bloques": "bloque", "pelotas": "pelota", "libros": "libro",
    "estante": "estant|librero",
}
for fam, pat in familias.items():
    g = [m for m in mats if re.search(pat, m, re.I)]
    print(f"  familia '{fam}': {len(g)} entradas ->", g)
print("  (rompecabezas aparece 1 vez en JSON actual pero con 2 nombres posibles; mesas/sillas, cojines, etc. únicos)")

# 4. Negación y fuera de diccionario
head("4. Extracción por keywords")
for t in [
    "no tengo pelotas",
    "no tengo bloques ni tapete, solo libros",
    "Tengo cuerdas, títeres, instrumentos musicales y pintura",
    "tengo pelotas de vinil",
    "ya no hay libros pero sí un rompecabezas",
]:
    print(f"  {t!r} -> {voice.parse_materiales_desde_voz(t)}")
print("  nota: el audio ES el único canal que aporta lo que la foto no ve; fuera de diccionario se pierde en silencio")

# 5. SDK retries: cuántas peticiones HTTP reales por create() con timeout
head("5. Retries del SDK openai (httpx.MockTransport, sin red)")
print("openai", openai.__version__, "| DEFAULT_MAX_RETRIES =", openai._constants.DEFAULT_MAX_RETRIES)
import openai._base_client as bc

bc.time.sleep = lambda s: None  # no dormir
n = {"c": 0}


def handler(req):
    n["c"] += 1
    raise httpx.ConnectTimeout("simulado", request=req)


cl = OpenAI(base_url="https://x.invalid/v1", api_key="test-key",
            http_client=httpx.Client(transport=httpx.MockTransport(handler)))
try:
    cl.responses.create(model="sam-3.1", input="x", timeout=sam.SAM_TIMEOUT)
except Exception as e:
    print("excepción:", type(e).__name__)
print("peticiones HTTP por una llamada create(timeout=30):", n["c"])
per = n["c"]
print(f"SAM peor caso (sin red de espera por reintento): {sam.SAM_RETRIES + 1} intentos x {per} x {sam.SAM_TIMEOUT}s "
      f"+ backoffs {sum(sam.SAM_BACKOFFS[:sam.SAM_RETRIES])}s = "
      f"{(sam.SAM_RETRIES + 1) * per * sam.SAM_TIMEOUT + sum(sam.SAM_BACKOFFS[:sam.SAM_RETRIES])}s "
      f"(Codex: 134s = sin retries SDK)")
print(f"Spark peor caso: {spark.SPARK_RETRIES + 1} x {per} x {spark.SPARK_TIMEOUT}s = "
      f"{(spark.SPARK_RETRIES + 1) * per * spark.SPARK_TIMEOUT}s")
print(f"Image peor caso: 1 x {per} x {image.IMAGE_TIMEOUT}s = {per * image.IMAGE_TIMEOUT}s")
print("Voz: requests.post timeout=60s, sin retry, cualquier fallo -> demo")
print("(timeout de httpx es por fase de socket, no tiempo total; estos son techos teóricos, no mediciones)")

# 6. finish_reason / truncamiento
head("6. Spark: finish_reason ignorado")
spark.OpenAI = lambda **k: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
    create=lambda **kw: SimpleNamespace(choices=[SimpleNamespace(
        finish_reason="length",
        message=SimpleNamespace(content="## Actividad 1\n" + "texto " * 40 + "dibuja una carita feliz en la"))]))))
res = spark.generate_planeacion(["bloques"], SETTINGS)
print("acepta respuesta con finish_reason='length':", bool(res), "| termina en:", repr(res[-30:]))
print("SPARK_MAX_TOKENS =", spark.SPARK_MAX_TOKENS, "| MIN_CONTENT_LEN =", spark.MIN_CONTENT_LEN)

# 7. Ficha vs 3 actividades
head("7. Ficha: qué parte del plan llega al prompt de imagen")
plan = Path("out/planeacion.md").read_text(encoding="utf-8")
p = image.build_ficha_prompt(plan)
resumen = p.split("actividades: ", 1)[1]
print("chars del plan:", len(plan), "| chars enviados:", len(resumen))
print("'Actividad 1' en resumen:", "Actividad 1" in resumen,
      "| 'Actividad 2':", "Actividad 2" in resumen, "| 'Actividad 3':", "Actividad 3" in resumen)
print("resumen enviado ->", resumen[-120:])

# 8. Validación del plan actual
head("8. Planeación actual: validación estructural")
print("actividades (## Actividad):", len(re.findall(r"^## Actividad", plan, re.M)))
for k in ["Campo", "PDA", "Aprendizaje", "Fase 1", "Fase 2", "Programa", "Seguridad"]:
    print(f"  '{k}':", len(re.findall(k, plan)))
print("termina en:", repr(plan[-40:]))
print("bloques 'Seguridad:' =", plan.count("**Seguridad:**"), "(esperado 3)")
acts = re.split(r"^## Actividad", plan, flags=re.M)[1:]
print("edades:", re.findall(r"\*\*Edad:\*\* (.+)", plan))
