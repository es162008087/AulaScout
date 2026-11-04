"""Web demo AulaScout: /api/generar corre el pipeline REAL (Voice + SAM + Spark + Image).

Despliegue: Cloud Run publico (decision de Alvaro 3-nov: sin auth, solo topes).
Protecciones (el endpoint gasta tokens de IA):
- Tope: 5 corridas/hora por IP y 20/dia global, contador en archivo
  (en Cloud Run vive en el disco efimero: se reinicia con el contenedor;
  desplegar con --max-instances 1 para que el tope global sea unico).
- Una corrida a la vez. MODEL_API_KEY solo vive en el servidor (secreto/.env).
- Asincrono: POST /api/generar devuelve job_id al instante y el pipeline corre en un
  hilo; el cliente consulta GET /api/status/<job_id>. (Cloud Run: --no-cpu-throttling,
  si no el hilo queda sin CPU tras responder el POST.)
"""

from __future__ import annotations

import fcntl
import json
import os
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_from_directory
from PIL import Image

import pipeline

BASE = Path(__file__).resolve().parents[1]
RUNS_WEB = Path(os.environ.get("RUNS_WEB", "/tmp/runs/web"))
RUNS_WEB.mkdir(parents=True, exist_ok=True)
CONTADOR = RUNS_WEB.parent / "_contador_web.json"  # fuera de runs/web (no se sirve)

MAX_POR_HORA_IP = 5
MAX_POR_DIA_GLOBAL = 20
MSG_LIMITE = "Límite de demo alcanzado"
ARCHIVOS_RUN = ["materiales.json", "transcripcion.txt", "planeacion.md",
                "ficha.png", "run.json", "etiquetas.json"]

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024
_en_curso = threading.Lock()


def ip_cliente() -> str:
    """IP del cliente: primera entrada de X-Forwarded-For si hay proxy (Cloud Run:
    env K_SERVICE; o loopback); si no, remote_addr. OJO: la primera entrada la puede
    declarar el cliente, asi que el tope por IP es de mejor esfuerzo; el tope global
    (20/dia) no depende de ella."""
    remota = request.remote_addr or "?"
    if os.environ.get("K_SERVICE") or remota in ("127.0.0.1", "::1"):
        xff = request.headers.get("X-Forwarded-For", "")
        if xff:
            return xff.split(",")[0].strip()
    return remota


def reservar_corrida(ip: str) -> str | None:
    """Revisa topes y registra la corrida. Devuelve None si OK, o el motivo."""
    ahora = time.time()
    hoy = datetime.fromtimestamp(ahora).date().isoformat()
    CONTADOR.parent.mkdir(parents=True, exist_ok=True)
    with open(CONTADOR, "a+") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        fh.seek(0)
        try:
            datos = json.loads(fh.read() or "[]")
        except json.JSONDecodeError:
            datos = []
        datos = [d for d in datos if ahora - d["ts"] < 48 * 3600]
        por_ip = sum(1 for d in datos if d["ip"] == ip and ahora - d["ts"] < 3600)
        por_dia = sum(1 for d in datos if d["dia"] == hoy)
        motivo = None
        if por_ip >= MAX_POR_HORA_IP:
            motivo = f"{MSG_LIMITE} ({MAX_POR_HORA_IP} por hora por IP)"
        elif por_dia >= MAX_POR_DIA_GLOBAL:
            motivo = f"{MSG_LIMITE} ({MAX_POR_DIA_GLOBAL} por día)"
        else:
            datos.append({"ts": ahora, "ip": ip, "dia": hoy})
        fh.seek(0)
        fh.truncate()
        fh.write(json.dumps(datos))
    return motivo


@app.route("/")
def index():
    return render_template("index.html")


def _leer(p: Path, default):
    return p.read_text(encoding="utf-8") if p.exists() else default


JOBS: dict[str, dict] = {}
_jobs_lock = threading.Lock()
MAX_JOBS_MEMORIA = 50


def _guardar_status(job_id: str, job: dict) -> None:
    d = RUNS_WEB / job_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "status.json").write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")


def _set_job(jid: str, **cambios) -> None:
    with _jobs_lock:
        job = JOBS.setdefault(jid, {})
        job.update(cambios)
        snap = dict(job)
    try:
        _guardar_status(jid, snap)
    except Exception:
        app.logger.exception("no se pudo escribir status.json")


def _describir_fallo(run: dict) -> str:
    partes = []
    v = run.get("voice", {})
    if v.get("estado") != "real":
        partes.append(f"Voice: {v.get('estado')} {v.get('error', '')}".strip())
    caidos = [k for k, x in run.get("sam", {}).items() if x.get("estado") != "real"]
    if caidos:
        partes.append("SAM falló en: " + ", ".join(caidos))
    sp = run.get("spark", {})
    if sp.get("estado") != "real":
        fin = [i.get("finish_reason") or i.get("error", "?") for i in sp.get("intentos", [])]
        partes.append(f"Spark: {sp.get('error', 'fallo')} ({', '.join(map(str, fin))})")
    im = run.get("image", {})
    if im.get("estado") not in ("real",):
        partes.append(f"Image: {im.get('estado')} {im.get('error', im.get('motivo', ''))}".strip())
    return "; ".join(partes) or "El pipeline terminó con fallos"


def _worker(job_id: str, foto_path: Path, audio_path: Path, dest: Path) -> None:
    try:
        run = pipeline.run_pipeline(foto_path, audio_path, dest)
        ok = bool(run.get("ok"))
        datos = {
            "transcripcion": _leer(dest / "transcripcion.txt", ""),
            "planeacion": _leer(dest / "planeacion.md", ""),
            "materiales": json.loads(_leer(dest / "materiales.json", "[]")),
            "latencia_s": run.get("latencia_total_s_n1"),
            "llamadas": run.get("llamadas_nuevas"),
            "estados": {
                "voice": run["voice"].get("estado"),
                "sam": {k: v.get("estado") for k, v in run["sam"].items()},
                "spark": run["spark"].get("estado"),
                "image": run["image"].get("estado"),
            },
            "ficha_url": f"/runs/{job_id}/ficha.png" if (dest / "ficha.png").exists() else None,
        }
        if ok:
            _set_job(job_id, status="listo", error=None, **datos)
        else:
            _set_job(job_id, status="error", error=_describir_fallo(run), **datos)
    except Exception as exc:
        app.logger.exception("pipeline fallo")
        _set_job(job_id, status="error",
                 error=f"{type(exc).__name__}: {str(exc)[:300]}")
    finally:
        _en_curso.release()


@app.route("/api/generar", methods=["POST"])
def generar():
    foto = request.files.get("foto")
    audio = request.files.get("audio")
    if not foto or not audio:
        return jsonify(error="Faltan foto y/o audio"), 400
    if not _en_curso.acquire(blocking=False):
        return jsonify(error="Hay otra corrida en curso, intenta en 2 minutos"), 429
    lanzado = False
    try:
        motivo = reservar_corrida(ip_cliente())
        if motivo:
            return jsonify(error=motivo), 429
        job_id = datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:8]
        dest = RUNS_WEB / job_id
        dest.mkdir(parents=True, exist_ok=True)
        ext = Path(audio.filename or "").suffix.lower()
        if ext not in (".m4a", ".wav", ".mp3", ".aac", ".mp4", ".ogg"):
            ext = ".m4a"
        audio_path = dest / f"nota{ext}"
        audio.save(audio_path)
        foto_path = dest / "salon.jpg"
        try:
            img = Image.open(foto.stream).convert("RGB")
            img.thumbnail((1280, 1280))
            img.save(foto_path, "JPEG", quality=90)
        except Exception:
            return jsonify(error="La foto no es una imagen válida (usa JPG/PNG)"), 400
        with _jobs_lock:
            while len(JOBS) >= MAX_JOBS_MEMORIA:
                JOBS.pop(next(iter(JOBS)))
        _set_job(job_id, job_id=job_id, status="generando", error=None,
                 inicio=time.time())
        threading.Thread(target=_worker, args=(job_id, foto_path, audio_path, dest),
                         daemon=True).start()
        lanzado = True
        return jsonify(job_id=job_id, status="generando"), 202
    finally:
        if not lanzado:
            _en_curso.release()


@app.route("/api/status/<job_id>")
def status(job_id: str):
    with _jobs_lock:
        job = JOBS.get(job_id)
        job = dict(job) if job else None
    if job is None:
        return jsonify(status="error",
                       error="Trabajo no encontrado (el servidor pudo reiniciarse); vuelve a generar"), 404
    job.setdefault("error", None)
    if job["status"] == "generando":
        job["transcurrido_s"] = round(time.time() - job.get("inicio", time.time()))
        return jsonify(status="generando", transcurrido_s=job["transcurrido_s"])
    return jsonify({k: job.get(k) for k in (
        "status", "error", "transcripcion", "planeacion", "materiales", "ficha_url",
        "latencia_s", "llamadas", "estados")})


@app.route("/runs/<path:p>")
def serve_run(p):
    return send_from_directory(RUNS_WEB, p)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)), threaded=True)
