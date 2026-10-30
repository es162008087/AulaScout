"""Etapa C2 (002): robustez x4 escenas variadas, n=1 por escena.

Uso:
  uv run python runs/002/C2/etapa_c2.py

Escenas generadas con PIL desde salon.jpg (sin costo API):
  escena1 = original (baseline)
  escena2 = iluminacion alta calida + zoom central (angulo distinto)
  escena3 = iluminacion baja fria + rotacion leve (angulo distinto)
  escena4 = recorte lateral derecho reescalado + contraste (encuadre distinto,
             enfasis estante/bandejas)

Por escena: SAM 6 conceptos EN + 1 alt max si 0, Voice DEMO (0 llamadas),
Spark 3500 temp 0 (3 acts, Seguridad x3), Image 3 paneles PNG.
Salidas por escena en runs/002/C2/escena{i}/:
  foto.jpg, etiquetas.json, run.json, overlay_<tag>.png, ficha.png,
  ficha_raw.json, planeacion.md, sam_<tag>_raw.json
Top-level runs/002/C2/run.json con latencias y costo por escena. No toca out/.
"""
from __future__ import annotations

import base64
import io
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "runs" / "002" / "A"))
sys.path.insert(0, str(REPO / "runs" / "002" / "B"))

from openai import OpenAI  # noqa: E402
from PIL import Image as PILImage, ImageEnhance  # noqa: E402

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


def make_scenes(foto: Path) -> list[tuple[int, str, Path]]:
    base = PILImage.open(foto).convert("RGB")
    w, h = base.size
    scenes: list[tuple[int, str, PILImage.Image]] = []
    scenes.append((1, "original baseline (Flow validada)", base))
    # escena2: iluminacion alta calida + zoom central 90%
    e2 = base.crop((int(w * 0.05), int(h * 0.05), int(w * 0.95), int(h * 0.95)))
    e2 = e2.resize((w, h))
    e2 = ImageEnhance.Brightness(e2).enhance(1.25)
    e2 = ImageEnhance.Color(e2).enhance(1.15)
    scenes.append((2, "iluminacion alta calida + zoom central (angulo distinto)", e2))
    # escena3: iluminacion baja fria + rotacion leve
    e3 = ImageEnhance.Brightness(base).enhance(0.7)
    r, g, b = e3.split()
    e3 = PILImage.merge("RGB", (r.point(lambda v: int(v * 0.9)),
                                g.point(lambda v: int(v * 0.95)),
                                b.point(lambda v: min(255, int(v * 1.1)))))
    e3 = e3.rotate(4, resample=PILImage.BICUBIC, expand=False)
    scenes.append((3, "iluminacion baja fria + rotacion 4deg (angulo distinto)", e3))
    # escena4: recorte mitad derecha + contraste (enfasis estante/bandejas)
    e4 = base.crop((int(w * 0.4), 0, w, h))
    e4 = e4.resize((w, h))
    e4 = ImageEnhance.Contrast(e4).enhance(1.3)
    scenes.append((4, "recorte lateral derecho + contraste (encuadre distinto)", e4))
    out = []
    for idx, desc, img in scenes:
        d = OUT_DIR / f"escena{idx}"
        d.mkdir(parents=True, exist_ok=True)
        p = d / "foto.jpg"
        img.save(p, "JPEG", quality=92)
        out.append((idx, desc, p))
        print(f"[escena{idx}] {desc} -> {p} {p.stat().st_size}B {img.size}")
    return out


def run_concept_to(client: OpenAI, image_b64: str, concept: str,
                   dest: Path, scene_dir: Path) -> dict:
    t0 = time.monotonic()
    result: dict = {"concepto": concept, "modelo_efectivo": A.MODEL_SAM,
                    "max_retries": 0}
    try:
        raw, meta, elapsed = A.segment_concept(client, image_b64, concept)
    except Exception as exc:
        result.update(
            {"estado": "fallo", "error": f"{type(exc).__name__}: {exc}",
             "transitorio_429_5xx": B.is_transient_api_error(exc),
             "tiempo_s": round(time.monotonic() - t0, 2)})
        dest.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                        encoding="utf-8")
        return result
    records: list[dict] = []
    for line in raw.splitlines():
        records.extend(A.parse_line(line))
    n_decode_ok = 0
    for rec in records:
        try:
            if A.decode_record_mask(rec) is not None:
                n_decode_ok += 1
        except Exception:
            pass
    result.update(
        {"estado": "real", "n_cajas": len(records), "n_mascaras": n_decode_ok,
         "tiempo_s": round(elapsed, 2), **meta,
         "records": [
             {"frame": r["frame"], "object_id": r["object_id"], "box": r["box"],
              "mask_h": r["mask"]["h"], "mask_w": r["mask"]["w"],
              "mask_enc": r["mask"]["enc"], "mask_c": r["mask"]["c"]}
             for r in records],
         "raw_sanitizado": A.sanitize_raw(raw)})
    dest.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    return result


def run_scene(client: OpenAI, idx: int, desc: str, foto: Path) -> dict:
    sdir = OUT_DIR / f"escena{idx}"
    sdir.mkdir(parents=True, exist_ok=True)
    image_b64 = base64.b64encode(foto.read_bytes()).decode("ascii")
    t_global = time.monotonic()
    llamadas_sam = 0
    sam_res: dict[str, dict] = {}
    sam_t = 0.0
    overlays: dict[str, str | None] = {}
    for concepto, tag, alt in B.CONCEPTS:
        res = run_concept_to(client, image_b64, concepto,
                             sdir / f"sam_{tag}_raw.json", sdir)
        llamadas_sam += 1
        if res.get("estado") == "real" and res.get("n_cajas") == 0 and alt:
            res_alt = run_concept_to(client, image_b64, alt,
                                     sdir / f"sam_{tag}_alt_raw.json", sdir)
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
        # overlay con cajas/mascaras si hay detecciones
        ov_name = None
        if res.get("estado") == "real" and res.get("n_cajas"):
            recs: list[dict] = []
            for line in res["raw_sanitizado"].splitlines():
                recs.extend(A.parse_line(line))
            dest = sdir / f"overlay_{tag}.png"
            if A.draw_overlay(foto, recs, dest):
                ov_name = dest.name
        overlays[tag] = ov_name
        print(f"[SAM e{idx}] {concepto}: {res.get('estado')} "
              f"cajas={res.get('n_cajas')} mascaras={res.get('n_mascaras')} "
              f"t={res.get('tiempo_s')}s overlay={ov_name}")
    # Voice DEMO
    voz_mats = parse_materiales_desde_voz(DEMO_TRANSCRIPTION)
    materiales: list[dict] = []
    for concepto, tag, _ in B.CONCEPTS:
        r = sam_res.get(tag, {})
        materiales.append({
            "id": f"E{idx}-{tag}", "concepto_en": concepto,
            "nombre_es": B.GLOSARIO_ES[concepto],
            "n_cajas": r.get("n_cajas", 0),
            "procedencia": "foto", "origen_modelo": "sam-3.1",
            "estado": r.get("estado", "no_llamado")})
    for i, m in enumerate(voz_mats, 1):
        materiales.append({"id": f"E{idx}-VOZ-{i:02d}", "concepto_en": None,
                           "nombre_es": m, "procedencia": "voz",
                           "origen_modelo": "espeak-sintetico", "estado": "demo"})
    # Spark 3500 (hasta 2 intentos documentados, precedente B: reasoning
    # oculto puede truncar el intento 1 con finish=length)
    spark_prompt = B.build_spark_prompt(materiales) + PROMPT_EXTRA
    llamadas_spark = 0
    intentos_spark: list[dict] = []
    while True:
        llamadas_spark += 1
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
        intentos_spark.append({"intento": llamadas_spark, "finish_reason": finish,
                               "respuesta_chars": len(texto),
                               "usage": dump.get("usage"), "tiempo_s": t_spark})
        print(f"[Spark e{idx}] intento{llamadas_spark} finish={finish} "
              f"chars={len(texto)} t={t_spark}s val={val}")
        if finish == "stop" and val["valido"]:
            break
        if llamadas_spark >= 2:
            break
        print(f"[Spark e{idx}] reintento documentado (precedente B)")
    spark = {"modelo_efectivo": MODEL_SPARK, "max_tokens": SPARK_MAX_TOKENS,
             "timeout_s": SPARK_TIMEOUT, "max_retries": 0,
             "finish_reason": finish, "tiempo_s": t_spark,
             "prompt_chars": len(spark_prompt), "respuesta_chars": len(texto),
             "usage": dump.get("usage"), "estado": "real", "validador": val,
             "intentos": intentos_spark, "llamadas_spark": llamadas_spark}
    if finish != "stop" or not val["valido"]:
        spark["estado"] = "fallo"
        spark["error"] = f"finish={finish} valido={val['valido']} {val}"
        (sdir / "spark_dump.json").write_text(
            json.dumps({"tiempo_s": t_spark, "dump": dump},
                       ensure_ascii=False, indent=2)[:8000], encoding="utf-8")
        raise RuntimeError(f"Spark escena{idx} fallo tras {llamadas_spark} intentos: {spark['error']}")
    (sdir / "planeacion.md").write_text(texto + "\n", encoding="utf-8")
    import re as _re
    _tit_re = _re.compile(r"(?m)^\s*(?:\*\*)?Titulo:(?:\*\*)?\s*(.+?)\s*$")
    tits = _tit_re.findall(texto)[:3]
    if len(tits) != 3:
        tits = B.extraer_titulos(texto)
    if len(tits) != 3:
        raise RuntimeError(f"escena{idx}: se esperaban 3 titulos, hallados {tits}")
    print(f"[Spark e{idx}] titulos={tits}")
    # Image 3 paneles
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
        raise RuntimeError(f"Image escena{idx} no devolvio imagen")
    data = base64.b64decode(b64)
    fmt = B.detectar_formato(data)
    if fmt is None:
        raise RuntimeError(f"Image escena{idx} bytes magicos desconocidos: {data[:12]!r}")
    img = PILImage.open(io.BytesIO(data)).convert("RGB")
    img.save(sdir / "ficha.png", "PNG")
    nbytes = (sdir / "ficha.png").stat().st_size
    t_img = round(time.monotonic() - t0, 2)
    image = {"modelo_efectivo": MODEL_IMAGE, "timeout_s": IMAGE_TIMEOUT,
             "max_retries": 0, "estado": "real", "archivo": "ficha.png",
             "formato_magic": "png", "formato_origen": fmt, "bytes": nbytes,
             "titulos": tits, "tiempo_s": t_img, "sin_sep": True}
    (sdir / "ficha_raw.json").write_text(
        json.dumps({**image, "prompt": fp}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"[Image e{idx}] ficha.png {nbytes}B origen={fmt} t={t_img}s")
    # etiquetas.json
    etiquetas = []
    for concepto, tag, _ in B.CONCEPTS:
        r = sam_res.get(tag, {})
        etiquetas.append({
            "id": f"E{idx}-{tag}", "categoria": "material_foto",
            "descripcion_libre": f"{B.GLOSARIO_ES[concepto]} ({concepto})",
            "n_instancias": r.get("n_cajas", 0),
            "visible_en_foto": (r.get("n_cajas", 0) or 0) > 0,
            "procedencia": "foto", "origen_modelo": "sam-3.1",
            "estado": r.get("estado", "no_llamado"),
            "overlay": overlays.get(tag)})
    for i, m in enumerate(voz_mats, 1):
        etiquetas.append({"id": f"E{idx}-VOZ-{i:02d}", "categoria": "material_voz",
                          "descripcion_libre": m, "n_instancias": 1,
                          "visible_en_foto": False, "procedencia": "voz",
                          "origen_modelo": "espeak-sintetico", "estado": "demo"})
    (sdir / "etiquetas.json").write_text(
        json.dumps({"etiquetas": etiquetas,
                    "nota_fusion": "Sin fusion foto+voz por texto: no hay IoU "
                    "entre modalidades ni confirmacion de educadora; procedencias "
                    "se conservan separadas."},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    lat = round(time.monotonic() - t_global, 2)
    llamadas_nuevas = llamadas_sam + llamadas_spark + 1
    uso = dump.get("usage") or {}
    run = {
        "etapa": "C2", "run": "002", "escena": idx, "descripcion": desc,
        "fecha_utc": datetime.now(timezone.utc).isoformat(),
        "foto": f"escena{idx}/foto.jpg",
        "sam_t_s": round(sam_t, 2), "spark_t_s": t_spark, "image_t_s": t_img,
        "latencia_total_s": lat,
        "llamadas_sam": llamadas_sam, "llamadas_spark": llamadas_spark, "llamadas_image": 1,
        "llamadas_voice": 0, "llamadas_nuevas": llamadas_nuevas,
        "spark_usage": uso,
        "costo_estimado_usd": round(llamadas_nuevas * 0.0074, 4),
        "max_retries": 0, "out_tocado": False, "fallback_usado": False,
        "sam": sam_res,
        "voice": {"estado": "demo", "origen_modelo": "espeak-sintetico",
                  "llamadas": 0, "tiempo_s": 0.0},
        "spark": spark, "image": image,
    }
    (sdir / "run.json").write_text(
        json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[C2 e{idx}] lat={lat}s (sam {round(sam_t,2)} + spark {t_spark} + img {t_img}) "
          f"llamadas={llamadas_nuevas}")
    return run


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    s = load_settings()
    client = OpenAI(base_url=s.base_url, api_key=s.api_key, max_retries=0, timeout=120)
    foto = REPO / "salon.jpg"
    assert foto.is_file(), "FALLO: no existe salon.jpg"
    scenes = make_scenes(foto)
    runs = [run_scene(client, idx, desc, p) for idx, desc, p in scenes]
    lats = [r["latencia_total_s"] for r in runs]
    total_llam = sum(r["llamadas_nuevas"] for r in runs)
    run = {
        "etapa": "C2", "run": "002",
        "fecha_utc": datetime.now(timezone.utc).isoformat(),
        "foto_base": "salon.jpg (Flow validada, 1024x765)",
        "n_escenas": 4, "n_por_escena": 1,
        "latencias_por_escena_s": lats,
        "latencia_total_s": round(sum(lats), 2),
        "llamadas_nuevas_total": total_llam,
        "costo_estimado_usd_total": round(sum(r["costo_estimado_usd"] for r in runs), 4),
        "costo_declarado": "$40 etapa (acumulado $72/$120)",
        "escenas": runs,
        "max_retries": 0, "out_tocado": False, "fallback_usado": False,
    }
    (OUT_DIR / "run.json").write_text(
        json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"latencias": lats, "llamadas_total": total_llam}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
