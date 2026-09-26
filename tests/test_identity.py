from datetime import datetime, timedelta, timezone

from news_manager import reconcile_events


def prepared(title="CPI", moment=None):
    moment = moment or datetime(2026, 1, 1, 10, tzinfo=timezone.utc)
    return {"title": title, "currency": "USD", "impact": "High", "time_utc": moment.isoformat(), "forecast": "1", "previous": "0", "is_speech": False, "_datetime": moment, "_date": moment.date().isoformat(), "_match_key": f"USD|{title.lower()}"}


def stored(event_id, item):
    return {"id": event_id, "match_key": item["_match_key"], "title": item["title"], "currency": item["currency"], "impact": item["impact"], "time_utc": item["time_utc"], "forecast": item["forecast"], "previous": item["previous"], "is_speech": False, "status": "active", "created_at": item["time_utc"]}


def test_reschedule_keeps_persistent_id():
    initial = prepared()
    moved = prepared(moment=initial["_datetime"] + timedelta(days=1))
    current, new, changed, _ = reconcile_events({"stable": stored("stable", initial)}, [moved])
    assert list(current) == ["stable"]
    assert not new
    assert changed[0]["changes"] == ["time changed"]


def test_duplicate_titles_remain_distinct():
    first = prepared(moment=datetime(2026, 1, 1, 10, tzinfo=timezone.utc))
    second = prepared(moment=datetime(2026, 1, 1, 12, tzinfo=timezone.utc))
    existing = {"one": stored("one", first), "two": stored("two", second)}
    moved = [prepared(moment=first["_datetime"] + timedelta(minutes=30)), prepared(moment=second["_datetime"] + timedelta(minutes=30))]
    current, new, _, _ = reconcile_events(existing, moved)
    assert set(current) == {"one", "two"}
    assert not new
