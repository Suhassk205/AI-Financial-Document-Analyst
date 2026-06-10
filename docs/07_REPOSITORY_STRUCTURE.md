# 07 — Repository Structure & Conventions

> **Document status:** Phase 0.5 (Foundation)
> **Last updated:** 2026-06-10
> **Audience:** All engineers
> **Scope:** Folder layout, purpose of each directory, dependency rules, coding standards. No business logic.

---

## Table of Contents

1. [Monorepo Layout](#1-monorepo-layout)
2. [Backend Structure](#2-backend-structure)
3. [Frontend Structure](#3-frontend-structure)
4. [Infrastructure Structure](#4-infrastructure-structure)
5. [Architectural Conventions](#5-architectural-conventions)
6. [Dependency Rules](#6-dependency-rules)
7. [Coding Standards](#7-coding-standards)

---

## 1. Monorepo Layout

A single repository holds backend, frontend, infrastructure, and docs. This keeps
architecture docs, API contracts, and the code that implements them versioned
together, and makes one `docker compose up` spin up the whole system.

```
ai-financial-document-analyst/
├── backend/            FastAPI app · Celery worker · Alembic migrations · tests
├── frontend/           React + TypeScript SPA (Vite, Tailwind, ShadCN)
├── infrastructure/     Postgres init, Redis config, ops scripts
├── docs/               Architecture & engineering documentation (source of truth)
├── docker-compose.yml  Local orchestration of all services
├── .env.example        Canonical environment template
├── .gitignore
└── README.md
```

---

## 2. Backend Structure

```
backend/
├── app/
│   ├── main.py              FastAPI entrypoint: app, middleware, lifespan, router mount
│   ├── api/
│   │   └── v1/
│   │       ├── router.py        Aggregate v1 router (includes sub-routers)
│   │       └── endpoints/       One module per resource (health today; business later)
│   ├── core/
│   │   ├── config.py            Typed, env-based settings (single source of config)
│   │   ├── logging.py           Centralized structured logging (structlog)
│   │   └── security.py          Auth/RBAC scaffold (implemented Phase 11)
│   ├── db/
│   │   ├── base.py              Declarative Base + naming convention
│   │   └── session.py           Async engine, session factory, get_db() dependency
│   ├── models/                  SQLAlchemy ORM models (base.py mixins now; tables per phase)
│   ├── schemas/                 Pydantic request/response models (per phase)
│   ├── services/                Business logic / use-cases (orchestrate repos + agents)
│   ├── repositories/            Data-access layer (DB queries; isolates SQL from services)
│   ├── tasks/
│   │   └── celery_app.py        Celery app, queues, routing, retry policy (no tasks yet)
│   ├── agents/                  LangGraph agents (supervisor + specialists) — Phase 7
│   ├── retrieval/               RAG: rewrite, HyDE, hybrid search, BGE re-rank — Phase 2/6
│   ├── ingestion/               Parse → section → chunk → embed pipeline — Phase 1/2
│   ├── memo/                    Investment memo synthesis — Phase 9
│   ├── benchmark/               Competitor benchmarking — Phase 8
│   └── utils/                   Cross-cutting helpers (pure, dependency-light)
├── migrations/              Alembic (env.py, script template, versions/)
├── tests/
│   ├── unit/                Fast, isolated (no external services)
│   ├── integration/         Require Postgres/Redis
│   └── evaluation/          Retrieval/extraction accuracy evals (future)
├── alembic.ini
├── pyproject.toml           Tooling config (ruff/black/mypy/pytest)
├── requirements.txt         Runtime deps
├── requirements-dev.txt     Dev/test deps
└── Dockerfile
```

### Folder responsibilities (the "why")

| Folder | Responsibility | Must NOT |
|---|---|---|
| `api/v1/endpoints` | HTTP shape: parse/validate request, call a service, shape response | Contain business logic or SQL |
| `core` | App-wide concerns: config, logging, security primitives | Import from feature modules |
| `db` | Engine/session lifecycle + declarative base | Hold business queries |
| `models` | ORM table definitions + shared mixins | Contain business behavior |
| `schemas` | Pydantic DTOs (validation, serialization) | Touch the DB |
| `services` | Use-case orchestration; the only place that combines repos + agents + retrieval | Talk HTTP or hold raw SQL |
| `repositories` | All data access; one repo per aggregate | Contain HTTP or LLM calls |
| `tasks` | Celery app + async tasks | Be called synchronously from request handlers |
| `agents` | LangGraph supervisor + specialists | Be imported by `core`/`db` |
| `retrieval` | RAG pipeline components | Persist domain entities directly |
| `ingestion` | Document → chunks/sections pipeline | Answer user queries |
| `memo` / `benchmark` | Domain-specific synthesis/comparison | Duplicate generic retrieval |
| `utils` | Small, pure helpers | Depend on `services`/`api` |

> **Domain-driven, layered design.** The dependency direction is one-way:
> `api → services → (repositories | agents | retrieval | ingestion) → db/models`.
> `core` and `utils` are leaf layers everyone may import; they import nothing
> upward. This keeps the app dependency-injection friendly and testable.

---

## 3. Frontend Structure

```
frontend/
├── index.html
├── package.json
├── vite.config.ts            Vite + path alias (@ → src)
├── tsconfig*.json
├── tailwind.config.js / postcss.config.js
├── Dockerfile
└── src/
    ├── main.tsx              React entry
    ├── App.tsx               Root shell (proves backend connectivity today)
    ├── index.css             Tailwind layers
    ├── components/           Reusable presentational components (incl. ShadCN ui/)
    ├── features/             Feature modules (upload, chat, metrics, ...) — per phase
    ├── pages/                Route-level pages composed from features
    ├── layouts/              App shells / page frames (sidebar, header, ...)
    ├── hooks/                Reusable React hooks
    ├── services/             API clients (api.ts foundation; feature clients later)
    ├── lib/                  Framework-agnostic helpers (formatting, constants)
    └── types/               Shared TypeScript types / API DTO mirrors
```

### Folder responsibilities

| Folder | Responsibility |
|---|---|
| `components` | Dumb, reusable UI (buttons, cards, tables). ShadCN primitives live in `components/ui`. |
| `features` | Self-contained slices (their own components + hooks + service calls) for one capability |
| `pages` | Route targets; compose features + layouts; minimal logic |
| `layouts` | Persistent structure shared across pages |
| `hooks` | Cross-feature reusable hooks (e.g. `useApi`) |
| `services` | All network I/O; the only layer that calls the backend |
| `lib` | Pure helpers and constants (no React, no network) |
| `types` | Shared types, including mirrors of backend response schemas |

> Same one-way rule: `pages → features → components`; `services`/`lib`/`types`
> are leaf layers. Components never call the network directly — they go through
> `services`.

---

## 4. Infrastructure Structure

```
infrastructure/
├── postgres/
│   └── init.sql      Enables pgvector/pgcrypto/pg_trgm ONLY (no tables — Alembic owns those)
├── redis/
│   └── README.md     Logical-DB allocation (broker/result/cache)
└── scripts/          Operational helper scripts (future: backup, seed, migrate wrappers)
```

See `docs/08_INFRASTRUCTURE_SETUP.md` for how these are used.

---

## 5. Architectural Conventions

1. **Single source of config.** Everything reads `app.core.config.settings`; no
   direct `os.environ` access scattered through the code.
2. **No secrets in code or VCS.** Only `.env.example` is committed.
3. **Async-first backend.** Async SQLAlchemy + async endpoints; heavy work is
   offloaded to Celery, never run inside a request (ADR-008).
4. **Migrations own the schema.** No table is created by `init.sql` or by ORM
   `create_all()` in app code — Alembic is the only path to schema change.
5. **Deterministic numbers.** Per ADR-007, quantitative results come from
   structured tables via SQL, never from LLM text.
6. **Citations everywhere.** Any future endpoint returning a financial claim
   must include citation data.
7. **Stable interfaces before implementation.** Scaffolds (e.g. `security.py`)
   define shapes now so dependents don't churn later.

---

## 6. Dependency Rules

**Backend layering (enforced by review; lint rules later):**

```
api  →  services  →  repositories  →  models/db
                  →  agents / retrieval / ingestion / memo / benchmark
core, utils  =  leaf layers (imported by anyone, import nothing upward)
```

- `api` never imports `repositories` or `models` directly — it goes through `services`.
- `repositories` are the only place with raw queries.
- `agents`/`retrieval`/`ingestion` may use `repositories` and `core`, never `api`.
- Circular imports are a hard error; if two modules need each other, a dependency
  is mis-placed.

**Frontend layering:** `pages → features → components`; `services`/`lib`/`types`
are leaves. UI never fetches directly.

---

## 7. Coding Standards

**Python (backend)**
- Formatter: **black** (line length 100). Linter: **ruff** (E/F/I/B/UP/N). Types: **mypy --strict**.
- `from __future__ import annotations` at top of modules; full type hints.
- Module/function docstrings explain *why*, not just *what*.
- Naming: `snake_case` functions/vars, `PascalCase` classes, `UPPER_SNAKE` constants.
- No print(); use `app.core.logging.get_logger`.

**TypeScript (frontend)**
- `strict` TypeScript; no `any` without justification.
- Components `PascalCase`; hooks `useX`; files match default export name.
- Path alias `@/` for `src/`.
- All network calls go through `src/services`.

**General**
- Conventional Commits (see `docs/09_DEVELOPMENT_GUIDELINES.md`).
- Tests accompany behavior changes; docs updated in the same PR.
- Keep PRs scoped to one phase deliverable where possible.
