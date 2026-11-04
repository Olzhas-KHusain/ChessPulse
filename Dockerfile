# Multi-stage build: one image serves both the static frontend and the FastAPI
# backend on port 8000. Node builds the UI, a slim Python image runs the API
# and the mounted SPA.

# --- Stage 1: build the frontend (static assets) ------------------------------
FROM node:22-bookworm-slim AS frontend

WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# Vite copies .env from the repo root; production must build without dev URLs.
RUN npm run build

# --- Stage 2: backend runtime --------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Stockfish from Debian is the engine binary for the analysis worker.
RUN apt-get update \
    && apt-get install -y --no-install-recommends stockfish \
    && rm -rf /var/lib/apt/lists/*
ENV STOCKFISH_PATH=/usr/games/stockfish

WORKDIR /app
COPY backend/pyproject.toml ./
COPY backend/app ./app
RUN pip install .
COPY backend/migrations ./migrations
COPY backend/alembic.ini ./
COPY backend/tests ./tests
COPY --from=frontend /build/dist /app/static

# Serve the built SPA + API from one process; migrations run in the entrypoint.
# Set RUN_EMBEDDED_WORKER=1 on hosts that cannot run a second process (for
# example a single Render free web service); Compose keeps its own worker.
ENV STATIC_DIR=/app/static
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os, urllib.request; port = os.environ.get('PORT', '8000'); urllib.request.urlopen('http://127.0.0.1:' + port + '/health', timeout=4)" || exit 1

# PORT defaults to 8000 for Compose; PaaS hosts (Render) inject their own port.
CMD ["sh", "-c", "alembic upgrade head && if [ \"$RUN_EMBEDDED_WORKER\" = \"1\" ]; then python -m app.worker & fi; exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port \"${PORT:-8000}\""]
