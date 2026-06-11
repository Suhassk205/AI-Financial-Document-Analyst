"""Integration tests for Phase 2C: hybrid retrieval (metadata filters + vector search).

A deterministic token-hashing embedder is shared by stored chunks and queries, so
filtering + ranking are exercised end-to-end against a live PostgreSQL with no
Gemini key/network. Includes a hybrid-vs-vector-only quality comparison.
"""

from __future__ import annotations

import hashlib
import math
import re
import uuid

import pytest
from app.api.v1.endpoints.search import get_hybrid_service, get_search_service
from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.models.company import Company
from app.models.document_chunk import DocumentChunk
from app.models.enums import EmbeddingStatus, ReportStatus
from app.models.report import Report
from app.retrieval.embeddings.provider import EmbeddingProvider
from app.retrieval.hybrid import HybridRetrievalService
from app.retrieval.search import QueryEmbedder, VectorSearchService
from fastapi import Depends
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

PREFIX = settings.api_v1_prefix
DIM = settings.embedding_dim


class HashingProvider(EmbeddingProvider):
    @property
    def model_name(self) -> str:
        return "hashing-test"

    @property
    def dimension(self) -> int:
        return DIM

    def embed_documents(self, texts):
        return [self._vec(t) for t in texts]

    @staticmethod
    def _vec(text: str) -> list[float]:
        v = [0.0] * DIM
        for tok in re.findall(r"[a-z0-9]+", text.lower()):
            v[int(hashlib.md5(tok.encode()).hexdigest(), 16) % DIM] += 1.0
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]


@pytest.fixture
def hybrid_client(api_client: AsyncClient) -> AsyncClient:
    async def _hybrid(db: AsyncSession = Depends(get_db)) -> HybridRetrievalService:
        return HybridRetrievalService(db, query_embedder=QueryEmbedder(HashingProvider()))

    async def _vector(db: AsyncSession = Depends(get_db)) -> VectorSearchService:
        return VectorSearchService(db, query_embedder=QueryEmbedder(HashingProvider()))

    app.dependency_overrides[get_hybrid_service] = _hybrid
    app.dependency_overrides[get_search_service] = _vector
    yield api_client
    app.dependency_overrides.pop(get_hybrid_service, None)
    app.dependency_overrides.pop(get_search_service, None)


def _company(session: Session, name: str, ticker: str) -> uuid.UUID:
    c = Company(name=name, ticker=ticker)
    session.add(c)
    session.commit()
    return c.id


def _report(session: Session, company_id: uuid.UUID, year: int, rtype: str = "10-K") -> uuid.UUID:
    r = Report(
        company_id=company_id, report_type=rtype, year=year, original_filename="x.pdf",
        storage_path="reports/2026/06/x.pdf", status=ReportStatus.EMBEDDED, total_pages=1,
    )
    session.add(r)
    session.commit()
    return r.id


def _chunk(session: Session, report_id: uuid.UUID, idx: int, text: str, section: str) -> None:
    session.add(
        DocumentChunk(
            report_id=report_id, chunk_index=idx, chunk_text=text,
            token_count=len(text.split()),
            chunk_metadata={"normalized_section_name": section, "section_name": section,
                            "report_id": str(report_id)},
            embedding=HashingProvider._vec(text),
            embedding_status=EmbeddingStatus.COMPLETED.value, embedding_model="hashing-test",
        )
    )
    session.commit()


_RISK = "supply chain disruption risk affecting battery cell production and deliveries"


def _seed_two_companies(session: Session) -> dict:
    tsla = _company(session, "Tesla Inc", "TSLA")
    gm = _company(session, "General Motors", "GM")
    tsla_r = _report(session, tsla, 2024)
    gm_r = _report(session, gm, 2023)
    # Both companies share near-identical risk text → vector-only can't disambiguate.
    _chunk(session, tsla_r, 0, _RISK, "Risk Factors")
    _chunk(session, tsla_r, 1, "revenue grew on strong vehicle deliveries and margins", "MD&A")
    _chunk(session, gm_r, 0, _RISK, "Risk Factors")
    _chunk(session, gm_r, 1, "consolidated balance sheet total assets and liabilities", "Financial Statements")
    return {"tsla": tsla, "gm": gm, "tsla_r": tsla_r, "gm_r": gm_r}


@pytest.mark.integration
async def test_profiles_endpoint(hybrid_client: AsyncClient) -> None:
    resp = await hybrid_client.get(f"{PREFIX}/search/profiles")
    assert resp.status_code == 200
    names = {p["name"] for p in resp.json()["profiles"]}
    assert {"GENERAL", "RISK_ANALYSIS", "FINANCIAL_STATEMENTS"} <= names


@pytest.mark.integration
async def test_no_filters_searches_all(hybrid_client: AsyncClient, sync_session: Session) -> None:
    _seed_two_companies(sync_session)
    resp = await hybrid_client.post(
        f"{PREFIX}/search/hybrid", json={"query": _RISK, "top_k": 10}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["profile"] == "GENERAL"
    assert body["candidate_count"] == 4          # all embedded chunks
    assert body["count"] >= 2


@pytest.mark.integration
async def test_single_section_filter(hybrid_client: AsyncClient, sync_session: Session) -> None:
    _seed_two_companies(sync_session)
    resp = await hybrid_client.post(
        f"{PREFIX}/search/hybrid",
        json={"query": _RISK, "top_k": 10, "filters": {"normalized_section_name": "Risk Factors"}},
    )
    body = resp.json()
    assert body["candidate_count"] == 2          # only the two Risk Factors chunks
    sections = {r["metadata"]["normalized_section_name"] for r in body["results"]}
    assert sections == {"Risk Factors"}


@pytest.mark.integration
async def test_multiple_filters_company_year_section(
    hybrid_client: AsyncClient, sync_session: Session
) -> None:
    ids = _seed_two_companies(sync_session)
    resp = await hybrid_client.post(
        f"{PREFIX}/search/hybrid",
        json={
            "query": _RISK, "top_k": 10,
            "filters": {"company_id": str(ids["tsla"]), "year": 2024,
                        "normalized_section_name": "Risk Factors"},
        },
    )
    body = resp.json()
    assert body["candidate_count"] == 1
    assert all(r["report_id"] == str(ids["tsla_r"]) for r in body["results"])


@pytest.mark.integration
async def test_hybrid_outperforms_vector_only(
    hybrid_client: AsyncClient, sync_session: Session
) -> None:
    """Vector-only can't tell Tesla's risk chunk from GM's (same text); hybrid scopes it."""
    ids = _seed_two_companies(sync_session)

    vec = (await hybrid_client.post(
        f"{PREFIX}/search/vector", json={"query": _RISK, "top_k": 10}
    )).json()
    vec_reports = {r["report_id"] for r in vec["results"]}
    # Vector-only returns BOTH companies' near-identical risk chunks → not scoped.
    assert {str(ids["tsla_r"]), str(ids["gm_r"])} <= vec_reports

    hyb = (await hybrid_client.post(
        f"{PREFIX}/search/hybrid",
        json={"query": _RISK, "top_k": 10,
              "filters": {"company_id": str(ids["tsla"]), "year": 2024}},
    )).json()
    hyb_reports = {r["report_id"] for r in hyb["results"]}
    # Hybrid returns ONLY Tesla content — higher precision for a company-scoped query.
    assert hyb_reports == {str(ids["tsla_r"])}
    assert hyb["candidate_count"] < vec["count"]   # candidate reduction


@pytest.mark.integration
async def test_conflicting_report_and_company(
    hybrid_client: AsyncClient, sync_session: Session
) -> None:
    ids = _seed_two_companies(sync_session)
    resp = await hybrid_client.post(
        f"{PREFIX}/search/hybrid",
        json={"query": _RISK,
              "filters": {"report_id": str(ids["tsla_r"]), "company_id": str(ids["gm"])}},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "CONFLICTING_FILTERS"


@pytest.mark.integration
async def test_invalid_report_id_is_404(hybrid_client: AsyncClient) -> None:
    resp = await hybrid_client.post(
        f"{PREFIX}/search/hybrid",
        json={"query": "risk", "filters": {"report_id": "00000000-0000-0000-0000-000000000000"}},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "FILTER_TARGET_NOT_FOUND"


@pytest.mark.integration
async def test_unknown_section_is_422(hybrid_client: AsyncClient) -> None:
    resp = await hybrid_client.post(
        f"{PREFIX}/search/hybrid",
        json={"query": "risk", "filters": {"normalized_section_name": "Made Up"}},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "UNKNOWN_SECTION"


@pytest.mark.integration
async def test_empty_result_set(hybrid_client: AsyncClient, sync_session: Session) -> None:
    _seed_two_companies(sync_session)
    # A year nobody has → zero candidates, valid 200.
    resp = await hybrid_client.post(
        f"{PREFIX}/search/hybrid", json={"query": _RISK, "filters": {"year": 1999}}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["candidate_count"] == 0
    assert body["count"] == 0


@pytest.mark.integration
async def test_hybrid_debug_returns_diagnostics(
    hybrid_client: AsyncClient, sync_session: Session
) -> None:
    _seed_two_companies(sync_session)
    resp = await hybrid_client.post(
        f"{PREFIX}/search/hybrid/debug",
        json={"query": _RISK, "profile": "RISK_ANALYSIS"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["profile"] == "RISK_ANALYSIS"
    assert "candidate_count" in body
    assert body["search_parameters"]["distance_metric"] == "cosine"
    assert body["search_parameters"]["preferred_sections"]      # profile injected
    assert body["query_embedding"]["dimension"] == DIM
    assert "filter_ms" in body["timings"]


@pytest.mark.integration
async def test_risk_profile_scopes_to_risk_sections(
    hybrid_client: AsyncClient, sync_session: Session
) -> None:
    _seed_two_companies(sync_session)
    resp = await hybrid_client.post(
        f"{PREFIX}/search/hybrid",
        json={"query": "battery production", "profile": "RISK_ANALYSIS", "top_k": 10},
    )
    body = resp.json()
    # RISK_ANALYSIS prefers Risk Factors → only risk chunks are candidates.
    assert body["candidate_count"] == 2
    assert all(r["metadata"]["normalized_section_name"] == "Risk Factors" for r in body["results"])
