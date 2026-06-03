# NovelForge 2.0 — Production-style multi-stage build
#
# Stage 1: install backend deps
# Stage 2: copy code + run uvicorn
#
# Why not a single stage? Slimmer runtime image (no compilers) and faster
# rebuilds when only source changes. Pinned to python 3.11-slim for size.
FROM python:3.11-slim AS backend

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app/backend

# Install deps first for layer cache
COPY backend/pyproject.toml ./pyproject.toml
RUN pip install --upgrade pip && pip install -e .

# Copy source
COPY backend/app ./app
COPY backend/pyproject.toml ./pyproject.toml

# Persistent data dir lives on a mounted volume
RUN mkdir -p /app/backend/data /app/backend/data/storage /app/backend/data/logs
VOLUME ["/app/backend/data"]

EXPOSE 8000

# Entrypoint: seed (idempotent) + uvicorn. Workers=1 because we have an
# in-process asyncio worker that already consumes agent_tasks; spawning
# multiple uvicorn workers would race on the same SQLite file.
ENTRYPOINT ["/app/backend/docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
