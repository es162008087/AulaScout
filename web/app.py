
from flask import Flask, render_template, request, jsonify, send_from_directory
import json, uuid, shutil
from datetime import datetime
from pathlib import Path
BASE = Path.home() / "dev/meta"
OUT = BASE / "out"
RUNS_WEB = BASE / "runs/web"
RUNS_WEB.mkdir(parents=True, exist_ok=True)
app = Flask(__name__)
@app.route("/")
def index():
    return render_template("index.html")
@app.route("/api/generar", methods=["POST"])
def generar():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:6]
    dest = RUNS_WEB / ts
    dest.mkdir(parents=True, exist_ok=True)
    foto = request.files.get("foto")
    audio = request.files.get("audio")
    if foto:
        foto.save(dest / "salon.jpg")
    if audio:
        audio.save(dest / "nota.m4a")
    trans_path = OUT / "transcripcion.txt"
    if trans_path.exists():
        trans = trans_path.read_text()
    else:
        trans = "Tengo tapete de foami, bloques de madera de colores, canasta con pelotas sensoriales y libros de tela."
    (dest / "transcripcion.txt").write_text(trans)
    for f in ["ficha.png","planeacion.md","materiales.json","etiquetas.json"]:
        src1 = OUT / f
        src2 = BASE / f"runs/002/VIDEO/{f}"
        if src1.exists():
            shutil.copy(src1, dest / f)
        elif src2.exists():
            shutil.copy(src2, dest / f)
    mp4 = OUT / "demo_aulascout.mp4"
    if mp4.exists():
        shutil.copy(mp4, dest / "demo_aulascout.mp4")
    run = {"estado":"demo-cache","timestamp":ts,"transcripcion":trans,"nota":"Cache cierre final 42d52e8 - pipeline real 11 llamadas ~$0.35","latencia_estimada":"55.69s","costo_estimado":"$0.35","archivos":[p.name for p in dest.iterdir()]}
    (dest / "run.json").write_text(json.dumps(run, indent=2, ensure_ascii=False))
    return jsonify(run)
@app.route("/runs/<path:p>")
def serve_run(p):
    return send_from_directory(RUNS_WEB, p)
@app.route("/out/<path:p>")
def serve_out(p):
    return send_from_directory(OUT, p)
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
