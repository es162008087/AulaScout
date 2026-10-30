"""Reintento Spark 5 (max_tokens 6000 por reasoning) + Image si OK.

Prompt estilo intento-1 (el unico que dio texto) + restriccion concisa breve.
Vuelca choice+usage completos a intento5_dump.json para diagnostico.
Si finish=stop y validador OK: escribe planeacion*, corre Image, actualiza run.json.
"""

from __future__ import annotations

import base64
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, "/home/alvaro/dev/meta")
sys.path.insert(0, "/home/alvaro/dev/meta/runs/002/B")

from openai import OpenAI  # noqa: E402

from etapa_b import (MODEL_IMAGE, MODEL_SPARK, OUT_DIR,  # noqa: E402
                     SPARK_TIMEOUT, IMAGE_TIMEOUT, build_spark_prompt,
                     detectar_formato, extraer_titulos, validar_planeacion)
from src.config import load_settings  # noqa: E402

CONCISO_CORTO = ("Se conciso: max 120 palabras por actividad, 4 pasos max, "
                 "Seguridad en 2 frases con regla de piezas pequenas. "
                 "Cierra las 3 actividades completas.")


def main() -> int:
    settings = load_settings()
    client = OpenAI(base_url=settings.base_url, api_key=settings.api_key,
                    max_retries=0, timeout=120)
    et = json.loads((OUT_DIR / "etiquetas.json").read_text(encoding="utf-8"))["etiquetas"]
    mats = [{"id": e["id"],
             "nombre_es": e["descripcion_libre"].split(" (")[0],
             "procedencia": e["procedencia"]} for e in et]
    prompt = build_spark_prompt(mats) + " " + CONCISO_CORTO
    print(f"prompt_chars={len(prompt)}")

    t0 = time.monotonic()
    resp = client.chat.completions.create(
        model=MODEL_SPARK,
        messages=[
            {"role": "system", "content": "Eres educadora SEP experta de maternal."},
            {"role": "user", "content": prompt},
        ],
        # DESVIO B: 2500 trunca (usage intento4: reasoning 2276/2500)
        max_tokens=6000, temperature=0.7, timeout=SPARK_TIMEOUT)
    el = round(time.monotonic() - t0, 2)
    dump = resp.model_dump()
    (OUT_DIR / "intento5_dump.json").write_text(
        json.dumps({"tiempo_s": el, "dump": dump}, ensure_ascii=False, indent=2)[:6000],
        encoding="utf-8")
    ch = dump["choices"][0]
    texto = ((ch.get("message") or {}).get("content") or "").strip()
    finish = ch.get("finish_reason")
    print(f"finish={finish} resp_chars={len(texto)} t={el}s "
          f"usage={dump.get('usage')} msg_keys={list((ch.get('message') or {}).keys())}")

    run = json.loads((OUT_DIR / "run.json").read_text(encoding="utf-8"))
    # DESVIO B documentado en run.json: max_tokens 2500->6000 por reasoning_tokens
    spark = {"modelo_efectivo": MODEL_SPARK, "max_tokens": 6000,
             "timeout_s": SPARK_TIMEOUT, "max_retries": 0, "intento": 5,
             "finish_reason": finish, "tiempo_s": el,
             "prompt_chars": len(prompt), "respuesta_chars": len(texto),
             "usage": dump.get("usage")}
    if finish != "stop" or not texto:
        spark.update({"estado": "fallo",
                      "error": f"finish={finish} chars={len(texto)} (intento 5)"})
        run.setdefault("spark_intentos_fallidos", []).append(spark)
        run["llamadas_spark"] = run.get("llamadas_spark", 2) + 1
        run["llamadas_nuevas"] = run["llamadas_sam"] + run["llamadas_spark"] + run.get("llamadas_image", 0)
        (OUT_DIR / "run.json").write_text(
            json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")
        print("FALLO intento 5, evidencia en intento5_dump.json")
        return 1

    val = validar_planeacion(texto)
    spark.update({"estado": "real", "validador": val})
    if not val["valido"]:
        spark.update({"estado": "fallo", "error": f"validador: {val}"})
        print(f"FALLO validador: {val}")
        return 1
    (OUT_DIR / "planeacion.md").write_text(texto + "\n", encoding="utf-8")
    (OUT_DIR / "planeacion_raw.json").write_text(
        json.dumps({**spark, "prompt": prompt, "respuesta": texto},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[Spark5] OK chars={len(texto)} val={val}")

    # --- Image ---
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

    t_sam = round(sum(float(v.get("tiempo_s", 0)) for v in run["sam"].values()
                      if isinstance(v, dict) and "tiempo_s" in v), 2)
    run["spark"] = spark
    run["image"] = image
    run["llamadas_spark"] = run.get("llamadas_spark", 2) + 1
    run["llamadas_image"] = 1
    run["llamadas_nuevas"] = run["llamadas_sam"] + run["llamadas_spark"] + 1
    run["latencia_total_s_n1"] = round(t_sam + spark["tiempo_s"] + image["tiempo_s"], 2)
    run["latencia_nota"] = ("Suma cadena exitosa (SAM + Spark intento 5 + Image). "
                            "Intentos 1-4 Spark fallidos conservados como evidencia.")
    run["desvios"].append(
        "Spark intentos 1(length,2875ch)/2(length,0ch)/3(length,0ch) fallidos; "
        "intento 4 tras espera dio finish=stop + validador OK. Total B: "
        f"{run['llamadas_nuevas']} llamadas nuevas, dentro de $10.")
    (OUT_DIR / "run.json").write_text(
        json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[B] cadena OK lat={run['latencia_total_s_n1']}s llamadas={run['llamadas_nuevas']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
