-- =============================================================================
-- PostgreSQL bootstrap — runs ONCE on first container init (empty data dir).
-- -----------------------------------------------------------------------------
-- Scope: enable required extensions ONLY.
-- Tables, indexes, and the vector column are owned by Alembic migrations,
-- NOT by this script. In particular the embedding dimension is intentionally
-- NOT defined here — it is deferred to Phase 2 (see docs/02_DATABASE_DESIGN.md §6.1).
-- =============================================================================

-- UUID generation (gen_random_uuid)
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- pgvector — vector similarity search.
-- NOTE: this only installs the extension. No `vector(N)` column is created here;
-- the dimension is finalized in Phase 2 and applied via an Alembic migration.
CREATE EXTENSION IF NOT EXISTS vector;

-- Trigram search (useful later for hybrid keyword/metadata matching).
CREATE EXTENSION IF NOT EXISTS pg_trgm;
