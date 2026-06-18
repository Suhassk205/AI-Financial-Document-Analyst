"""§3 Demo Dataset Package — deterministic, key-free demo seeder.

Inserts a small, fully-processed peer cohort directly via the ORM so the entire
read surface (reports, risks, tone, financial metrics, hybrid search,
benchmarking, memos) has consistent data for demos and for the data-dependent
validation suites — WITHOUT calling Gemini or running Celery.

Properties
----------
- **Deterministic**: fixed UUIDs + content; re-running replaces the demo rows.
- **Key-free**: embeddings are computed locally (hashed → normalised 768-dim),
  so no GEMINI_API_KEY / DEMO_MODE is required.
- **Idempotent**: existing demo companies (by ticker prefix ``DEMO`` ) are
  deleted first (cascades clean up reports/chunks/risks/tone).

The companies are FICTIONAL (no real-issuer data) to keep the demo self-contained.

Run:  python -m validation.seed_demo
"""

from __future__ import annotations

import asyncio
import hashlib
import math
import uuid
from typing import Any

from app.db.session import AsyncSessionLocal
from app.models import (
    Company,
    DocumentChunk,
    FinancialMetric,
    InvestmentMemo,
    ManagementTone,
    MemoSection,
    Report,
    ReportSection,
    RiskFactor,
)
from app.models.enums import MemoStatus, MemoType, ReportStatus, ReportType
from sqlalchemy import delete, select

EMBED_DIM = 768

# Stable namespace so the same company/report always gets the same UUID.
_NS = uuid.UUID("12000000-0000-0000-0000-000000000000")


def _uid(*parts: str) -> uuid.UUID:
    return uuid.uuid5(_NS, "::".join(parts))


def _embed(text: str) -> list[float]:
    """Deterministic, locally-computed unit-norm 768-dim vector for ``text``.

    Not semantically meaningful — it exists so seeded chunks are retrievable by
    pgvector (the search layer filters ``embedding IS NOT NULL``) and so identical
    text always maps to an identical vector. Built by expanding SHA256 digests.
    """
    raw = bytearray()
    counter = 0
    while len(raw) < EMBED_DIM * 2:
        raw += hashlib.sha256(f"{text}|{counter}".encode()).digest()
        counter += 1
    vals = [((raw[2 * i] << 8) | raw[2 * i + 1]) / 65535.0 - 0.5 for i in range(EMBED_DIM)]
    norm = math.sqrt(sum(v * v for v in vals)) or 1.0
    return [v / norm for v in vals]


# --- Cohort definition -----------------------------------------------------
# Three fictional technology peers with intentionally different financial,
# risk and tone profiles so benchmarking produces a meaningful ranking.
COHORT: list[dict[str, Any]] = [
    {
        "name": "Apex Robotics Inc.",
        "ticker": "DEMO-APX",
        "sector": "Technology",
        "industry": "Industrial Automation",
        "year": 2024,
        "revenue_b": 48.2,
        "net_margin_pct": 24.5,
        "fcf_b": 11.8,
        # normalized_name -> (value, unit) — names match the benchmarking aliases
        # so every dimension (financial + capital allocation) scores. All metrics
        # are "higher is better" to keep the ground-truth ranking unambiguous.
        "fin": {
            "REVENUE": (48.2, "BILLION"), "NET_MARGIN": (24.5, "PERCENT"),
            "OPERATING_MARGIN": (30.0, "PERCENT"), "FREE_CASH_FLOW": (11.8, "BILLION"),
            "CASH_FLOW_MARGIN": (24.5, "PERCENT"), "CAPEX": (3.0, "BILLION"),
            "DIVIDENDS": (2.0, "BILLION"),
        },
        "tone": ("POSITIVE", "CONFIDENT", 0.12, 0.78, 0.10),
        "risks": [
            ("Supply Chain Concentration Risk", "SUPPLY_CHAIN", "HIGH",
             "A majority of precision actuators are sourced from a single region, "
             "exposing production to geopolitical and logistics disruption."),
            ("Competitive Pricing Pressure", "COMPETITION", "MEDIUM",
             "Aggressive pricing by emerging automation vendors could compress margins."),
        ],
    },
    {
        "name": "Bolt Dynamics Corp.",
        "ticker": "DEMO-BLT",
        "sector": "Technology",
        "industry": "Industrial Automation",
        "year": 2024,
        "revenue_b": 29.7,
        "net_margin_pct": 14.1,
        "fcf_b": 4.3,
        "fin": {
            "REVENUE": (29.7, "BILLION"), "NET_MARGIN": (14.1, "PERCENT"),
            "OPERATING_MARGIN": (18.0, "PERCENT"), "FREE_CASH_FLOW": (4.3, "BILLION"),
            "CASH_FLOW_MARGIN": (14.5, "PERCENT"), "CAPEX": (2.0, "BILLION"),
            "DIVIDENDS": (0.5, "BILLION"),
        },
        "tone": ("NEUTRAL", "CAUTIOUS", 0.34, 0.45, 0.30),
        "risks": [
            ("Foreign Exchange Volatility", "MARKET", "HIGH",
             "Over half of revenue is earned abroad; currency swings materially "
             "affect reported results."),
            ("Cybersecurity Incident Risk", "CYBERSECURITY", "CRITICAL",
             "Connected factory products increase exposure to security breaches "
             "that could disrupt customers and trigger liability."),
            ("Regulatory Compliance Risk", "REGULATORY", "MEDIUM",
             "Evolving safety regulations for autonomous systems may raise "
             "compliance costs."),
        ],
    },
    {
        "name": "Cortex Systems plc",
        "ticker": "DEMO-CTX",
        "sector": "Technology",
        "industry": "Industrial Automation",
        "year": 2024,
        "revenue_b": 12.4,
        "net_margin_pct": 8.9,
        "fcf_b": 1.1,
        "fin": {
            "REVENUE": (12.4, "BILLION"), "NET_MARGIN": (8.9, "PERCENT"),
            "OPERATING_MARGIN": (9.5, "PERCENT"), "FREE_CASH_FLOW": (1.1, "BILLION"),
            "CASH_FLOW_MARGIN": (8.9, "PERCENT"), "CAPEX": (1.0, "BILLION"),
            "DIVIDENDS": (0.0, "BILLION"),
        },
        "tone": ("NEGATIVE", "VERY_CAUTIOUS", 0.52, 0.28, 0.55),
        "risks": [
            ("Liquidity and Refinancing Risk", "LIQUIDITY", "CRITICAL",
             "Near-term debt maturities combined with negative operating cash flow "
             "in two segments raise refinancing risk."),
            ("Customer Concentration Risk", "MARKET", "HIGH",
             "The top three customers account for a large share of revenue."),
        ],
    },
]

SECTIONS = [
    ("Item 1 - Business", "BUSINESS", 1, 14),
    ("Item 1A - Risk Factors", "RISK_FACTORS", 15, 38),
    ("Item 7 - Management's Discussion and Analysis", "MDA", 39, 62),
]


async def _purge_demo(db: Any) -> int:
    tickers = [c["ticker"] for c in COHORT]
    existing = (await db.execute(select(Company).where(Company.ticker.in_(tickers)))).scalars().all()
    for company in existing:
        await db.execute(delete(Company).where(Company.id == company.id))
    await db.commit()
    return len(existing)


async def seed() -> dict[str, Any]:
    summary: dict[str, Any] = {"companies": [], "purged": 0, "chunks": 0, "metrics": 0, "risks": 0, "tone": 0}
    async with AsyncSessionLocal() as db:
        summary["purged"] = await _purge_demo(db)

        for spec in COHORT:
            cid = _uid("company", spec["ticker"])
            company = Company(
                id=cid,
                name=spec["name"],
                ticker=spec["ticker"],
                sector=spec["sector"],
                industry=spec["industry"],
            )
            db.add(company)

            rid = _uid("report", spec["ticker"])
            report = Report(
                id=rid,
                company_id=cid,
                report_type=ReportType.TEN_K,
                year=spec["year"],
                original_filename=f"{spec['ticker']}_{spec['year']}_10K.pdf",
                storage_path=f"demo/{spec['ticker']}/{spec['year']}_10K.pdf",
                status=ReportStatus.READY,
                total_pages=62,
            )
            db.add(report)

            # Sections + one searchable chunk each.
            section_ids: dict[str, uuid.UUID] = {}
            for sname, norm, sp, ep in SECTIONS:
                sid = _uid("section", spec["ticker"], norm)
                section_ids[norm] = sid
                db.add(
                    ReportSection(
                        id=sid,
                        report_id=rid,
                        section_name=sname,
                        normalized_section_name=norm,
                        start_page=sp,
                        end_page=ep,
                        content="",
                        confidence_score=0.95,
                    )
                )

            chunk_texts = [
                (
                    "BUSINESS",
                    f"{spec['name']} designs and manufactures industrial robotics and "
                    f"automation systems. In fiscal {spec['year']} the company reported "
                    f"total revenue of approximately ${spec['revenue_b']} billion with a "
                    f"net margin of {spec['net_margin_pct']}%.",
                ),
                (
                    "MDA",
                    f"Free cash flow for {spec['name']} was approximately "
                    f"${spec['fcf_b']} billion. Management discussed capital allocation, "
                    f"operating leverage, and demand trends across automation segments.",
                ),
                (
                    "RISK_FACTORS",
                    f"{spec['name']} faces the following principal risks: "
                    + "; ".join(r[0] for r in spec["risks"]) + ".",
                ),
            ]
            chunk_ids: dict[str, uuid.UUID] = {}
            for ci, (norm, text) in enumerate(chunk_texts):
                ch_id = _uid("chunk", spec["ticker"], str(ci))
                chunk_ids[norm] = ch_id
                db.add(
                    DocumentChunk(
                        id=ch_id,
                        report_id=rid,
                        section_id=section_ids.get(norm),
                        chunk_index=ci,
                        chunk_text=text,
                        token_count=max(10, len(text.split())),
                        start_page=1,
                        end_page=1,
                        embedding=_embed(text),
                        embedding_status="COMPLETED",
                        embedding_model="demo-local-hash-768",
                    )
                )
                summary["chunks"] += 1

            # Flush so chunks/sections exist before rows that reference them by
            # literal FK id (source_chunk_id is set as a value, not a relationship,
            # so the unit-of-work cannot infer the insert ordering on its own).
            await db.flush()

            # Financial metrics — normalized names match the benchmarking aliases
            # (comparison_builder.py) so the FINANCIAL and CAPITAL_ALLOCATION
            # dimensions score, not just RISK and TONE.
            category_for = {
                "REVENUE": "REVENUE", "NET_MARGIN": "MARGINS", "OPERATING_MARGIN": "MARGINS",
                "FREE_CASH_FLOW": "CASH_FLOW", "CASH_FLOW_MARGIN": "CASH_FLOW",
                "CAPEX": "CAPEX", "DIVIDENDS": "CAPEX",
            }
            for norm, (val, unit) in spec["fin"].items():
                db.add(
                    FinancialMetric(
                        id=_uid("metric", spec["ticker"], norm),
                        report_id=rid,
                        source_chunk_id=chunk_ids.get("BUSINESS"),
                        metric_name=norm.replace("_", " ").title(),
                        normalized_metric_name=norm,
                        metric_category=category_for.get(norm, "OTHER"),
                        value=val,
                        currency="USD" if unit == "BILLION" else None,
                        unit=unit,
                        fiscal_year=spec["year"],
                        confidence_score=0.92,
                        extraction_method="HYBRID_VALIDATED",
                        source_text=chunk_texts[0][1],
                    )
                )
                summary["metrics"] += 1

            # Risk factors.
            for rname, cat, sev, desc in spec["risks"]:
                db.add(
                    RiskFactor(
                        id=_uid("risk", spec["ticker"], rname),
                        company_id=cid,
                        report_id=rid,
                        source_chunk_id=chunk_ids.get("RISK_FACTORS"),
                        risk_name=rname,
                        normalized_risk_name=rname.lower().replace(" ", "_"),
                        risk_description=desc,
                        category=cat,
                        severity=sev,
                        confidence_score=0.88,
                        extraction_method="LLM_BASED",
                        source_text=desc,
                    )
                )
                summary["risks"] += 1

            # Management tone.
            sentiment, conf_level, hedging, positive, negative = spec["tone"]
            db.add(
                ManagementTone(
                    id=_uid("tone", spec["ticker"]),
                    company_id=cid,
                    report_id=rid,
                    source_chunk_id=chunk_ids.get("MDA"),
                    source_type="MDA",
                    sentiment=sentiment,
                    confidence_level=conf_level,
                    hedging_score=hedging,
                    positive_score=positive,
                    negative_score=negative,
                    confidence_score=0.87,
                    extraction_method="LLM_BASED",
                    source_text=chunk_texts[1][1],
                )
            )
            summary["tone"] += 1

            summary["companies"].append(
                {"id": str(cid), "name": spec["name"], "ticker": spec["ticker"], "report_id": str(rid)}
            )

            # A deterministic, COMPLETED single-company memo for the strongest
            # peer, so the memo read / citation / export surface is demonstrable
            # without invoking the LLM generator. Citations reference real seeded
            # chunks (text_chunk) and structured sources (financial_metric).
            if spec["ticker"] == COHORT[0]["ticker"]:
                memo_id = _uid("memo", spec["ticker"])
                biz_chunk = str(chunk_ids["BUSINESS"])
                risk_chunk = str(chunk_ids["RISK_FACTORS"])
                db.add(
                    InvestmentMemo(
                        id=memo_id,
                        company_id=cid,
                        report_id=rid,
                        memo_type=MemoType.SINGLE_COMPANY,
                        status=MemoStatus.COMPLETED,
                        title=f"Investment Memo — {spec['name']} (FY{spec['year']})",
                        executive_summary=(
                            f"{spec['name']} is the strongest performer in its peer cohort, "
                            f"with industry-leading margins (net {spec['net_margin_pct']}%), "
                            f"robust free cash flow (${spec['fcf_b']}B), and a confident "
                            f"management tone. The principal watch item is supply-chain "
                            f"concentration."
                        ),
                        content="See sections for the full thesis, bull case and bear case.",
                        metadata_fields={"generated_by": "demo_seed", "deterministic": True},
                    )
                )
                memo_sections = [
                    (
                        "Investment Thesis", 1,
                        f"{spec['name']} combines scale (${spec['revenue_b']}B revenue) with "
                        f"best-in-cohort profitability and cash generation, supporting a "
                        f"constructive view.",
                        [
                            {"report_id": str(rid), "chunk_id": biz_chunk,
                             "source_type": "text_chunk", "page_number": 1,
                             "section_name": "Item 1 - Business",
                             "text_snippet": "total revenue of approximately"},
                            {"report_id": str(rid), "source_type": "financial_metric",
                             "section_name": "MD&A", "text_snippet": "Net margin 24.5%"},
                        ],
                    ),
                    (
                        "Bull Case", 2,
                        "Operating leverage and disciplined capital allocation (CAPEX + "
                        "dividends) can compound free cash flow if automation demand holds.",
                        [{"report_id": str(rid), "source_type": "financial_metric",
                          "text_snippet": "Free cash flow ~$11.8B"}],
                    ),
                    (
                        "Bear Case", 3,
                        "Supply-chain concentration in a single region is the key downside "
                        "risk; a disruption would pressure production and margins.",
                        [{"report_id": str(rid), "chunk_id": risk_chunk,
                          "source_type": "risk_factor", "page_number": 1,
                          "section_name": "Item 1A - Risk Factors",
                          "text_snippet": "sourced from a single region"}],
                    ),
                ]
                for sname, order, content, cites in memo_sections:
                    db.add(
                        MemoSection(
                            id=_uid("memo_section", spec["ticker"], str(order)),
                            memo_id=memo_id,
                            section_name=sname,
                            section_order=order,
                            content=content,
                            citations=cites,
                        )
                    )
                summary["memo_id"] = str(memo_id)

        await db.commit()
    return summary


def main() -> None:
    result = asyncio.run(seed())
    print("Demo dataset seeded (fictional cohort):")
    print(f"  purged prior demo companies : {result['purged']}")
    print(f"  companies                   : {len(result['companies'])}")
    print(f"  chunks (with embeddings)    : {result['chunks']}")
    print(f"  financial metrics           : {result['metrics']}")
    print(f"  risk factors                : {result['risks']}")
    print(f"  tone rows                   : {result['tone']}")
    for c in result["companies"]:
        print(f"    - {c['ticker']:10s} {c['name']:24s} company_id={c['id']}")


if __name__ == "__main__":
    main()
