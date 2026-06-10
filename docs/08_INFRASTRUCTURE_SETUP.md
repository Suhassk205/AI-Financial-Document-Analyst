# 08 — Infrastructure Setup

> **Document status:** Phase 0.5 (Foundation)
> **Last updated:** 2026-06-10
> **Audience:** Engineers running the stack locally; ops
> **Scope:** Docker, PostgreSQL+pgvector, Redis, Celery, Alembic, local dev workflow.

---

## Table of Contents

1. [Docker Architecture](#1-docker-architecture)
2. [PostgreSQL + pgvector](#2-postgresql--pgvector)
3. [Redis](#3-redis)
4. [Celery](#4-celery)
5. [Alembic](#5-alembic)
6. [Local Development Workflow](#6-local-development-workflow)
7. [Troubleshooting](#7-troubleshooting)

---

## 1. Docker Architecture

`docker-compose.yml` defines five services on one bridge network (`fda_net`).
Services address each other by name (`postgres`, `redis`), which is why the
connection URLs in `.env` use those hostnames.

```mermaid
flowchart TB
    subgraph fda_net["Docker network: fda_net"]
        FE["frontend<br/>Vite :5173"]
        BE["backend<br/>FastAPI :8000"]
        WK["worker<br/>Celery"]
        PG[("postgres<br/>pgvector :5432")]
        RD[("redis :6379")]
    end
    FE -->|VITE_API_BASE_URL| BE
    BE --> PG
    BE --> RD
    WK --> PG
    WK --> RD
    BE -. enqueues .-> RD
    RD -. delivers .-> WK
```

### Services, ports, volumes

| Service | Image / build | Host port → container | Volumes | Depends on (healthy) |
|---|---|---|---|---|
| `postgres` | `pgvector/pgvector:pg16` | 5432 → 5432 | `postgres_data`, `init.sql` (ro) | — |
| `redis` | `redis:7-alpine` | 6379 → 6379 | `redis_data` | — |
| `backend` | `./backend/Dockerfile` | 8000 → 8000 | `./backend` (bind), `uploads_data` | postgres, redis |
| `worker` | `./backend/Dockerfile` | — | `./backend` (bind), `uploads_data` | postgres, redis, backend |
| `frontend` | `./frontend/Dockerfile` | 5173 → 5173 | `./frontend` (bind), anon `node_modules` | backend |

- **Named volumes** (`postgres_data`, `redis_data`, `uploads_data`) persist data
  across restarts. They are listed in `.gitignore` and never committed.
- **Bind mounts** (`./backend`, `./frontend`) give hot reload in dev.
- **Healthchecks** on postgres/redis gate dependent services so the backend
  doesn't start before its dependencies accept connections.

### Networking
A single user-defined bridge network provides DNS-by-service-name. Only the ports
listed above are published to the host; inter-service traffic stays on `fda_net`.

---

## 2. PostgreSQL + pgvector

- **Image:** `pgvector/pgvector:pg16` ships PostgreSQL 16 with the `vector` extension available.
- **Init:** `infrastructure/postgres/init.sql` runs once on first boot and enables
  extensions **only** — `pgcrypto` (UUIDs), `vector` (pgvector), `pg_trgm`.
- **No tables in init.** Schema is owned exclusively by Alembic (§5). This keeps
  one migration path and a clean history.
- **Embedding dimension is NOT set here.** Per ADR / `02_DATABASE_DESIGN.md §6.1`,
  the `vector(EMBEDDING_DIM)` column and its HNSW index are introduced by an
  Alembic migration in **Phase 2** once the embedding model is chosen. Nothing in
  Phase 0.5 locks a dimension.

**Connecting:**
- App (async): `DATABASE_URL=postgresql+asyncpg://analyst:analyst@postgres:5432/financial_analyst`
- Alembic (sync): `DATABASE_URL_SYNC=postgresql+psycopg://...`

**Verify pgvector:**
```bash
docker compose exec postgres psql -U analyst -d financial_analyst -c "\dx"
# expect: vector, pgcrypto, pg_trgm
```

---

## 3. Redis

One Redis instance, three logical databases (see `infrastructure/redis/README.md`):

| DB | Env var | Role |
|----|---------|------|
| 0 | `REDIS_URL` | future cache (retrieval cache, rate limiting) |
| 1 | `CELERY_BROKER_URL` | Celery broker (task queue) |
| 2 | `CELERY_RESULT_BACKEND` | Celery results / task state |

Runs with AOF persistence (`--appendonly yes`) so queued tasks survive restarts.

**Verify:**
```bash
docker compose exec redis redis-cli ping     # PONG
```

---

## 4. Celery

Defined in `backend/app/tasks/celery_app.py` (ADR-008: Redis + Celery). **No tasks
are registered yet** — this is the worker foundation.

### Queues
| Queue | Purpose |
|---|---|
| `default` | misc/control tasks |
| `ingestion` | parse → chunk → embed (I/O + embedding-API heavy) — Phase 1/2 |
| `extraction` | metric / risk / tone extraction (LLM heavy) — Phase 3/4/5 |

Segregating queues lets heavy ingestion scale on its own worker pool without
starving lighter extraction/control tasks.

### Task routing
Routing maps task-name globs to queues:
```python
task_routes = {
    "app.tasks.ingestion.*":  {"queue": "ingestion"},
    "app.tasks.extraction.*": {"queue": "extraction"},
}
```
Concrete task names are added with their implementations in later phases.

### Retry strategy
Global defaults (per-task overrides allowed):
- `task_acks_late=True` + `worker_prefetch_multiplier=1` → a crashed worker's task
  is re-queued, and long tasks are dispatched fairly.
- `task_default_retry_delay=10s`, `task_max_retries=3` → tasks that opt into
  autoretry back off and cap retries (exponential backoff configured per task).
- `result_expires=24h` → results don't accumulate unbounded in Redis.

### Running the worker
```bash
# via compose (already wired):
docker compose up worker
# or directly:
celery -A app.tasks.celery_app.celery_app worker --loglevel=INFO -Q default,ingestion,extraction
```
Optional monitoring (Flower) is added in Phase 11.

---

## 5. Alembic

Alembic owns all schema evolution. Config: `backend/alembic.ini`; environment:
`backend/migrations/env.py` (targets `Base.metadata`, pulls the **sync** DB URL
from settings — no hardcoded credentials).

### Strategy
- **Versioning:** date-prefixed, slugged revision files for a readable history
  (`YYYYMMDD_HHMM_<rev>_<slug>.py`).
- **Autogenerate** with `compare_type` and `compare_server_default` enabled to
  catch column/default drift.
- **Reviewed migrations:** every autogenerated migration is read and edited before
  commit (autogenerate is a starting point, not gospel — especially for pgvector
  columns and indexes, which it can't fully infer).
- **Rollback:** every migration implements a real `downgrade()`.

### Common commands
```bash
# create the first (empty) baseline once models exist / to seed history:
docker compose exec backend alembic revision -m "baseline"

# autogenerate after adding/altering models:
docker compose exec backend alembic revision --autogenerate -m "add companies table"

# apply / roll back:
docker compose exec backend alembic upgrade head
docker compose exec backend alembic downgrade -1

# inspect:
docker compose exec backend alembic current
docker compose exec backend alembic history
```

### Best practices
- One logical change per migration; descriptive message.
- Never edit an applied migration — write a new one.
- The embedding `vector(EMBEDDING_DIM)` column + HNSW index land in a dedicated
  Phase 2 migration, after the dimension is decided.
- Index builds on large tables use `CREATE INDEX CONCURRENTLY` where possible
  (handled in the migration body).

---

## 6. Local Development Workflow

**First run:**
```bash
cp .env.example .env                 # fill GEMINI_API_KEY / OPENROUTER_API_KEY if testing those
cp frontend/.env.example frontend/.env
docker compose up --build
```

**Verify the stack:**
```bash
curl http://localhost:8000/api/v1/health     # {"status":"ok"}
curl http://localhost:8000/api/v1/ready       # checks DB + Redis
open http://localhost:8000/docs               # OpenAPI UI
open http://localhost:5173                     # frontend shows backend health
```

**Day-to-day:**
```bash
docker compose up                 # start everything (hot reload on)
docker compose logs -f backend    # tail backend logs
docker compose exec backend pytest          # run tests
docker compose exec backend ruff check .    # lint
docker compose down               # stop (keeps volumes)
docker compose down -v            # stop + wipe data volumes (fresh DB/Redis)
```

**Running backend without Docker (optional):**
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
# point DATABASE_URL/REDIS_URL at localhost instead of service names
uvicorn app.main:app --reload
```

---

## 7. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Backend exits on boot | Postgres/Redis not ready | compose healthchecks gate this; check `docker compose logs postgres` |
| `/ready` returns 503 | DB or Redis unreachable | inspect `checks` in the JSON body; verify URLs in `.env` |
| `vector` extension missing | init ran before image had it / wrong image | confirm `pgvector/pgvector:pg16`; `down -v` then `up` |
| Alembic can't connect | using async URL | Alembic uses `DATABASE_URL_SYNC` (psycopg), not asyncpg |
| Frontend can't reach API | wrong base URL | set `VITE_API_BASE_URL` (host uses `localhost:8000`) |
| Stale deps after requirements change | image cached | `docker compose build --no-cache backend` |
