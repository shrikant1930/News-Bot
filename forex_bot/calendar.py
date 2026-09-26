"""Calendar fetch and event reconciliation, using the established identity engine."""

from typing import Any

from news_manager import get_calendar, prepare_event, reconcile_events, should_include


def fetch_prepared_events() -> list[dict[str, Any]]:
    raw_events = get_calendar()  # Raises on timeout, 429, malformed JSON, or empty feed.
    prepared = []
    for raw_event in raw_events:
        if not isinstance(raw_event, dict) or not should_include(raw_event):
            continue
        try:
            prepared.append(prepare_event(raw_event))
        except (TypeError, ValueError, KeyError):
            # A single broken provider record must not poison the complete refresh.
            continue
    if not prepared:
        raise RuntimeError("Calendar contained no valid relevant events; storage left unchanged.")
    return prepared


def reconcile(existing: dict[str, dict[str, Any]], prepared: list[dict[str, Any]]):
    """Delegate to the proven persistent-ID, duplicates, and reschedule logic."""
    return reconcile_events(existing, prepared)
