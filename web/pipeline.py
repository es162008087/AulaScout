"""Pipeline real para la web: Voice + SAM 3.1 + Spark 1.3 + Image 1.0.

Derivado de runs/002/JUECES_SIM_03NOV/etapa_sim.py (max_retries=0, sin fallback).
Uso: run_pipeline(foto, audio, out_dir) -> dict run. Una corrida a la vez (globals).
"""

from __future__ import annotations

import base64
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "runs" / "002" / "A"))
sys.path.insert(0, str(REPO / "runs" / "002" / "B"))

from openai import OpenAI  # noqa: E402
from PIL import Image  # noqa: E402

import etapa_a as A  # noqa: E402
import etapa_b as B  # noqa: E402
from src.config import load_settings  # noqa: E402
from src.voice import (  # noqa: E402
    DEMO_TRANSCRIPTION,
    VOZ_A_OFICIAL,
    parse_materiales_desde_voz,
    transcribir_audio,
)

OUT_DIR = REPO  # se fija en run_pipeline
MODEL_SPARK = "muse-spark-1.3"
MODEL_IMAGE = "muse-image-1.0"
MODEL_VOICE = "muse-voice-transcribe-1.0"
SPARK_MAX_TOKENS = 6000  # web: 3500 truncaba (finish=length x3 el 3-nov); 6000 deja margen al razonamiento
SPARK_TIMEOUT = 120
SPARK_MAX_ATTEMPTS = 3
IMAGE_TIMEOUT = 90

CONCEPTS = B.CONCEPTS
GLOSARIO_ES = B.GLOSARIO_ES

NEG_RE = __import__("re").compile(r"(?i)\b(no tengo|no hay|no tiene|sin )\b")


def split_afirmado_negado(transcripcion: str) -> tuple[str, list[str]]:
    """Separa clausulas afirmadas de negadas; devuelve (texto_afirmado, keywords_negadas)."""
    afirmadas: list[str] = []
    negadas: list[str] = []
    for chunk in __import__("re").split(r"[.;]", transcripcion):
        bajo = chunk.strip().lower()
        if not bajo:
            continue
        kws = [kw for kw in VOZ_A_OFICIAL if kw in bajo]
        if NEG_RE.search(chunk) and kws:
            negadas.extend(k for k in kws if k not in negadas)
        elif bajo:
            afirmadas.append(chunk.strip())
    return " ".join(afirmadas), negadas


def _run_concept(client: OpenAI, image_b64: str, concept: str, tag: str) -> dict:
    t0 = time.monotonic()
    result: dict = {"concepto": concept, "modelo_efectivo": A.MODEL_SAM,
                    "max_retries": 0}
    try:
        raw, meta, elapsed = A.segment_concept(client, image_b64, concept)
    except Exception as exc:
        result.update(
            {"estado": "fallo", "error": f"{type(exc).__name__}: {exc}",
             "transitorio_429_5xx": B.is_transient_api_error(exc),
             "tiempo_s": round(time.monotonic() - t0, 2)}
        )
        (OUT_DIR / f"{tag}_raw.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
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
        {
            "estado": "real",
            "n_cajas": len(records),
            "n_mascaras": n_decode_ok,
            "tiempo_s": round(elapsed, 2),
            **meta,
            "records": [
                {"frame": r["frame"], "object_id": r["object_id"], "box": r["box"],
                 "mask_h": r["mask"]["h"], "mask_w": r["mask"]["w"],
                 "mask_enc": r["mask"]["enc"], "mask_c": r["mask"]["c"]}
                for r in records
            ],
            "raw_sanitizado": A.sanitize_raw(raw),
        }
    )
    (OUT_DIR / f"{tag}_raw.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def _overlay_for(result: dict, tag: str, foto: Path) -> tuple[str | None, bool | None]:
    if result.get("estado") != "real" or not result.get("n_cajas"):
        return None, None
    recs: list[dict] = []
    for line in result["raw_sanitizado"].splitlines():
        recs.extend(A.parse_line(line))
    dest = OUT_DIR / f"{tag}_overlay.png"
    ok = A.draw_overlay(foto, recs, dest)
    return dest.name, ok


def run_pipeline(foto: Path, audio: Path, out_dir: Path) -> dict:
    global OUT_DIR
    OUT_DIR = Path(out_dir)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    settings = load_settings()
    client = OpenAI(base_url=settings.base_url, api_key=settings.api_key,
                    max_retries=0, timeout=120)
    foto = Path(foto)
    audio = Path(audio)
    image_b64 = base64.b64encode(foto.read_bytes()).decode("ascii")

    t_global = time.monotonic()
    llamadas_sam = 0
    sam_resumen: dict[str, dict] = {}
    sam_abortado = False

    for concepto, tag, alt in CONCEPTS:
        if sam_abortado:
            sam_resumen[tag] = {"concepto": concepto, "estado": "no_llamado",
                                "motivo": "aborto 429/5xx previo"}
            continue
        res = _run_concept(client, image_b64, concepto, tag)
        llamadas_sam += 1
        if res.get("estado") == "fallo" and res.get("transitorio_429_5xx"):
            sam_abortado = True
            sam_resumen[tag] = {k: v for k, v in res.items()
                                if k not in ("raw_sanitizado", "records")}
            continue
        if res.get("estado") == "real" and res.get("n_cajas") == 0 and alt:
            res_alt = _run_concept(client, image_b64, alt, f"{tag}_alt")
            llamadas_sam += 1
            if res_alt.get("estado") == "real" and res_alt.get("n_cajas", 0) > 0:
                res_alt["concepto_original"] = concepto
                res = res_alt
                tag_ef = f"{tag}_alt"
            else:
                res["alternativa_probada"] = alt
                res["alternativa_resultado"] = (
                    f"{res_alt.get('n_cajas', '?')} cajas, "
                    f"{res_alt.get('n_mascaras', '?')} mascaras")
                (OUT_DIR / f"{tag}_raw.json").write_text(
                    json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
                tag_ef = tag
        else:
            tag_ef = tag
        overlay_name, overlay_ok = _overlay_for(res, tag_ef, foto)
        sam_resumen[tag] = {k: v for k, v in res.items()
                            if k not in ("raw_sanitizado", "records")}
        sam_resumen[tag]["overlay"] = overlay_name
        sam_resumen[tag]["overlay_mascaras_ok"] = overlay_ok
        print(f"[SAM] {concepto}: estado={res.get('estado')} "
              f"cajas={res.get('n_cajas')} masks={res.get('n_mascaras')} "
              f"t={res.get('tiempo_s')}s overlay={overlay_name}", flush=True)

    # --- Voice REAL (nota humana, WAV 16kHz, audioEncoding WAV) ---
    t0 = time.monotonic()
    voice_info: dict = {"modelo_efectivo": MODEL_VOICE, "audio": audio.name,
                        "max_retries": 0}
    try:
        transcripcion = transcribir_audio(audio, settings)
        t_voice = round(time.monotonic() - t0, 2)
        es_demo = transcripcion.strip() == DEMO_TRANSCRIPTION.strip()
        afirmado, negadas_kw = split_afirmado_negado(transcripcion)
        voz_presentes = parse_materiales_desde_voz(afirmado)
        voz_negados = [VOZ_A_OFICIAL[k] for k in negadas_kw
                       if VOZ_A_OFICIAL[k] not in voz_presentes]
        voice_info.update(
            {"estado": "demo" if es_demo else "real",
             "transcripcion": transcripcion,
             "tiempo_s": t_voice, "llamadas": 1,
             "materiales_presentes": voz_presentes,
             "materiales_negados": voz_negados})
        (OUT_DIR / "transcripcion.txt").write_text(transcripcion + "\n",
                                                   encoding="utf-8")
        print(f"[Voice] estado={voice_info['estado']} {t_voice}s "
              f"presentes={voz_presentes} negados={voz_negados}", flush=True)
    except Exception as exc:
        voice_info.update(
            {"estado": "fallo", "error": f"{type(exc).__name__}: {exc}",
             "tiempo_s": round(time.monotonic() - t0, 2), "llamadas": 1})
        voz_presentes, voz_negados = [], []
        print(f"[Voice] FALLO {exc}", flush=True)

    # --- Materiales con ID y procedencia (sin fusion por texto) ---
    materiales: list[dict] = []
    for concepto, tag, _ in CONCEPTS:
        r = sam_resumen.get(tag, {})
        materiales.append({
            "id": f"FOTO-{tag}",
            "concepto_en": concepto,
            "nombre_es": GLOSARIO_ES[concepto],
            "n_cajas": r.get("n_cajas", 0),
            "n_mascaras": r.get("n_mascaras", 0),
            "procedencia": "foto",
            "origen_modelo": "sam-3.1",
            "estado": r.get("estado", "no_llamado"),
        })
    for i, m in enumerate(voz_presentes, 1):
        materiales.append({
            "id": f"VOZ-{i:02d}",
            "concepto_en": None,
            "nombre_es": m,
            "procedencia": "voz",
            "origen_modelo": "muse-voice-transcribe-1.0",
            "estado": voice_info.get("estado", "fallo"),
        })
    for i, m in enumerate(voz_negados, 1):
        materiales.append({
            "id": f"VOZ-NEG-{i:02d}",
            "concepto_en": None,
            "nombre_es": m,
            "procedencia": "voz",
            "origen_modelo": "muse-voice-transcribe-1.0",
            "estado": voice_info.get("estado", "fallo"),
            "negacion": True,
            "nota": "negacion en voz ('no tengo...'): conservada sin categoria, "
                    "no disponible para planificar (3.2)",
        })
    (OUT_DIR / "materiales.json").write_text(
        json.dumps(materiales, ensure_ascii=False, indent=2), encoding="utf-8")

    # --- Spark 1.3 (3500, temp 0, finish stop + validador) ---
    spark_prompt = B.build_spark_prompt(materiales)
    spark_info: dict = {"modelo_efectivo": MODEL_SPARK,
                        "max_tokens": SPARK_MAX_TOKENS, "temperature": 0.0,
                        "timeout_s": SPARK_TIMEOUT, "max_retries": 0}
    texto = ""
    intentos: list[dict] = []
    for intento in range(1, SPARK_MAX_ATTEMPTS + 1):
        t0 = time.monotonic()
        try:
            resp = client.chat.completions.create(
                model=MODEL_SPARK,
                messages=[
                    {"role": "system",
                     "content": "Eres educadora SEP experta de maternal."},
                    {"role": "user", "content": spark_prompt},
                ],
                max_tokens=SPARK_MAX_TOKENS,
                temperature=0.0,
                timeout=SPARK_TIMEOUT,
            )
            texto_try = (resp.choices[0].message.content or "").strip()
            finish = resp.choices[0].finish_reason
            dt = round(time.monotonic() - t0, 2)
            val = B.validar_planeacion(texto_try)
            ok = finish == "stop" and val["valido"]
            intentos.append({"intento": intento, "finish_reason": finish,
                             "respuesta_chars": len(texto_try),
                             "validador": val, "tiempo_s": dt,
                             "estado": "real" if ok else "fallo"})
            print(f"[Spark] intento{intento} finish={finish} "
                  f"chars={len(texto_try)} val={val['valido']} {dt}s", flush=True)
            if ok:
                texto = texto_try
                break
            texto = texto_try
        except Exception as exc:
            dt = round(time.monotonic() - t0, 2)
            intentos.append({"intento": intento, "estado": "fallo",
                             "error": f"{type(exc).__name__}: {exc}",
                             "tiempo_s": dt})
            print(f"[Spark] intento{intento} FALLO {exc}", flush=True)
    ultimo_ok = next((i for i in reversed(intentos)
                      if i.get("estado") == "real"), None)
    if ultimo_ok is not None:
        spark_info.update(
            {"estado": "real",
             "finish_reason": ultimo_ok["finish_reason"],
             "tiempo_s": ultimo_ok["tiempo_s"],
             "prompt_chars": len(spark_prompt),
             "respuesta_chars": ultimo_ok["respuesta_chars"],
             "validador": ultimo_ok["validador"],
             "intentos": intentos})
        (OUT_DIR / "planeacion.md").write_text(texto + "\n", encoding="utf-8")
        (OUT_DIR / "planeacion_raw.json").write_text(
            json.dumps({**spark_info, "prompt": spark_prompt, "respuesta": texto},
                       ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        spark_info.update({"estado": "fallo", "intentos": intentos,
                           "error": "sin intento stop+valido"})
        print("[Spark] FALLO total", flush=True)

    # --- Image 1.0 (3 paneles, 3 titulos, sin SEP) ---
    image_info: dict = {"modelo_efectivo": MODEL_IMAGE, "timeout_s": IMAGE_TIMEOUT,
                        "max_retries": 0}
    if spark_info.get("estado") == "real":
        titulos = B.extraer_titulos(texto)
        ficha_prompt = (
            "Ficha visual infantil para aula de maternal, estilo plano y alegre, "
            "dividida en 3 paneles horizontales (uno por actividad), con titulos "
            f"cortos: {'; '.join(titulos) if titulos else 'juego libre'}. "
            "Sin texto largo, sin logos, sin siglas SEP, sin marcas de agua."
        )
        t0 = time.monotonic()
        try:
            resp = client.responses.create(
                model=MODEL_IMAGE,
                input=[{"role": "user", "content": [
                    {"type": "input_text", "text": ficha_prompt}]}],
                tools=[{"type": "image_generation"}],
                timeout=IMAGE_TIMEOUT,
            )
            b64 = ""
            for item in resp.output or []:
                d = item if isinstance(item, dict) else getattr(
                    item, "model_dump", lambda: {})()
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
            fmt = B.detectar_formato(data)
            if fmt is None:
                raise ValueError(f"bytes magicos desconocidos: {data[:12]!r}")
            if fmt == "webp":
                import io
                img = Image.open(io.BytesIO(data)).convert("RGB")
                img.save(OUT_DIR / "ficha.png", "PNG")
                fmt = "png (convertido desde webp con PIL)"
            else:
                (OUT_DIR / "ficha.png").write_bytes(data)
            image_info.update(
                {"estado": "real", "archivo": "ficha.png", "formato_magic": fmt,
                 "bytes": (OUT_DIR / "ficha.png").stat().st_size,
                 "titulos": titulos,
                 "tiempo_s": round(time.monotonic() - t0, 2)})
            (OUT_DIR / "ficha_raw.json").write_text(
                json.dumps({**image_info, "prompt": ficha_prompt},
                           ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"[Image] ficha.png {image_info['bytes']}B magic={fmt}", flush=True)
        except Exception as exc:
            image_info.update(
                {"estado": "fallo", "error": f"{type(exc).__name__}: {exc}",
                 "tiempo_s": round(time.monotonic() - t0, 2)})
            print(f"[Image] FALLO {exc}", flush=True)
    else:
        image_info.update({"estado": "no_llamado",
                           "motivo": "Spark fallo, sin 3 titulos para ficha"})
        print("[Image] no llamado (Spark fallo)", flush=True)

    # --- etiquetas.json ---
    etiquetas: list[dict] = []
    for m in materiales:
        if m["procedencia"] == "foto":
            etiquetas.append({
                "id": m["id"], "categoria": "material_foto",
                "descripcion_libre": f"{m['nombre_es']} ({m['concepto_en']})",
                "n_instancias": m["n_cajas"],
                "visible_en_foto": m["n_cajas"] > 0,
                "procedencia": "foto", "origen_modelo": "sam-3.1",
                "estado": m["estado"],
            })
        elif m.get("negacion"):
            etiquetas.append({
                "id": m["id"], "categoria": "material_voz_negado",
                "descripcion_libre": m["nombre_es"], "n_instancias": 0,
                "visible_en_foto": False,
                "procedencia": "voz", "origen_modelo": "muse-voice-transcribe-1.0",
                "estado": m["estado"], "negacion": True,
                "nota": m["nota"],
            })
        else:
            etiquetas.append({
                "id": m["id"], "categoria": "material_voz",
                "descripcion_libre": m["nombre_es"], "n_instancias": 1,
                "visible_en_foto": False,
                "procedencia": "voz",
                "origen_modelo": "muse-voice-transcribe-1.0",
                "estado": m["estado"],
            })
    (OUT_DIR / "etiquetas.json").write_text(
        json.dumps({"etiquetas": etiquetas,
                    "foto_origen": "foto subida por el usuario",
                    "voz_origen": "audio subido por el usuario",
                    "nota_fusion": "Sin fusion foto+voz por texto: no hay IoU "
                    "entre modalidades ni confirmacion de educadora; procedencias "
                    "se conservan separadas. Negaciones conservadas sin categoria."},
                   ensure_ascii=False, indent=2), encoding="utf-8")

    # --- run.json ---
    latencia = round(time.monotonic() - t_global, 2)
    llamadas_image = 1 if image_info.get("estado") != "no_llamado" else 0
    llamadas_total = llamadas_sam + 1 + len(intentos) + llamadas_image
    run = {
        "etapa": "web", "run": "002",
        "fecha_utc": datetime.now(timezone.utc).isoformat(),
        "foto": foto.name,
        "audio": audio.name,
        "latencia_total_s_n1": latencia,
        "llamadas_nuevas": llamadas_total,
        "llamadas_sam": llamadas_sam,
        "llamadas_voice": 1,
        "llamadas_spark": len(intentos),
        "llamadas_image": llamadas_image,
        "reintentos": 0, "max_retries": 0,
        "out_tocado": "ninguno",
        "fallback_usado": False,
        "sam_abortado_429_5xx": sam_abortado,
        "sam": sam_resumen,
        "voice": voice_info,
        "spark": spark_info,
        "image": image_info,
        "desvios": [
            "Corrida web: foto y audio subidos por el usuario.",
        ],
    }
    (OUT_DIR / "run.json").write_text(
        json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[VIDEO] latencia total n=1: {latencia}s, llamadas nuevas: {llamadas_total}",
          flush=True)

    run["ok"] = spark_info.get("estado") == "real"
    return run
