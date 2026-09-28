from datetime import datetime, timezone
from zoneinfo import ZoneInfo

SUPPORTED_CURRENCIES = frozenset({"USD", "EUR", "GBP", "JPY", "CAD", "AUD", "NZD", "CHF"})


def normalize_currency(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    currency = value.strip().upper()
    return currency if currency in SUPPORTED_CURRENCIES else None


def normalized_currencies(group: dict) -> set[str]:
    values = group.get("currencies", [])
    if not isinstance(values, list):
        return set()
    return {currency for value in values if (currency := normalize_currency(value)) is not None}


def event_matches_group(event: dict, group: dict) -> bool:
    """Match events for Daily/Weekly briefings."""
    currency = normalize_currency(event.get("currency"))
    if currency is None or currency not in normalized_currencies(group):
        return False

    if event.get("is_speech", False):
        return bool(group.get("include_speeches", False))

    return event.get("impact") in group.get("impacts", [])


def event_matches_alert_group(event: dict, group: dict) -> bool:
    """Match events that are allowed to trigger timed alerts."""
    currency = normalize_currency(event.get("currency"))
    if currency is None or currency not in normalized_currencies(group):
        return False

    if event.get("impact") not in group.get("alert_impacts", []):
        return False

    if event.get("is_speech", False):
        return bool(group.get("include_speeches", False))

    return True


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def local_time(event: dict, timezone_name: str) -> datetime:
    return parse_utc(event["time_utc"]).astimezone(ZoneInfo(timezone_name))


def normalized_minutes(group: dict) -> list[int]:
    values = group.get("alert_minutes_before", [])
    if not isinstance(values, list):
        return []
    result = set()
    for value in values:
        try:
            result.add(int(value))
        except (TypeError, ValueError):
            pass
    return sorted(result, reverse=True)
