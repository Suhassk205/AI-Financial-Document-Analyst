"""Tone record matcher comparing current and previous reporting periods (Phase 5)."""

from __future__ import annotations

from collections import defaultdict
from app.models.management_tone import ManagementTone


class ToneMatcher:
    """Matches management tone records from sequential periods by source type."""

    def match(
        self, current: list[ManagementTone], previous: list[ManagementTone]
    ) -> list[tuple[ManagementTone | None, ManagementTone | None]]:
        """Match current and previous tone records by source_type sequentially."""
        current_by_type = defaultdict(list)
        for r in current:
            current_by_type[r.source_type].append(r)

        previous_by_type = defaultdict(list)
        for r in previous:
            previous_by_type[r.source_type].append(r)

        # Sort each group by chunk index / id to ensure stable sequential matching
        for k in current_by_type:
            current_by_type[k].sort(key=lambda x: x.created_at)
        for k in previous_by_type:
            previous_by_type[k].sort(key=lambda x: x.created_at)

        all_types = set(current_by_type.keys()) | set(previous_by_type.keys())
        matches: list[tuple[ManagementTone | None, ManagementTone | None]] = []

        for stype in all_types:
            curr_list = current_by_type.get(stype, [])
            prev_list = previous_by_type.get(stype, [])

            max_len = max(len(curr_list), len(prev_list))
            for i in range(max_len):
                c_item = curr_list[i] if i < len(curr_list) else None
                p_item = prev_list[i] if i < len(prev_list) else None
                matches.append((c_item, p_item))

        return matches
