"""Lightweight retrieval and matching of released economic results."""

import re
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

RESULTS_URL = "https://biquote.io/api/calendar"
MATCH_TOLERANCE = timedelta(minutes=2)


class ResultSource:
    """No-key released-results source; queried only for eligible releases."""

    def __init__(self, session: requests.Session | None = None):
        self._session = session or requests.Session()

    def fetch(self, start: datetime, end: datetime) -> list[dict[str, Any]]:
        response = self._session.get(
            RESULTS_URL,
            params={
                "from": start.astimezone(timezone.utc).isoformat(),
                "to": end.astimezone(timezone.utc).isoformat(),
                "limit": 100,
            },
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise RuntimeError("Result source returned an unexpected payload")
        return [row for row in payload if isinstance(row, dict)]


def match_released_results(events: list[dict], source_events: list[dict]) -> list[dict]:
    """Return only conservative, unambiguous event/result matches.

    Exact normalized titles are preferred. A renamed release can match only
    when there is exactly one candidate at the same currency/time and its
    parsed forecast agrees, avoiding a loose title-only match.
    """
    matches = []
    for event in events:
        candidates = [
            source_event
            for source_event in source_events
            if _same_currency_and_time(event, source_event)
            and _present(source_event.get("actual"))
            and _present(source_event.get("forecast"))
        ]
        exact_title = [candidate for candidate in candidates if _normalize(event.get("title")) == _normalize(candidate.get("name"))]
        candidates = exact_title or [
            candidate
            for candidate in candidates
            if _equal_values(str(event.get("forecast", "")), str(candidate["forecast"]))
        ]
        if len(candidates) != 1:
            continue
        source_event = candidates[0]
        matches.append(
            {
                "event": event,
                "actual": str(source_event["actual"]),
                "forecast": str(source_event["forecast"]),
                "previous": _text_or_none(source_event.get("previous")),
            }
        )
    return matches


def compare_actual_to_forecast(actual: str, forecast: str) -> str:
    """Return above, below, or inline only when the values are comparable."""
    actual_value = _parse_value(actual)
    forecast_value = _parse_value(forecast)
    if actual_value is None or forecast_value is None or actual_value[1] != forecast_value[1]:
        return "inline"
    if actual_value[0] > forecast_value[0]:
        return "above"
    if actual_value[0] < forecast_value[0]:
        return "below"
    return "inline"


def _same_currency_and_time(event: dict, source_event: dict) -> bool:
    if _normalize(event.get("currency")) != _normalize(source_event.get("currency")):
        return False
    try:
        event_time = _parse_utc(event["time_utc"])
        source_time = _parse_utc(source_event["time"])
    except (KeyError, TypeError, ValueError):
        return False
    return abs(event_time - source_time) <= MATCH_TOLERANCE


def _equal_values(left: str, right: str) -> bool:
    left_value = _parse_value(left)
    right_value = _parse_value(right)
    return left_value is not None and left_value == right_value


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def _normalize(value: object) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _present(value: object) -> bool:
    return value is not None and str(value).strip() != ""


def _text_or_none(value: object) -> str | None:
    return str(value) if _present(value) else None


_NUMBER = re.compile(r"^([+-]?)(\d[\d,]*(?:\.\d+)?)([KMBT]?)%?$")
_MULTIPLIERS = {"": 1, "K": 1_000, "M": 1_000_000, "B": 1_000_000_000, "T": 1_000_000_000_000}


def _parse_value(value: str) -> tuple[float, bool] | None:
    text = value.strip().upper().replace(" ", "")
    is_percent = text.endswith("%")
    if is_percent:
        text = text[:-1]
    matched = _NUMBER.fullmatch(text)
    if not matched:
        return None
    sign, number, suffix = matched.groups()
    result = float(number.replace(",", "")) * _MULTIPLIERS[suffix]
    return (-result if sign == "-" else result, is_percent)
