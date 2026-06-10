# AI Financial Document Analyst

A production-grade **RAG + multi-agent** platform that analyzes financial
disclosures (10-K, 10-Q, earnings call transcripts) and produces grounded,
citation-backed analysis: metric extraction, YoY/QoQ comparison, risk extraction
and evolution tracking, management tone analysis, competitor benchmarking,
investment memo generation, and conversational financial Q&A.

> **Status:** Phase 1A complete — document ingestion foundation (upload → store →
> queue → PDF extraction → page persistence). See `docs/06_IMPLEMENTATION_ROADMAP.md`.

## Tech stack

| Layer | Choice |
|---|---|
| Backend | FastAPI (async) |
| Frontend | React + TypeScript + Tailwind + ShadCN |
| Database | PostgreSQL + pgvector |
| Async | Redis + Celery |
| Migrations | Alembic |
| PDF extraction | PyMuPDF |
| Agents | LangGraph |
| Primary LLM / embeddings | Gemini 2.5 Pro / Gemini Embeddings |
| Fallback LLM | GPT-4o via OpenRouter |
| Retrieval | Hybrid (metadata filter + vector + rewrite + HyDE + BGE re-rank) |

## Repository layout

```
.
├── backend/          FastAPI app, Celery worker, Alembic migrations, tests
├── frontend/         React + TypeScript SPA
├── infrastructure/   Postgres init, Redis config, scripts
└── docs/             Architecture & engineering documentation (source of truth)
```

## Quick start (local)

```bash
cp .env.example .env          # fill in API keys
docker compose up --build     # postgres, redis, backend, worker, frontend
docker compose exec backend alembic upgrade head   # apply schema
```

Then visit:
- API health: http://localhost:8000/api/v1/health
- API docs (OpenAPI): http://localhost:8000/docs
- Frontend: http://localhost:5173

## Tests

```bash
cd backend
pip install -r requirements-dev.txt
pytest -m unit          # fast, no external services
pytest -m integration   # requires Postgres (via docker compose)
```

## Documentation

| Doc | Topic |
|---|---|
| `docs/01_ARCHITECTURE.md` | System architecture |
| `docs/02_DATABASE_DESIGN.md` | Schema, pgvector, indexes |
| `docs/03_AGENT_DESIGN.md` | LangGraph multi-agent design |
| `docs/04_API_DESIGN.md` | API contracts |
| `docs/05_RETRIEVAL_DESIGN.md` | RAG / hybrid retrieval |
| `docs/06_IMPLEMENTATION_ROADMAP.md` | Roadmap, ADRs, decision log (living) |
| `docs/07_REPOSITORY_STRUCTURE.md` | Folder structure & conventions |
| `docs/08_INFRASTRUCTURE_SETUP.md` | Docker / Postgres / Redis / Celery / Alembic |
| `docs/09_DEVELOPMENT_GUIDELINES.md` | Naming, branching, commits, testing |
| `docs/10_PHASE_1A_IMPLEMENTATION.md` | Phase 1A — document ingestion foundation |
