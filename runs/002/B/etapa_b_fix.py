"""Etapa B fix: reintento Spark conciso (finish=stop) + Image. 2 llamadas.

El intento 1 trunco (finish=length, 2875 chars, corte a mitad de frase).
Se conserva en planeacion_intento1_raw.json y run.json.
"""

from __future__ import annotations

import base64
import json
import shutil
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "runs" / "002" / "A"))

from openai import OpenAI  # noqa: E402

sys.path.insert(0, str(REPO / "runs" / "002" / "B"))
from etapa_b import (MODEL_IMAGE, MODEL_SPARK, OUT_DIR, SPARK_MAX_TOKENS,
                     SPARK_TIMEOUT, IMAGE_TIMEOUT, build_spark_prompt,
                     detectar_formato, extraer_titulos, validar_planeacion)
from src.config import load_settings  # noqa: E402

CONCISO = (
    "IMPORTANTE: se conciso. Cada actividad maximo 120 palabras. "
    "Pasos: maximo 4 pasos de una linea. Seguridad: 2 frases "
    "(incluir SIEMPRE la regla de piezas pequenas). "
    "Total maximo 400 palabras. Cierra las 3 actividades completas."
)


def main() -> int:
    settings = load_settings()
    client = OpenAI(base_url=settings.base_url, api_key=settings.api_key,
                    max_retries=0, timeout=120)
    run = json.loads((OUT_DIR / "run.json").read_text(encoding="utf-8"))

    # Preservar intento 1 truncado
    shutil.move(str(OUT_DIR / "planeacion_raw.json"),
                str(OUT_DIR / "planeacion_intento1_raw.json"))
    intento1 = dict(run["spark"])
    intento1["nota"] = "truncado a mitad de frase; conservado como evidencia"

    materiales = json.loads((OUT_DIR / "etiquetas.json").read_text(
        encoding="utf-8"))["etiquetas"]
    mats = [{"id": e["id"],
             "nombre_es": e["descripcion_libre"].split(" (")[0],
             "procedencia": e["procedencia"]} for e in materiales]
    prompt = build_spark_prompt(mats) + " " + CONCISO

    spark: dict = {"modelo_efectivo": MODEL_SPARK, "max_tokens": SPARK_MAX_TOKENS,
                   "timeout_s": SPARK_TIMEOUT, "max_retries": 0, "intento": 2,
                   "prompt_conciso": True}
    t0 = time.monotonic()
    resp = client.chat.completions.create(
        model=MODEL_SPARK,
        messages=[
            {"role": "system", "content": "Eres educadora SEP experta de maternal."},
            {"role": "user", "content": prompt},
        ],
        max_tokens=SPARK_MAX_TOKENS, temperature=0.7, timeout=SPARK_TIMEOUT)
    texto = (resp.choices[0].message.content or "").strip()
    finish = resp.choices[0].finish_reason
    spark.update({"estado": "real", "finish_reason": finish,
                  "tiempo_s": round(time.monotonic() - t0, 2),
                  "prompt_chars": len(prompt), "respuesta_chars": len(texto)})
    (OUT_DIR / "planeacion.md").write_text(texto + "\n", encoding="utf-8")
    (OUT_DIR / "planeacion_raw.json").write_text(
        json.dumps({**spark, "prompt": prompt, "respuesta": texto},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    val = validar_planeacion(texto)
    spark["validador"] = val
    spark["intento_1_truncado"] = intento1
    if finish == "length" or not val["valido"]:
        spark["estado"] = "fallo"
        spark["error"] = f"finish={finish} val={val}"
        run["spark"] = spark
        (OUT_DIR / "run.json").write_text(
            json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"FALLO Spark intento 2: finish={finish} val={val}")
        return 1
    print(f"[Spark2] finish={finish} chars={len(texto)} val={val} t={spark['tiempo_s']}s")

    titulos = extraer_titulos(texto)
    ficha_prompt = (
        "Ficha visual infantil para aula de maternal, estilo plano y alegre, "
        "dividida en 3 paneles horizontales (uno por actividad), con titulos "
        f"cortos: {'; '.join(titulos) if titulos else 'juego libre'}. "
        "Sin texto largo, sin logos, sin siglas SEP, sin marcas de agua.")
    image: dict = {"modelo_efectivo": MODEL_IMAGE, "timeout_s": IMAGE_TIMEOUT,
                   "max_retries": 0}
    t0 = time.monotonic()
    resp = client.responses.create(
        model=MODEL_IMAGE,
        input=[{"role": "user", "content": [
            {"type": "input_text", "text": ficha_prompt}]}],
        tools=[{"type": "image_generation"}], timeout=IMAGE_TIMEOUT)
    b64 = ""
    for item in resp.output or []:
        d = item if isinstance(item, dict) else getattr(item, "model_dump", lambda: {})()
        if not isinstance(d, dict) or d.get("type") != "image_generation_call":
            continue
        for name in ("result", "image"):
            v = d.get(name)
            if v and str(v).strip():
                b64 = str(v).strip()
                break
        if b64:
            break
    if b64.startswith("data:"):
        b64 = b64.split(",", 1)[1] if "," in b64 else ""
    if not b64:
        raise ValueError("Image no devolvio imagen.")
    data = base64.b64decode(b64)
    fmt = detectar_formato(data)
    if fmt is None:
        raise ValueError(f"bytes magicos desconocidos: {data[:12]!r}")
    fname = f"ficha.{fmt}"
    (OUT_DIR / fname).write_bytes(data)
    image.update({"estado": "real", "archivo": fname, "formato_magic": fmt,
                  "bytes": len(data), "titulos": titulos,
                  "tiempo_s": round(time.monotonic() - t0, 2)})
    (OUT_DIR / "ficha_raw.json").write_text(
        json.dumps({**image, "prompt": ficha_prompt},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[Image] {fname} {len(data)}B magic={fmt} t={image['tiempo_s']}s")

    # run.json: cadena exitosa + latencia compuesta honesta
    t_sam = round(sum(float(v.get("tiempo_s", 0))
                      for v in run["sam"].values()
                      if isinstance(v, dict) and "tiempo_s" in v), 2)
    latencia_cadena = round(t_sam + spark["tiempo_s"] + image["tiempo_s"], 2)
    run["spark"] = spark
    run["image"] = image
    run["llamadas_spark"] = 2
    run["llamadas_image"] = 1
    run["llamadas_nuevas"] = run["llamadas_sam"] + 2 + 1
    run["latencia_total_s_n1"] = latencia_cadena
    run["latencia_nota"] = (
        "Suma de la cadena exitosa (SAM 7 llamadas + Spark intento 2 + Image), "
        "un intento exitoso por modelo, sin reintentos. El intento 1 de Spark "
        f"(truncado length) aporto {intento1.get('tiempo_s')}s fuera de la cadena "
        "y se conserva en planeacion_intento1_raw.json.")
    run["desvios"].append(
        "Spark intento 1 con prompt largo trunco (finish=length, 2875 chars, "
        "corte a mitad de frase) -> marcado fallo y conservado; intento 2 con "
        "prompt conciso (<=400 palabras) dio finish=stop + validador OK. "
        "Total B: 10 llamadas nuevas (7 SAM + 2 Spark + 1 Image), dentro de $10.")
    (OUT_DIR / "run.json").write_text(
        json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[B-fix] cadena OK latencia={latencia_cadena}s llamadas={run['llamadas_nuevas']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
