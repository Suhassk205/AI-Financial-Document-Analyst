"""Evidence Fusion node (Phase 7).

Synthesizes outputs from multiple tools into a unified, structured context block.
"""

from __future__ import annotations

import json
from typing import Any

from app.core.logging import get_logger
from app.agents.financial_analyst.state import AgentState
from app.agents.financial_analyst.validators import validate_evidence_fusion

log = get_logger(__name__)


class EvidenceFusion:
    """Synthesizes structured tool outputs into a coherent markdown representation."""

    async def fuse_evidence(self, state: AgentState) -> dict[str, Any]:
        """Aggregate tool results into a structured string."""
        validate_evidence_fusion(state)
        tool_outputs = state.get("tool_outputs") or []

        if not tool_outputs:
            return {"fused_evidence": "No primary evidence retrieved from database."}

        sections = []

        for out in tool_outputs:
            tool_name = out["tool_name"]
            success = out["success"]
            result = out["result"]

            if not success:
                sections.append(f"### Tool Execution Failure: {tool_name}\nDetail: {result}\n")
                continue

            if tool_name == "retrieve_evidence":
                context_text = result.get("context_text", "")
                citations = result.get("citations", [])
                sections.append(
                    f"### Retrieved Document Context\n{context_text}\n"
                )
                if citations:
                    citations_str = "\n".join(
                        [f"- [{c['citation_id']}] Section '{c['section_name']}' (Page {c['page_number']}): {c['source_text_preview']}"
                         for c in citations]
                    )
                    sections.append(f"#### Source Citations:\n{citations_str}\n")

            elif tool_name == "get_financial_metrics":
                metrics_list = result
                if not metrics_list:
                    sections.append("### Financial Metrics\nNo financial metrics found matching the query criteria.\n")
                else:
                    lines = [
                        "| Metric Name | Value | Period | Category | Confidence |",
                        "| :--- | :--- | :--- | :--- | :--- |"
                    ]
                    for m in metrics_list:
                        period = f"FY{m['fiscal_year']}"
                        if m['fiscal_quarter']:
                            period += f" Q{m['fiscal_quarter']}"
                        val_str = f"{m['currency'] or ''} {m['value']:,} {m['unit'] or ''}".strip()
                        lines.append(
                            f"| {m['normalized_metric_name']} ({m['metric_name']}) | {val_str} | {period} | {m['metric_category']} | {m['confidence_score']:.2f} |"
                        )
                    sections.append("### Financial Metrics\n" + "\n".join(lines) + "\n")

            elif tool_name == "get_metric_comparisons":
                comps = result
                if not comps:
                    sections.append("### Period-over-Period Comparisons\nNo comparison records found.\n")
                else:
                    lines = [
                        "| Metric Name | Current Val | Prev Val | Abs Change | % Change | Current Period | Prev Period |",
                        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |"
                    ]
                    for c in comps:
                        pct = f"{c['percentage_change'] * 100:.2f}%" if c['percentage_change'] is not None else "N/A"
                        abs_chg = f"{c['absolute_change']:,}" if c['absolute_change'] is not None else "N/A"
                        lines.append(
                            f"| {c['metric_name']} | {c['current_value'] or 'N/A'} | {c['previous_value'] or 'N/A'} | {abs_chg} | {pct} | {c['current_period']} | {c['previous_period']} |"
                        )
                    sections.append("### Period-over-Period Comparisons\n" + "\n".join(lines) + "\n")

            elif tool_name == "get_financial_analytics":
                ratios = result
                if not ratios:
                    sections.append("### Financial Ratios & Analytics\nNo financial analytics records found.\n")
                else:
                    lines = [
                        "| Ratio Name | Value | Category | Period | Signals |",
                        "| :--- | :--- | :--- | :--- | :--- |"
                    ]
                    for r in ratios:
                        period = f"FY{r['fiscal_year']}"
                        if r['fiscal_quarter']:
                            period += f" Q{r['fiscal_quarter']}"
                        signals_str = ", ".join([f"{k}: {v}" for k, v in r['signals'].items()]) if r['signals'] else "None"
                        lines.append(
                            f"| {r['ratio_name']} | {r['ratio_value'] or 'N/A'} | {r['category']} | {period} | {signals_str} |"
                        )
                    sections.append("### Financial Ratios & Analytics\n" + "\n".join(lines) + "\n")

            elif tool_name == "get_risk_factors":
                risks = result
                if not risks:
                    sections.append("### Risk Factors\nNo risk factors found.\n")
                else:
                    lines = [
                        "| Risk Name | Category | Severity | Confidence | Description |",
                        "| :--- | :--- | :--- | :--- | :--- |"
                    ]
                    for r in risks:
                        lines.append(
                            f"| {r['normalized_risk_name']} | {r['category']} | {r['severity']} | {r['confidence_score']:.2f} | {r['risk_description']} |"
                        )
                    sections.append("### Risk Factors\n" + "\n".join(lines) + "\n")

            elif tool_name == "get_risk_evolution":
                evos = result
                if not evos:
                    sections.append("### Risk Evolution\nNo risk evolution records found.\n")
                else:
                    lines = [
                        "| Evolution Type | Confidence | Explanation |",
                        "| :--- | :--- | :--- |"
                    ]
                    for e in evos:
                        lines.append(
                            f"| {e['evolution_type']} | {e['confidence_score']:.2f} | {e['explanation']} |"
                        )
                    sections.append("### Risk Evolution\n" + "\n".join(lines) + "\n")

            elif tool_name == "get_management_tone":
                tones = result
                if not tones:
                    sections.append("### Management Tone\nNo management tone records found.\n")
                else:
                    lines = [
                        "| Source Type | Sentiment | Confidence | Hedging Score | Positive | Negative |",
                        "| :--- | :--- | :--- | :--- | :--- | :--- |"
                    ]
                    for t in tones:
                        lines.append(
                            f"| {t['source_type']} | {t['sentiment']} | {t['confidence_level']} | {t['hedging_score']:.3f} | {t['positive_score']:.3f} | {t['negative_score']:.3f} |"
                        )
                    sections.append("### Management Tone\n" + "\n".join(lines) + "\n")

            elif tool_name == "get_tone_evolution":
                tone_evos = result
                if not tone_evos:
                    sections.append("### Tone Evolution\nNo tone evolution records found.\n")
                else:
                    lines = [
                        "| Evolution Type | Confidence | Explanation |",
                        "| :--- | :--- | :--- |"
                    ]
                    for te in tone_evos:
                        lines.append(
                            f"| {te['evolution_type']} | {te['confidence_score']:.2f} | {te['explanation']} |"
                        )
                    sections.append("### Tone Evolution\n" + "\n".join(lines) + "\n")

            else:
                sections.append(f"### {tool_name}\n{json.dumps(result, indent=2)}\n")

        fused = "\n\n".join(sections)
        log.info("evidence_fusion.success", len_chars=len(fused))
        return {"fused_evidence": fused}
