"""Etapa C1 (002): pipeline x3 n=3 sobre base B. SAM 6 EN + Spark 3500 + Image.

Uso:
  uv run python runs/002/C1/etapa_c1.py

Salidas en runs/002/C1/: run_n1..n3.json, planeacion_run{i}.md, ficha_run{i}.png,
ficha_run{i}_raw.json, etiquetas.json, promedio.json, run.json. No toca out/.
Voice DEMO marcado (0 llamadas). Piano no repetido.
"""
from __future__ import annotations

import base64
import io
import json
import re
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "runs" / "002" / "A"))
sys.path.insert(0, str(REPO / "runs" / "002" / "B"))

from openai import OpenAI  # noqa: E402

import etapa_a as A  # noqa: E402
import etapa_b as B  # noqa: E402
from src.config import load_settings  # noqa: E402
from src.voice import DEMO_TRANSCRIPTION, parse_materiales_desde_voz  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent
MODEL_SPARK = B.MODEL_SPARK
MODEL_IMAGE = B.MODEL_IMAGE
SPARK_MAX_TOKENS = 3500
SPARK_TIMEOUT = B.SPARK_TIMEOUT
IMAGE_TIMEOUT = B.IMAGE_TIMEOUT

PROMPT_EXTRA = (" RESUMEN CORTO: max 80 palabras por actividad, max 3 pasos por actividad,"
    " Seguridad en 2 frases cortas incluyendo la regla de piezas pequenas."
    " Sin introduccion ni cierre. Cierra las 3 actividades completas, sin truncar.")

TIT_RE = re.compile(r"(?m)^\s*(?:\*\*)?Titulo:(?:\*\*)?\s*(.+?)\s*$")


def run_chain(client: OpenAI, image_b64: str, foto: Path, idx: int) -> dict:
    t_global = time.monotonic()
    llamadas_sam = 0
    sam_res: dict[str, dict] = {}
    sam_t = 0.0
    # SAM 6 conceptos EN, 1 alt max si 0, sin piano
    for concepto, tag, alt in B.CONCEPTS:
        res = B.run_concept(client, image_b64, concepto, f"run{idx}_{tag}")
        llamadas_sam += 1
        if res.get("estado") == "real" and res.get("n_cajas") == 0 and alt:
            res_alt = B.run_concept(client, image_b64, alt, f"run{idx}_{tag}_alt")
            llamadas_sam += 1
            if res_alt.get("estado") == "real" and res_alt.get("n_cajas", 0) > 0:
                res = res_alt
            else:
                res["alternativa_probada"] = alt
                res["alternativa_resultado"] = (
                    f"{res_alt.get('n_cajas', '?')} cajas, "
                    f"{res_alt.get('n_mascaras', '?')} mascaras")
        sam_res[tag] = {k: v for k, v in res.items()
                        if k not in ("raw_sanitizado", "records")}
        sam_t += float(res.get("tiempo_s", 0) or 0)
        print(f"[SAM r{idx}] {concepto}: {res.get('estado')} "
              f"cajas={res.get('n_cajas')} t={res.get('tiempo_s')}s")
    # Voice DEMO
    voz_mats = parse_materiales_desde_voz(DEMO_TRANSCRIPTION)
    materiales: list[dict] = []
    for concepto, tag, _ in B.CONCEPTS:
        r = sam_res.get(tag, {})
        materiales.append({
            "id": f"FOTO-{tag}", "concepto_en": concepto,
            "nombre_es": B.GLOSARIO_ES[concepto],
            "n_cajas": r.get("n_cajas", 0),
            "procedencia": "foto", "origen_modelo": "sam-3.1",
            "estado": r.get("estado", "no_llamado")})
    for i, m in enumerate(voz_mats, 1):
        materiales.append({"id": f"VOZ-{i:02d}", "concepto_en": None,
                           "nombre_es": m, "procedencia": "voz",
                           "origen_modelo": "espeak-sintetico", "estado": "demo"})
    # Spark 3500 temp 0
    spark_prompt = B.build_spark_prompt(materiales) + PROMPT_EXTRA
    t0 = time.monotonic()
    resp = client.chat.completions.create(
        model=MODEL_SPARK,
        messages=[{"role": "system",
                   "content": "Eres educadora SEP experta de maternal. Resumen corto."},
                  {"role": "user", "content": spark_prompt}],
        max_tokens=SPARK_MAX_TOKENS, temperature=0, timeout=SPARK_TIMEOUT)
    dump = resp.model_dump()
    ch = dump["choices"][0]
    texto = ((ch.get("message") or {}).get("content") or "").strip()
    finish = ch.get("finish_reason")
    t_spark = round(time.monotonic() - t0, 2)
    val = B.validar_planeacion(texto)
    spark = {"modelo_efectivo": MODEL_SPARK, "max_tokens": SPARK_MAX_TOKENS,
             "timeout_s": SPARK_TIMEOUT, "max_retries": 0,
             "finish_reason": finish, "tiempo_s": t_spark,
             "prompt_chars": len(spark_prompt), "respuesta_chars": len(texto),
             "usage": dump.get("usage"), "estado": "real", "validador": val}
    print(f"[Spark r{idx}] finish={finish} chars={len(texto)} t={t_spark}s val={val}")
    if finish != "stop" or not val["valido"]:
        spark["estado"] = "fallo"
        spark["error"] = f"finish={finish} valido={val['valido']} {val}"
        (OUT_DIR / f"spark_run{idx}_dump.json").write_text(
            json.dumps({"tiempo_s": t_spark, "dump": dump},
                       ensure_ascii=False, indent=2)[:8000], encoding="utf-8")
        raise RuntimeError(f"Spark run{idx} fallo: {spark['error']}")
    (OUT_DIR / f"planeacion_run{idx}.md").write_text(texto + "\n", encoding="utf-8")
    tits = TIT_RE.findall(texto)[:3]
    if len(tits) != 3:
        raise RuntimeError(f"run{idx}: se esperaban 3 titulos, hallados {tits}")
    print(f"[Spark r{idx}] titulos={tits}")
    # Image 3 paneles, 3 titulos reales, sin SEP
    fp = ("Ficha visual infantil para aula de maternal, estilo plano y alegre,"
          " dividida en 3 paneles horizontales, uno por actividad, cada panel con su titulo exacto"
          " y una ilustracion alusiva (sin texto largo, sin logos, sin siglas SEP, sin marcas de agua)."
          f" Panel 1 titulo: '{tits[0]}'. Panel 2 titulo: '{tits[1]}'. Panel 3 titulo: '{tits[2]}'.")
    t0 = time.monotonic()
    r2 = client.responses.create(
        model=MODEL_IMAGE,
        input=[{"role": "user", "content": [{"type": "input_text", "text": fp}]}],
        tools=[{"type": "image_generation"}], timeout=IMAGE_TIMEOUT)
    b64 = ""
    for item in r2.output or []:
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
        raise RuntimeError(f"Image run{idx} no devolvio imagen")
    data = base64.b64decode(b64)
    fmt = B.detectar_formato(data)
    if fmt is None:
        raise RuntimeError(f"Image run{idx} bytes magicos desconocidos: {data[:12]!r}")
    if any("SEP" in t.upper() for t in tits):
        raise RuntimeError(f"titulo con SEP prohibido: {tits}")
    from PIL import Image as PILImage
    img = PILImage.open(io.BytesIO(data)).convert("RGB")
    img.save(OUT_DIR / f"ficha_run{idx}.png", "PNG")
    nbytes = (OUT_DIR / f"ficha_run{idx}.png").stat().st_size
    t_img = round(time.monotonic() - t0, 2)
    image = {"modelo_efectivo": MODEL_IMAGE, "timeout_s": IMAGE_TIMEOUT,
             "max_retries": 0, "estado": "real", "archivo": f"ficha_run{idx}.png",
             "formato_magic": "png", "formato_origen": fmt, "bytes": nbytes,
             "titulos": tits, "tiempo_s": t_img, "sin_sep": True}
    (OUT_DIR / f"ficha_run{idx}_raw.json").write_text(
        json.dumps({**image, "prompt": fp}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"[Image r{idx}] ficha_run{idx}.png {nbytes}B origen={fmt} t={t_img}s")
    lat = round(time.monotonic() - t_global, 2)
    run_n = {
        "etapa": "C1", "run": "002", "iteracion": idx,
        "fecha_utc": datetime.now(timezone.utc).isoformat(),
        "foto": "salon.jpg (Flow validada, 1024x765)",
        "sam_t_s": round(sam_t, 2), "spark_t_s": t_spark, "image_t_s": t_img,
        "latencia_total_s": lat,
        "llamadas_sam": llamadas_sam, "llamadas_spark": 1, "llamadas_image": 1,
        "llamadas_voice": 0, "llamadas_nuevas": llamadas_sam + 2,
        "max_retries": 0, "out_tocado": False, "fallback_usado": False,
        "sam": sam_res,
        "voice": {"estado": "demo", "origen_modelo": "espeak-sintetico",
                  "llamadas": 0, "tiempo_s": 0.0},
        "spark": spark, "image": image,
    }
    (OUT_DIR / f"run_n{idx}.json").write_text(
        json.dumps(run_n, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[C1 r{idx}] lat={lat}s (sam {round(sam_t,2)} + spark {t_spark} + img {t_img})")
    return run_n


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    s = load_settings()
    client = OpenAI(base_url=s.base_url, api_key=s.api_key, max_retries=0, timeout=120)
    foto = REPO / "salon.jpg"
    assert foto.is_file(), "FALLO: no existe salon.jpg"
    image_b64 = base64.b64encode(foto.read_bytes()).decode("ascii")
    runs = [run_chain(client, image_b64, foto, i) for i in (1, 2, 3)]
    lats = sorted(r["latencia_total_s"] for r in runs)
    prom = {
        "etapa": "C1", "n": 3, "latencias_s": lats,
        "p50_s": round(statistics.median(lats), 2),
        "p90_s": round(lats[0] * 0.1 + lats[-1] * 0.9, 2),
        "media_s": round(statistics.mean(lats), 2),
        "min_s": lats[0], "max_s": lats[-1],
        "llamadas_nuevas_total": sum(r["llamadas_nuevas"] for r in runs),
        "nota": "p50=mediana n=3; p90=interpolacion lineal min-max (n=3, aprox). "
                "Cadena por corrida = SAM+Spark+Image (Voice demo 0s).",
    }
    (OUT_DIR / "promedio.json").write_text(
        json.dumps(prom, ensure_ascii=False, indent=2), encoding="utf-8")
    # etiquetas.json desde run_n3 (misma forma que B)
    r3 = runs[2]
    etiquetas = []
    for concepto, tag, _ in B.CONCEPTS:
        r = r3["sam"].get(tag, {})
        etiquetas.append({
            "id": f"FOTO-{tag}", "categoria": "material_foto",
            "descripcion_libre": f"{B.GLOSARIO_ES[concepto]} ({concepto})",
            "n_instancias": r.get("n_cajas", 0),
            "visible_en_foto": (r.get("n_cajas", 0) or 0) > 0,
            "procedencia": "foto", "origen_modelo": "sam-3.1",
            "estado": r.get("estado", "no_llamado")})
    for i, m in enumerate(parse_materiales_desde_voz(DEMO_TRANSCRIPTION), 1):
        etiquetas.append({"id": f"VOZ-{i:02d}", "categoria": "material_voz",
                          "descripcion_libre": m, "n_instancias": 1,
                          "visible_en_foto": False, "procedencia": "voz",
                          "origen_modelo": "espeak-sintetico", "estado": "demo"})
    (OUT_DIR / "etiquetas.json").write_text(
        json.dumps({"etiquetas": etiquetas,
                    "nota_fusion": "Sin fusion foto+voz por texto: no hay IoU "
                    "entre modalidades ni confirmacion de educadora; procedencias "
                    "se conservan separadas."},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    run = {
        "etapa": "C1", "run": "002",
        "fecha_utc": datetime.now(timezone.utc).isoformat(),
        "foto": "salon.jpg (Flow validada, 1024x765)",
        "n": 3, "latencias_s": lats,
        "promedio": prom,
        "sam": r3["sam"], "voice": r3["voice"],
        "spark": r3["spark"], "image": r3["image"],
        "etiquetas_archivo": "etiquetas.json",
        "out_tocado": False, "fallback_usado": False, "max_retries": 0,
    }
    (OUT_DIR / "run.json").write_text(
        json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(prom, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
