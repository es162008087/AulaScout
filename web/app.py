"""Web demo AulaScout: /api/generar corre el pipeline REAL (Voice + SAM + Spark + Image).

Despliegue: Cloud Run publico (decision de Alvaro 3-nov: sin auth, solo topes).
Protecciones (el endpoint gasta tokens de IA):
- Tope: 5 corridas/hora por IP y 20/dia global, contador en archivo
  (en Cloud Run vive en el disco efimero: se reinicia con el contenedor;
  desplegar con --max-instances 1 para que el tope global sea unico).
- Una corrida a la vez. MODEL_API_KEY solo vive en el servidor (secreto/.env).
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
RUNS_WEB = BASE / "runs" / "web"
RUNS_WEB.mkdir(parents=True, exist_ok=True)
CONTADOR = BASE / "runs" / "_contador_web.json"  # fuera de runs/web (no se sirve)

MAX_POR_HORA_IP = 5
MAX_POR_DIA_GLOBAL = 20
MSG_LIMITE = "Límite de demo alcanzado"
ARCHIVOS_RUN = ["materiales.json", "transcripcion.txt", "planeacion.md",
                "ficha.png", "run.json", "etiquetas.json"]

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024
_en_curso = threading.Lock()


def ip_cliente() -> str:
    """IP del cliente. Detras de un proxy de confianza (Cloud Run: env K_SERVICE; o
    loopback) el proxy agrega la IP real al FINAL de X-Forwarded-For; lo anterior lo
    puede falsear el cliente, por eso se toma solo la ultima entrada."""
    remota = request.remote_addr or "?"
    if os.environ.get("K_SERVICE") or remota in ("127.0.0.1", "::1"):
        xff = request.headers.get("X-Forwarded-For", "")
        if xff:
            return xff.split(",")[-1].strip()
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


@app.route("/api/generar", methods=["POST"])
def generar():
    foto = request.files.get("foto")
    audio = request.files.get("audio")
    if not foto or not audio:
        return jsonify(error="Faltan foto y/o audio"), 400
    if not _en_curso.acquire(blocking=False):
        return jsonify(error="Hay otra corrida en curso, intenta en 2 minutos"), 429
    try:
        motivo = reservar_corrida(ip_cliente())
        if motivo:
            return jsonify(error=motivo), 429
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:6]
        dest = RUNS_WEB / ts
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
        try:
            run = pipeline.run_pipeline(foto_path, audio_path, dest)
        except Exception as exc:  # no filtrar detalles internos al cliente
            app.logger.exception("pipeline fallo")
            return jsonify(error="Falló el pipeline", tipo=type(exc).__name__), 500
        ok = bool(run.get("ok"))
        resp = {
            "ok": ok,
            "id": ts,
            "latencia_s": run.get("latencia_total_s_n1"),
            "llamadas": run.get("llamadas_nuevas"),
            "estados": {
                "voice": run["voice"].get("estado"),
                "sam": {k: v.get("estado") for k, v in run["sam"].items()},
                "spark": run["spark"].get("estado"),
                "image": run["image"].get("estado"),
            },
            "transcripcion": _leer(dest / "transcripcion.txt", ""),
            "planeacion": _leer(dest / "planeacion.md", ""),
            "materiales": json.loads(_leer(dest / "materiales.json", "[]")),
            "archivos": {n: f"/runs/{ts}/{n}" for n in ARCHIVOS_RUN if (dest / n).exists()},
        }
        return jsonify(resp), (200 if ok else 502)
    finally:
        _en_curso.release()


@app.route("/runs/<path:p>")
def serve_run(p):
    return send_from_directory(RUNS_WEB, p)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)), threaded=True)
