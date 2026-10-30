"""Etapa A (002): SAM 3.1 por concepto, 2 llamadas, max_retries=0, sin fallback.

Uso:
  uv run python runs/002/A/etapa_a.py --self-test   # Etapa 0 offline, 0 llamadas
  uv run python runs/002/A/etapa_a.py               # Etapa A real (2 llamadas)

Salidas en runs/002/A/: tapete_raw.json, piano_raw.json, tapete_overlay.png, run.json.
No toca out/.
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from openai import OpenAI  # noqa: E402

from meta_sam_parser import SegmentationMask, decode_mask_to_raster  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402
from src.config import load_settings  # noqa: E402

MODEL_SAM = "sam-3.1"
TIMEOUT_S = 120
OUT_DIR = Path(__file__).resolve().parent

BOX_RE = re.compile(r"<\|box;([^|]*)\|>")
MASK_RE = re.compile(r"<\|mask;([^|]*)\|>")
RECORD_RE = re.compile(
    r"(?P<oid>\d+)<\|box;(?P<box>[^|]*)\|><\|mask;(?P<mask>[^|]*)\|>"
)
FRAME_RE = re.compile(r"<(?P<n>\d+)f>")


def parse_kv(body: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for chunk in body.split(";"):
        if "=" in chunk:
            k, v = chunk.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def parse_line(line: str) -> list[dict]:
    """Parsea una línea <Nf>id<|box|><|mask|>... según dev.meta.ai/docs/sam."""
    line = line.strip()
    if not line:
        return []
    m = FRAME_RE.match(line)
    frame = int(m.group("n")) if m else 0
    rest = line[m.end():] if m else line
    records: list[dict] = []
    for rm in RECORD_RE.finditer(rest):
        box = parse_kv(rm.group("box"))
        mask = parse_kv(rm.group("mask"))
        data = mask.get("data", "")
        dm = re.match(r"(?P<h>\d+),(?P<w>\d+),(?P<enc>[~!])(?P<payload>.*)$", data, re.S)
        records.append(
            {
                "frame": frame,
                "object_id": int(rm.group("oid")),
                "box": {
                    "x1": int(box["x1"]),
                    "y1": int(box["y1"]),
                    "x2": int(box["x2"]),
                    "y2": int(box["y2"]),
                    "w": int(box["w"]),
                    "h": int(box["h"]),
                    "c": float(box["c"]) if "c" in box else None,
                },
                "mask": {
                    "h": int(dm.group("h")) if dm else 0,
                    "w": int(dm.group("w")) if dm else 0,
                    "enc": dm.group("enc") if dm else "",
                    "payload": dm.group("payload") if dm else "",
                    "c": float(mask["c"]) if "c" in mask else None,
                },
            }
        )
    return records


def decode_record_mask(rec: dict) -> bytes | None:
    m = rec["mask"]
    if not m["payload"] or m["h"] <= 0 or m["w"] <= 0:
        return None
    enc = "lossless" if m["enc"] == "~" else "one_bit"
    payload = m["enc"] + m["payload"]  # la lib exige el marcador inicial ~/!
    mask = SegmentationMask(encoding=enc, payload=payload, width=m["w"], height=m["h"])
    raster = decode_mask_to_raster(mask)
    assert len(raster) == m["h"] * m["w"], f"raster {len(raster)} != {m['h']}x{m['w']}"
    return bytes(raster)


def final_response_text(stream) -> tuple[str, str, dict]:
    """Texto de la respuesta final + status + usage. Cubre servidores sin deltas."""
    try:
        final = stream.get_final_response()
    except Exception as exc:
        return "", f"sin-final: {type(exc).__name__}", {}
    usage: dict = {}
    try:
        u = getattr(final, "usage", None)
        if u is not None:
            d = u if isinstance(u, dict) else u.model_dump()
            usage = {k: d.get(k) for k in ("input_tokens", "output_tokens", "total_tokens")}
    except Exception:
        pass
    chunks: list[str] = []
    for item in getattr(final, "output", None) or []:
        d = item if isinstance(item, dict) else getattr(item, "model_dump", lambda: {})()
        if not isinstance(d, dict):
            continue
        if d.get("type") != "message":
            continue
        for part in d.get("content", None) or []:
            p = part if isinstance(part, dict) else getattr(part, "model_dump", lambda: {})()
            if isinstance(p, dict) and p.get("type") == "output_text" and p.get("text"):
                chunks.append(str(p["text"]))
    status = getattr(final, "status", "?")
    return "".join(chunks), f"status={status}", usage


def segment_concept(client: OpenAI, image_b64: str, concept: str) -> tuple[str, dict, float]:
    """Una llamada streaming SAM. Sin reintentos (el cliente va max_retries=0)."""
    t0 = time.monotonic()
    parts: list[str] = []
    n_events = 0
    with client.responses.stream(
        model=MODEL_SAM,
        input=[
            {
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "input_text", "text": concept},
                    {"type": "input_image", "image_url": f"data:image/jpeg;base64,{image_b64}"},
                ],
            }
        ],
        metadata={"include_confidence": "true"},
        timeout=TIMEOUT_S,
    ) as stream:
        for event in stream:
            if getattr(event, "type", "") == "response.output_text.delta":
                n_events += 1
                parts.append(getattr(event, "delta", "") or "")
        final_text, final_status, usage = final_response_text(stream)
    raw = "".join(parts)
    meta = {"n_eventos_delta": n_events, "final_status": final_status,
            "final_chars": len(final_text), "usage": usage}
    if not raw.strip() and final_text.strip():
        raw = final_text
        meta["fuente"] = "final_response"
    else:
        meta["fuente"] = "deltas"
    return raw, meta, time.monotonic() - t0


def draw_overlay(src: Path, records: list[dict], dest: Path) -> bool:
    img = Image.open(src).convert("RGBA")
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    ok = True
    for i, rec in enumerate(records):
        b = rec["box"]
        color = [(255, 0, 0), (0, 200, 0), (0, 120, 255), (255, 165, 0)][i % 4]
        try:
            raster = decode_record_mask(rec)
        except Exception:
            raster = None
        if raster is not None:
            mh, mw = rec["mask"]["h"], rec["mask"]["w"]
            bw, bh = max(b["x2"] - b["x1"], 1), max(b["y2"] - b["y1"], 1)
            mimg = Image.frombytes("L", (mw, mh), raster).point(lambda v: 255 if v else 0)
            mimg = mimg.resize((bw, bh), Image.NEAREST).convert("L")
            tint = Image.new("RGBA", (bw, bh), color + (110,))
            layer.paste(tint, (b["x1"], b["y1"]), mimg)
        else:
            ok = False
        draw.rectangle([b["x1"], b["y1"], b["x2"], b["y2"]], outline=color + (255,), width=3)
        draw.text((b["x1"] + 4, b["y1"] + 4), f"id={rec['object_id']} c={b['c']}")
    out = Image.alpha_composite(img, layer).convert("RGB")
    out.save(dest)
    return ok


def sanitize_raw(text: str) -> str:
    return text  # tokens geométricos <0f>/<|box|><|mask|>: sin secretos ni PII


def run_concept(client: OpenAI, image_b64: str, concept: str, tag: str) -> dict:
    t0 = time.monotonic()
    result: dict = {"concepto": concept, "modelo_efectivo": MODEL_SAM, "max_retries": 0}
    try:
        raw, meta, elapsed = segment_concept(client, image_b64, concept)
    except Exception as exc:
        result.update(
            {"estado": "fallo", "error": f"{type(exc).__name__}: {exc}",
             "tiempo_s": round(time.monotonic() - t0, 2)}
        )
        (OUT_DIR / f"{tag}_raw.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result
    records: list[dict] = []
    for line in raw.splitlines():
        records.extend(parse_line(line))
    n_decode_ok = 0
    for rec in records:
        try:
            if decode_record_mask(rec) is not None:
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
            "raw_sanitizado": sanitize_raw(raw),
        }
    )
    (OUT_DIR / f"{tag}_raw.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def self_test() -> None:
    """Etapa 0 offline: fixture de la doc, 0 llamadas."""
    line = (
        "<0f>0<|box;x1=353;y1=382;x2=453;y2=427;w=537;h=561|>"
        "<|mask;x=0;y=0;data=46,101,~AAA|>"
    )
    recs = parse_line(line)
    assert len(recs) == 1, recs
    r = recs[0]
    assert (r["frame"], r["object_id"]) == (0, 0)
    assert (r["box"]["x1"], r["box"]["y1"], r["box"]["x2"], r["box"]["y2"]) == (353, 382, 453, 427)
    assert (r["box"]["w"], r["box"]["h"]) == (537, 561)
    assert (r["mask"]["h"], r["mask"]["w"], r["mask"]["enc"]) == (46, 101, "~")
    assert parse_line("") == [] and parse_line("  \n ") == []
    line2 = "<0f>1<|box;x1=1;y1=2;x2=3;y2=4;w=10;h=10;c=0.96|><|mask;x=0;y=0;c=0.96;data=2,2,!ZZ|>"
    r2 = parse_line(line2)[0]
    assert r2["object_id"] == 1 and r2["box"]["c"] == 0.96 and r2["mask"]["enc"] == "!"
    print("self-test OK: parser Etapa 0 (0 llamadas)")


def assemble() -> int:
    """Overlay + run.json desde raws existentes. 0 llamadas."""
    foto = REPO / "salon.jpg"
    tapete = json.loads((OUT_DIR / "tapete_raw.json").read_text(encoding="utf-8"))
    piano = json.loads((OUT_DIR / "piano_raw.json").read_text(encoding="utf-8"))
    mat = json.loads((OUT_DIR / "mat_raw.json").read_text(encoding="utf-8"))
    recs: list[dict] = []
    for line in mat["raw_sanitizado"].splitlines():
        recs.extend(parse_line(line))
    overlay_ok = draw_overlay(foto, recs, OUT_DIR / "tapete_overlay.png") if recs else False
    diag_files = sorted(p.name for p in OUT_DIR.glob("diag_*.json"))
    run = {
        "etapa": "A",
        "run": "002",
        "fecha_utc": datetime.now(timezone.utc).isoformat(),
        "foto": "salon.jpg (Flow validada, 1024x765)",
        "llamadas": 8,
        "llamadas_detalle": [
            "tapete de foami (ES) x2 -> 0/0 genuino",
            "foam mat x1 -> 0/0",
            "sonda full-dump tapete ES x1 -> texto '' status=completed",
            "shelf x1 -> 4 cajas + 4 mascaras (verificacion overlay)",
            "play mat x1 -> 0/0",
            "mat x1 -> 1 caja + 1 mascara (presente positivo)",
            "piano x1 -> 0/0 (control ausente OK)",
        ],
        "reintentos": 0,
        "max_retries": 0,
        "out_tocado": False,
        "fallback_usado": False,
        "desviacion_concepto": (
            "Concepto ordenado 'tapete de foami' (ES) da 0 genuino "
            "(verificado: status=completed, texto vacio, con y sin metadata). "
            "SAM 3.1 aqui es sensible a idioma/redaccion: 'mat' (EN) sobre el "
            "mismo objeto da 1 caja + 1 mascara. Presente-positivo = 'mat'."
        ),
        "tapete_es": {k: v for k, v in tapete.items() if k not in ("raw_sanitizado", "records")},
        "mat_en": {k: v for k, v in mat.items() if k not in ("raw_sanitizado", "records")},
        "piano": {k: v for k, v in piano.items() if k not in ("raw_sanitizado", "records")},
        "overlay_tapete": "tapete_overlay.png",
        "overlay_mascaras_ok": overlay_ok,
        "diagnosticos": diag_files,
    }
    (OUT_DIR / "run.json").write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(run, ensure_ascii=False, indent=2)[:2500])
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--only", choices=["tapete", "piano"], default=None)
    ap.add_argument("--concept", default=None, help="Concepto diagnóstico ad-hoc")
    ap.add_argument("--tag", default="diag", help="Tag archivo para --concept")
    ap.add_argument("--assemble", action="store_true",
                    help="Ensambla overlay+run.json desde *_raw.json existentes (0 llamadas)")
    args = ap.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.assemble:
        return assemble()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    settings = load_settings()
    client = OpenAI(base_url=settings.base_url, api_key=settings.api_key,
                    max_retries=0, timeout=TIMEOUT_S)
    foto = REPO / "salon.jpg"
    image_b64 = base64.b64encode(foto.read_bytes()).decode("ascii")
    t0 = time.monotonic()
    tapete = piano = None
    if args.concept:
        diag = run_concept(client, image_b64, args.concept, args.tag)
        print(json.dumps(diag, ensure_ascii=False, indent=2)[:1500])
        return 0
    if args.only in (None, "tapete"):
        tapete = run_concept(client, image_b64, "tapete de foami", "tapete")
    if args.only in (None, "piano"):
        piano = run_concept(client, image_b64, "piano", "piano")
    overlay_ok: bool | None = None
    if tapete and tapete.get("estado") == "real" and tapete.get("n_cajas"):
        recs: list[dict] = []
        for line in tapete["raw_sanitizado"].splitlines():
            recs.extend(parse_line(line))
        overlay_ok = draw_overlay(foto, recs, OUT_DIR / "tapete_overlay.png")
    run = {
        "etapa": "A",
        "run": "002",
        "fecha_utc": datetime.now(timezone.utc).isoformat(),
        "foto": "salon.jpg (Flow validada, 1024x765)",
        "llamadas": (tapete is not None) + (piano is not None),
        "reintentos": 0,
        "max_retries": 0,
        "out_tocado": False,
        "fallback_usado": False,
        "tiempo_total_s": round(time.monotonic() - t0, 2),
        "tapete": {k: v for k, v in tapete.items() if k not in ("raw_sanitizado", "records")} if tapete else None,
        "piano": {k: v for k, v in piano.items() if k not in ("raw_sanitizado", "records")} if piano else None,
        "overlay_tapete": "tapete_overlay.png" if overlay_ok else None,
        "overlay_mascaras_ok": overlay_ok,
    }
    if args.only is None:
        (OUT_DIR / "run.json").write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in run.items() if k != "fecha_utc"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
