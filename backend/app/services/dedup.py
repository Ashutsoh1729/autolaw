"""Deduplication engine — resolves overlapping/near-duplicate events using fuzzy matching."""

import hashlib
import json
from typing import Any

from rapidfuzz import fuzz

from app.schemas.event import EventResponse


def _normalize_text(text: str) -> str:
    """Normalize text for comparison."""
    return " ".join(text.lower().split())


def _compute_fingerprint(event: EventResponse) -> str:
    """Compute a stable fingerprint for an event based on date + normalized title."""
    raw = f"{event.date}|{event.title}|{sorted(event.people)}"
    return hashlib.md5(raw.encode()).hexdigest()


def _compute_dedup_group(event: dict[str, Any]) -> str:
    """Compute a dedup group hash for a raw extracted event."""
    title = _normalize_text(event.get("title", ""))
    desc = _normalize_text(event.get("description", ""))
    people = sorted(event.get("people", []))
    raw = f"{event.get('date', '')}|{title[:100]}|{desc[:200]}|{people}"
    return hashlib.md5(raw.encode()).hexdigest()[:16]


def _events_overlap(a: EventResponse, b: EventResponse, threshold: int = 80) -> bool:
    """Check if two events likely describe the same real-world event."""
    # Same date (or close dates) is a strong signal
    date_match = a.date == b.date
    if a.date_end and b.date_end:
        date_match = date_match or a.date_end == b.date_end

    # Fuzzy match title and description
    title_sim = fuzz.token_sort_ratio(
        _normalize_text(a.title), _normalize_text(b.title)
    )
    desc_sim = 0
    if a.description and b.description:
        desc_sim = fuzz.token_sort_ratio(
            _normalize_text(a.description), _normalize_text(b.description)
        )

    # Check people overlap
    people_a = set(p.lower() for p in a.people)
    people_b = set(p.lower() for p in b.people)
    people_overlap = len(people_a & people_b) > 0 if people_a and people_b else True

    # Scoring
    if date_match and title_sim >= threshold:
        return True
    if date_match and desc_sim >= threshold:
        return True
    if title_sim >= threshold and desc_sim >= threshold and people_overlap:
        return True
    return False


def deduplicate_events(events: list[EventResponse], threshold: int = 80) -> list[EventResponse]:
    """Deduplicate a list of events, keeping the highest-confidence version of duplicates."""
    if not events:
        return []

    # Sort by confidence descending so we keep the best version
    sorted_events = sorted(events, key=lambda e: e.confidence, reverse=True)

    deduped: list[EventResponse] = []
    seen_fingerprints: set[str] = set()

    for event in sorted_events:
        fp = _compute_fingerprint(event)

        # Exact fingerprint match
        if fp in seen_fingerprints:
            continue

        # Fuzzy overlap check against already kept events
        is_duplicate = False
        for kept in deduped:
            if _events_overlap(event, kept, threshold):
                is_duplicate = True
                # Merge dedup groups
                if kept.dedup_group is None:
                    kept.dedup_group = event.dedup_group or fp
                break

        if not is_duplicate:
            seen_fingerprints.add(fp)
            deduped.append(event)

    return deduped


def sort_events_chronologically(events: list[EventResponse]) -> list[EventResponse]:
    """Sort events by date chronologically.

    Handles partial dates by treating unspecified parts as early (Jan 1 for year-only, 1st for month-only).
    """
    from datetime import datetime

    def _parse_date_for_sort(date_str: str, precision: str) -> str:
        """Convert a date string to a sortable ISO-like format."""
        # Already ISO-like
        if date_str and date_str[0].isdigit() and len(date_str) >= 10:
            return date_str[:10]

        # Try parsing various formats
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%B %d, %Y", "%B %Y", "%Y"):
            try:
                dt = datetime.strptime(date_str, fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue

        # Fallback: extract year
        import re
        year_match = re.search(r"\b(\d{4})\b", date_str)
        if year_match:
            year = year_match.group(1)
            if precision == "year":
                return f"{year}-01-01"
            elif precision == "month":
                return f"{year}-01-01"
            return f"{year}-01-01"

        return "0000-01-01"

    def _sort_key(e: EventResponse) -> tuple:
        sort_date = _parse_date_for_sort(e.date, e.date_precision)
        return (sort_date, e.confidence or 0)

    return sorted(events, key=_sort_key)


async def process_events(
    raw_events: list[dict[str, Any]],
    matter_id: str,
    source_document_id: str,
    chunk_index: int | None = None,
) -> list[dict[str, Any]]:
    """Process raw extracted events: add metadata and compute dedup groups."""
    processed = []
    for evt in raw_events:
        evt["matter_id"] = matter_id
        evt["source_document_id"] = source_document_id
        evt["source_chunk_index"] = chunk_index
        evt["dedup_group"] = _compute_dedup_group(evt)
        processed.append(evt)
    return processed
