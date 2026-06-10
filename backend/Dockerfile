# syntax=docker/dockerfile:1
# -----------------------------------------------------------------------------
# Backend image — FastAPI API + Celery worker share this image.
# -----------------------------------------------------------------------------
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# System deps: build tools for asyncpg/psycopg; curl for healthchecks.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first for better layer caching.
COPY requirements.txt requirements-dev.txt ./
RUN pip install --upgrade pip && pip install -r requirements-dev.txt

# App source (bind-mounted in dev via docker-compose for hot reload).
COPY . .

# Create the local upload directory (dev object storage).
RUN mkdir -p /app/data/uploads

EXPOSE 8000

# Default command is overridden by docker-compose (uvicorn vs celery).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
