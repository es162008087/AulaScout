"""Etapa B (002): corrida completa 1 escena — 6 SAM EN + Spark + Image.

Uso:
  uv run python runs/002/B/etapa_b.py

Salidas en runs/002/B/: <concepto>_raw.json, <concepto>_overlay.png,
planeacion.md, planeacion_raw.json, ficha.(png|webp), ficha_raw.json,
etiquetas.json, run.json. No toca out/. Voice queda DEMO marcado (sin llamada).
"""

from __future__ import annotations

import base64
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "runs" / "002" / "A"))

from openai import OpenAI  # noqa: E402

import etapa_a as A  # noqa: E402
from src.config import load_settings  # noqa: E402
from src.voice import DEMO_TRANSCRIPTION, parse_materiales_desde_voz  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent
MODEL_SPARK = "muse-spark-1.3"
MODEL_IMAGE = "muse-image-1.0"
SPARK_MAX_TOKENS = 2500
SPARK_TIMEOUT = 60
IMAGE_TIMEOUT = 90

# (concepto, tag_archivo, alternativa_si_0)
CONCEPTS: list[tuple[str, str, str | None]] = [
    ("mat", "mat", None),
    ("wooden blocks", "wooden_blocks", "toy blocks"),
    ("sensory balls in basket", "sensory_balls", "basket with balls"),
    ("fabric books", "fabric_books", "cloth books"),
    ("low wooden shelf", "low_shelf", "wooden shelf"),
    ("white trays", "white_trays", "trays"),
]

GLOSARIO_ES = {
    "mat": "tapete de foami",
    "wooden blocks": "bloques de madera",
    "sensory balls in basket": "pelotas sensoriales en canasta",
    "fabric books": "libros de tela",
    "low wooden shelf": "estante bajo de madera",
    "white trays": "bandejas blancas",
}

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def is_transient_api_error(exc: Exception) -> bool:
    s = str(exc)
    return "429" in s or "500" in s or "502" in s or "503" in s or "504" in s


def run_concept(client: OpenAI, image_b64: str, concept: str, tag: str) -> dict:
    t0 = time.monotonic()
    result: dict = {"concepto": concept, "modelo_efectivo": A.MODEL_SAM,
                    "max_retries": 0}
    try:
        raw, meta, elapsed = A.segment_concept(client, image_b64, concept)
    except Exception as exc:
        result.update(
            {"estado": "fallo", "error": f"{type(exc).__name__}: {exc}",
             "transitorio_429_5xx": is_transient_api_error(exc),
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


def overlay_for(result: dict, tag: str, foto: Path) -> tuple[str | None, bool | None]:
    if result.get("estado") != "real" or not result.get("n_cajas"):
        return None, None
    recs: list[dict] = []
    for line in result["raw_sanitizado"].splitlines():
        recs.extend(A.parse_line(line))
    dest = OUT_DIR / f"{tag}_overlay.png"
    ok = A.draw_overlay(foto, recs, dest)
    return dest.name, ok


def build_spark_prompt(materiales: list[dict]) -> str:
    lineas = "\n".join(
        f"- [{m['id']}] {m['nombre_es']} (procedencia: {m['procedencia']})"
        for m in materiales
    )
    return (
        "Eres educadora SEP de maternal (lactantes y maternal, 18 a 36 meses). "
        "Con estos materiales detectados en el salon:\n"
        f"{lineas}\n\n"
        "Genera una planeacion didactica en markdown con EXACTAMENTE 3 actividades "
        "de 20 minutos cada una, para edad 18-36 meses. "
        "Cada actividad DEBE tener estas 6 secciones con estos titulos exactos: "
        "Titulo, Edad, Objetivo, Materiales, Pasos, Seguridad. "
        "En Edad escribe siempre el rango 18-36 meses. "
        "En Seguridad incluye la regla de piezas pequenas (no usar piezas pequenas "
        "que quepan en la boca) y adaptacion de seguridad propia de la actividad. "
        "Cita los materiales por su [ID] tal como aparecen arriba. "
        "Responde SOLO con la planeacion markdown, sin introduccion ni cierre."
    )


def validar_planeacion(texto: str) -> dict:
    n_acts = len(re.findall(r"(?im)^#{1,3}\s+.+", texto))
    if n_acts < 3:
        n_acts = len(re.findall(r"(?i)actividad\s*\d", texto))
    n_seg = len(re.findall(r"(?i)seguridad", texto))
    tiene_edad = "18" in texto and "36" in texto
    tiene_piezas = bool(re.search(r"(?i)piezas?\s+peque", texto))
    ok = n_acts >= 3 and n_seg >= 3 and tiene_edad and tiene_piezas
    return {"n_actividades": n_acts, "n_seguridad": n_seg,
            "tiene_edad_18_36": tiene_edad, "tiene_piezas_pequenas": tiene_piezas,
            "valido": ok}


def extraer_titulos(texto: str) -> list[str]:
    heads = re.findall(r"(?m)^#{1,3}\s+(.+?)\s*$", texto)
    heads = [h for h in heads if "actividad" in h.lower()][:3]
    if len(heads) < 3:
        heads = re.findall(r"(?m)^#{1,3}\s+(.+?)\s*$", texto)[:3]
    return [h.strip() for h in heads][:3]


def detectar_formato(data: bytes) -> str | None:
    if data.startswith(PNG_MAGIC):
        return "png"
    if data.startswith(b"RIFF") and len(data) > 11 and data[8:12] == b"WEBP":
        return "webp"
    return None


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    settings = load_settings()
    client = OpenAI(base_url=settings.base_url, api_key=settings.api_key,
                    max_retries=0, timeout=120)
    foto = REPO / "salon.jpg"
    if not foto.is_file():
        print("FALLO: no existe salon.jpg", file=sys.stderr)
        return 1
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
        res = run_concept(client, image_b64, concepto, tag)
        llamadas_sam += 1
        if res.get("estado") == "fallo" and res.get("transitorio_429_5xx"):
            sam_abortado = True
            sam_resumen[tag] = {k: v for k, v in res.items()
                                if k not in ("raw_sanitizado", "records")}
            continue
        # 1 alternativa max si 0 genuino
        if res.get("estado") == "real" and res.get("n_cajas") == 0 and alt:
            res_alt = run_concept(client, image_b64, alt, f"{tag}_alt")
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
        overlay_name, overlay_ok = overlay_for(res, tag_ef, foto)
        sam_resumen[tag] = {k: v for k, v in res.items()
                            if k not in ("raw_sanitizado", "records")}
        sam_resumen[tag]["overlay"] = overlay_name
        sam_resumen[tag]["overlay_mascaras_ok"] = overlay_ok
        print(f"[SAM] {concepto}: estado={res.get('estado')} "
              f"cajas={res.get('n_cajas')} masks={res.get('n_mascaras')} "
              f"t={res.get('tiempo_s')}s overlay={overlay_name}")

    # --- Voice DEMO marcado (sin llamada) ---
    voz_mats = parse_materiales_desde_voz(DEMO_TRANSCRIPTION)
    voice_info = {
        "estado": "demo",
        "origen_modelo": "espeak-sintetico",
        "transcripcion": "DEMO: " + DEMO_TRANSCRIPTION,
        "materiales": voz_mats,
        "nota": "pendiente audio humano consentido 5-7s con negacion para video final",
        "llamadas": 0,
        "tiempo_s": 0.0,
    }
    print(f"[Voice] DEMO {len(voz_mats)} materiales (sin llamada)")

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
    for i, m in enumerate(voz_mats, 1):
        materiales.append({
            "id": f"VOZ-{i:02d}",
            "concepto_en": None,
            "nombre_es": m,
            "procedencia": "voz",
            "origen_modelo": "espeak-sintetico",
            "estado": "demo",
        })

    # --- Spark ---
    spark_prompt = build_spark_prompt(materiales)
    spark_info: dict = {"modelo_efectivo": MODEL_SPARK,
                        "max_tokens": SPARK_MAX_TOKENS,
                        "timeout_s": SPARK_TIMEOUT, "max_retries": 0}
    t0 = time.monotonic()
    try:
        resp = client.chat.completions.create(
            model=MODEL_SPARK,
            messages=[
                {"role": "system", "content": "Eres educadora SEP experta de maternal."},
                {"role": "user", "content": spark_prompt},
            ],
            max_tokens=SPARK_MAX_TOKENS,
            temperature=0.7,
            timeout=SPARK_TIMEOUT,
        )
        texto = (resp.choices[0].message.content or "").strip()
        finish = resp.choices[0].finish_reason
        spark_info.update(
            {"estado": "real", "finish_reason": finish,
             "tiempo_s": round(time.monotonic() - t0, 2),
             "prompt_chars": len(spark_prompt), "respuesta_chars": len(texto)})
        (OUT_DIR / "planeacion.md").write_text(texto + "\n", encoding="utf-8")
        (OUT_DIR / "planeacion_raw.json").write_text(
            json.dumps({**spark_info, "prompt": spark_prompt, "respuesta": texto},
                       ensure_ascii=False, indent=2), encoding="utf-8")
        val = validar_planeacion(texto)
        spark_info["validador"] = val
        if finish == "length":
            spark_info["estado"] = "fallo"
            spark_info["error"] = "plan truncado finish_reason=length"
        elif not val["valido"]:
            spark_info["estado"] = "fallo"
            spark_info["error"] = f"validador rechazo plan: {val}"
        print(f"[Spark] finish={finish} chars={len(texto)} validador={val}")
    except Exception as exc:
        spark_info.update(
            {"estado": "fallo", "error": f"{type(exc).__name__}: {exc}",
             "tiempo_s": round(time.monotonic() - t0, 2)})
        texto = ""
        print(f"[Spark] FALLO {exc}")

    # --- Image ---
    image_info: dict = {"modelo_efectivo": MODEL_IMAGE, "timeout_s": IMAGE_TIMEOUT,
                        "max_retries": 0}
    if spark_info.get("estado") == "real":
        titulos = extraer_titulos(texto)
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
            fmt = detectar_formato(data)
            if fmt is None:
                raise ValueError(
                    f"bytes magicos desconocidos: {data[:12]!r}")
            fname = f"ficha.{fmt}"
            (OUT_DIR / fname).write_bytes(data)
            image_info.update(
                {"estado": "real", "archivo": fname, "formato_magic": fmt,
                 "bytes": len(data), "titulos": titulos,
                 "tiempo_s": round(time.monotonic() - t0, 2)})
            (OUT_DIR / "ficha_raw.json").write_text(
                json.dumps({**image_info, "prompt": ficha_prompt},
                           ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"[Image] {fname} {len(data)}B magic={fmt}")
        except Exception as exc:
            image_info.update(
                {"estado": "fallo", "error": f"{type(exc).__name__}: {exc}",
                 "tiempo_s": round(time.monotonic() - t0, 2)})
            print(f"[Image] FALLO {exc}")
    else:
        image_info.update({"estado": "no_llamado",
                           "motivo": "Spark fallo, sin 3 titulos para ficha"})
        print("[Image] no llamado (Spark fallo)")

    # --- etiquetas.json ---
    etiquetas: list[dict] = []
    for i, m in enumerate(materiales, 1):
        if m["procedencia"] == "foto":
            etiquetas.append({
                "id": m["id"], "categoria": "material_foto",
                "descripcion_libre": f"{m['nombre_es']} ({m['concepto_en']})",
                "n_instancias": m["n_cajas"],
                "visible_en_foto": m["n_cajas"] > 0,
                "procedencia": "foto", "origen_modelo": "sam-3.1",
                "estado": m["estado"],
            })
        else:
            etiquetas.append({
                "id": m["id"], "categoria": "material_voz",
                "descripcion_libre": m["nombre_es"], "n_instancias": 1,
                "visible_en_foto": False,
                "procedencia": "voz", "origen_modelo": "espeak-sintetico",
                "estado": "demo",
            })
    (OUT_DIR / "etiquetas.json").write_text(
        json.dumps({"etiquetas": etiquetas,
                    "nota_fusion": "Sin fusion foto+voz por texto: no hay IoU "
                    "entre modalidades ni confirmacion de educadora; procedencias "
                    "se conservan separadas."},
                   ensure_ascii=False, indent=2), encoding="utf-8")

    # --- run.json ---
    latencia = round(time.monotonic() - t_global, 2)
    # Spark intento unico (siempre se llama); Image solo si Spark OK.
    llamadas_total = (llamadas_sam + 1
                      + (1 if image_info.get("estado") != "no_llamado" else 0))
    run = {
        "etapa": "B", "run": "002",
        "fecha_utc": datetime.now(timezone.utc).isoformat(),
        "foto": "salon.jpg (Flow validada, 1024x765)",
        "latencia_total_s_n1": latencia,
        "llamadas_nuevas": llamadas_total,
        "llamadas_sam": llamadas_sam,
        "llamadas_spark": 1,
        "llamadas_image": 1 if image_info.get("estado") != "no_llamado" else 0,
        "llamadas_voice": 0,
        "reintentos": 0, "max_retries": 0,
        "out_tocado": False, "fallback_usado": False,
        "sam_abortado_429_5xx": sam_abortado,
        "sam": sam_resumen,
        "voice": voice_info,
        "spark": spark_info,
        "image": image_info,
        "desvios": [
            "Voice sin llamada API: espeak-sintetico marcado demo (autorizado).",
            "No se repitio piano (control A OK).",
        ],
    }
    (OUT_DIR / "run.json").write_text(
        json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[B] latencia total n=1: {latencia}s, llamadas nuevas: {llamadas_total}")
    print(json.dumps({k: v for k, v in run.items()
                      if k not in ("sam", "spark", "image")},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
