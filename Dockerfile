FROM python:3.12-slim

# ffmpeg lo necesita faster-whisper para decodificar audio
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ backend/
COPY static/ static/

RUN useradd -m nova && chown -R nova:nova /app
USER nova

ENV NOVA_HOST=0.0.0.0 \
    NOVA_PORT=8000

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
  CMD curl -sf http://127.0.0.1:8000/api/health || exit 1

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
