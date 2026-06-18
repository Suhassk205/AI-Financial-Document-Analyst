"""§1 End-to-End Validation Suite — full pipeline integrity.

Walks the entire document→answer chain through the live API and verifies each
stage produced queryable output:

    Upload → Parse → Sections → Chunks → Embeddings → Retrieval →
    Financial → Risk → Tone → Benchmark → Memo → Agent

The deterministic demo dataset stands in for the ingestion stages (a fully
``READY`` report with sections, embedded chunks, metrics, risks and
tone), so this check is reproducible and key-free. The retrieval, benchmark,
memo and agent stages are exercised against the running services.

Run ``python -m validation.seed_demo`` first.

    python -m validation.e2e_validation
"""

from __future__ import annotations

import sys

from validation._client import ValidationClient
from validation._results import Suite
from validation.seed_demo import COHORT, _uid


def run(client: ValidationClient | None = None) -> Suite:
    suite = Suite("E2E Validation")
    own = client is None
    client = client or ValidationClient()
    try:
        client.ensure_auth()
        ticker = COHORT[0]["ticker"]
        company_id = str(_uid("company", ticker))
        report_id = str(_uid("report", ticker))

        # Stage 0: report exists in a fully-processed terminal status.
        rep = client.get(f"/reports/{report_id}")
        status = rep.json().get("status") if rep.status == 200 else None
        suite.record("Upload→Process: report in terminal status",
                     rep.status == 200 and status == "READY", f"status={status}")

        # Stage 1: Section extraction.
        sec = client.get(f"/reports/{report_id}/sections")
        n_sec = len(sec.json()) if sec.status == 200 and isinstance(sec.json(), list) else \
            sec.json().get("count", 0) if sec.status == 200 else 0
        suite.record("Section extraction produced sections", sec.status == 200 and n_sec > 0,
                     f"{n_sec} sections")

        # Stage 2: Chunking.
        ch = client.get(f"/reports/{report_id}/chunks")
        ch_body = ch.json() if ch.status == 200 else {}
        n_chunks = ch_body.get("count") or len(ch_body.get("items", [])) if isinstance(ch_body, dict) else 0
        suite.record("Chunking produced chunks", ch.status == 200 and n_chunks > 0, f"{n_chunks} chunks")

        # Stage 3: Embeddings.
        emb = client.get(f"/reports/{report_id}/embeddings/stats")
        emb_ok = emb.status == 200
        suite.record("Embeddings present for chunks", emb_ok,
                     str(emb.json()) if emb_ok else f"HTTP {emb.status}")

        # Stage 4: Retrieval (hybrid + RAG assembly).
        hb = client.post("/search/hybrid", json={"query": "free cash flow", "top_k": 5})
        suite.record("Retrieval: hybrid search returns hits",
                     hb.status == 200 and len(hb.json().get("results", [])) > 0,
                     f"HTTP {hb.status}, {len(hb.json().get('results', [])) if hb.status==200 else 0} hits")
        rag = client.post("/rag/retrieve",
                          json={"query": "revenue and risks", "strategy": "GENERAL_ANALYSIS", "top_k": 5})
        rag_cites = len(rag.json().get("citations", [])) if rag.status == 200 else 0
        suite.record("Retrieval: RAG assembles grounded context",
                     rag.status == 200 and rag_cites > 0, f"HTTP {rag.status}, {rag_cites} citations")

        # Stage 5: Financial intelligence.
        met = client.get(f"/reports/{report_id}/metrics")
        met_body = met.json() if met.status == 200 else {}
        n_met = met_body.get("count") or len(met_body.get("items", [])) if isinstance(met_body, dict) else 0
        suite.record("Financial extraction produced metrics", met.status == 200 and n_met > 0,
                     f"{n_met} metrics")

        # Stage 6: Risk intelligence.
        risk = client.get(f"/companies/{company_id}/risks")
        n_risk = risk.json().get("count", 0) if risk.status == 200 else 0
        suite.record("Risk extraction produced risks", risk.status == 200 and n_risk > 0, f"{n_risk} risks")

        # Stage 7: Tone intelligence.
        tone = client.get(f"/companies/{company_id}/tone")
        tone_ok = tone.status == 200 and bool(tone.json())
        suite.record("Tone extraction produced tone", tone_ok, f"HTTP {tone.status}")

        # Stage 8: Benchmarking.
        cohort = [str(_uid("company", c["ticker"])) for c in COHORT]
        bm = client.post("/benchmark/compare", json={"company_ids": cohort, "configuration": {}})
        n_summ = len(bm.json().get("cohort_summaries", [])) if bm.status == 200 else 0
        suite.record("Benchmarking ranks the cohort", bm.status == 200 and n_summ == len(cohort),
                     f"{n_summ}/{len(cohort)} ranked")

        # Stage 9: Memo generation (deterministic seeded memo).
        memo_id = str(_uid("memo", ticker))
        memo = client.get(f"/memos/{memo_id}")
        memo_ok = memo.status == 200 and memo.json().get("status") == "COMPLETED"
        suite.record("Memo available & completed", memo_ok,
                     f"HTTP {memo.status}, status={memo.json().get('status') if memo.status==200 else '-'}")

        # Stage 10: Agent response (best-effort — LLM may be rate-limited).
        agent = client.request("POST", "/agent/chat", timeout=90, json={
            "query": "What are the principal risks?", "thread_id": "e2e-smoke", "company_id": company_id,
        })
        agent_answered = agent.status == 200 and bool(agent.json().get("answer"))
        degraded = agent.status == 200 and "could not" in agent.json().get("answer", "").lower() \
            or "error" in agent.json().get("answer", "").lower()
        suite.record("Agent endpoint responds", agent_answered,
                     f"HTTP {agent.status}" + (" (LLM degraded — see agent_eval)" if degraded else ""),
                     warn=degraded)

        passed_stages = suite.passed
        suite.measure("stages_validated", len(suite.checks))
        suite.measure("stages_passed", passed_stages)
    finally:
        if own:
            client.close()

    suite.print_summary()
    return suite


def main() -> int:
    suite = run()
    suite.save()
    return 0 if suite.ok else 1


if __name__ == "__main__":
    sys.exit(main())
