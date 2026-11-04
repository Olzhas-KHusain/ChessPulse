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
COPY backend/migrations ./migrations
COPY backend/alembic.ini ./

# Serve the built SPA + API from one process; migrations run in the entrypoint.
ENV STATIC_DIR=/app/static
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)" || exit 1

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000"]
