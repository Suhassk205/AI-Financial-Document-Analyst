"""Normalization utilities for management tone classification (Phase 5)."""

from __future__ import annotations

import re


def clean_text(text: str) -> str:
    """Normalize whitespace and lowercase text for robust phrase matching."""
    if not text:
        return ""
    # Replace newlines/tabs with space
    cleaned = re.sub(r"\s+", " ", text)
    return cleaned.strip().lower()


def split_sentences(text: str) -> list[str]:
    """Split text into sentences using simple regex boundaries."""
    if not text:
        return []
    # Split on periods/exclamations/question marks followed by spaces
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return [s.strip() for s in sentences if s.strip()]


def count_phrase_occurrences(text: str, phrases: list[str]) -> int:
    """Count the total number of times any of the target phrases occur in the text.

    Case-insensitive substring matching is used. We use cleaned text to normalize spaces.
    """
    text_clean = clean_text(text)
    if not text_clean:
        return 0

    count = 0
    for phrase in phrases:
        phrase_clean = clean_text(phrase)
        # Using re.escape and finding all matches
        matches = re.findall(re.escape(phrase_clean), text_clean)
        count += len(matches)
    return count
