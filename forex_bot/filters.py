from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def event_matches_group(event: dict, group: dict) -> bool:
    if event.get("currency") not in group.get("currencies", []):
        return False
    if event.get("is_speech", False):
        return bool(group.get("include_speeches", False))
    return event.get("impact") in group.get("impacts", [])


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
