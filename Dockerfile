# Cloud Run: contexto = raiz del repo (web/ importa src/ y runs/002/{A,B}).
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements-web.txt .
RUN pip install --no-cache-dir -r requirements-web.txt
COPY src/ src/
COPY runs/002/A/etapa_a.py runs/002/A/etapa_a.py
COPY runs/002/B/etapa_b.py runs/002/B/etapa_b.py
COPY web/ web/
ENV PYTHONUNBUFFERED=1
# MODEL_API_KEY llega como secreto de Cloud Run (nunca en la imagen ni en el repo)
CMD exec gunicorn --chdir web app:app --bind 0.0.0.0:${PORT:-8080} --timeout 300 --workers 1 --threads 8
