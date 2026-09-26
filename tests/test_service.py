from datetime import datetime, timedelta, timezone

from forex_bot.service import BotService


class Repository:
    def __init__(self, events, groups):
        self.events, self.groups = events, groups
        self.claimed_alerts, self.claimed_digests = set(), set()

    def active_events(self): return self.events
    def enabled_groups(self): return self.groups
    def claim_alert(self, row):
        key = (row["chat_id"], row["event_id"], row["minutes_before"], row["scheduled_for"])
        if key in self.claimed_alerts: return False
        self.claimed_alerts.add(key); return True
    def complete_alert(self, key, message_id): pass
    def fail_alert(self, key): pass
    def claim_digest(self, chat_id, kind, date):
        key = (str(chat_id), kind, date)
        if key in self.claimed_digests: return False
        self.claimed_digests.add(key); return True
    def complete_digest(self, *args): pass
    def fail_digest(self, *args): pass


class Telegram:
    def __init__(self): self.messages = []
    def send(self, chat_id, text): self.messages.append((chat_id, text)); return len(self.messages)


def event(moment, currency="USD", impact="High", speech=False):
    return {"id": "event-1", "title": "CPI", "currency": currency, "impact": impact, "is_speech": speech, "time_utc": moment.isoformat(), "status": "active"}


def group(**extra):
    value = {"chat_id": "100", "timezone": "Asia/Kolkata", "currencies": ["USD"], "impacts": ["High"], "include_speeches": False, "alert_minutes_before": [60, 15, 5, 0], "daily_digest_enabled": False, "weekly_digest_enabled": False}
    value.update(extra); return value


def test_alert_claim_prevents_duplicate_after_restart_window():
    now = datetime(2026, 1, 1, 10, tzinfo=timezone.utc)
    repository, telegram = Repository([event(now)], [group()]), Telegram()
    service = BotService(repository, telegram, now=lambda: now)
    assert service.check_deliveries() == 1
    assert service.check_deliveries() == 0
    assert len(telegram.messages) == 1


def test_speech_bypasses_impact_only_when_enabled():
    now = datetime(2026, 1, 1, 10, tzinfo=timezone.utc)
    item = event(now, impact="Low", speech=True)
    blocked = BotService(Repository([item], [group()]), Telegram(), now=lambda: now)
    allowed_telegram = Telegram()
    allowed = BotService(Repository([item], [group(include_speeches=True)]), allowed_telegram, now=lambda: now)
    assert blocked.check_deliveries() == 0
    assert allowed.check_deliveries() == 1


def test_daily_digest_is_local_timezone_filtered_and_deduplicated():
    now = datetime(2026, 1, 1, 5, 30, tzinfo=timezone.utc)  # 11:00 in Kolkata
    repository, telegram = Repository([event(now + timedelta(hours=1))], [group(alert_minutes_before=[], daily_digest_enabled=True, daily_digest_time="11:00")]), Telegram()
    service = BotService(repository, telegram, now=lambda: now)
    assert service.check_deliveries() == 1
    assert service.check_deliveries() == 0
    assert "Daily Economic Briefing" in telegram.messages[0][1]


def test_weekly_digest_is_sent_on_configured_local_day():
    now = datetime(2026, 1, 5, 5, 30, tzinfo=timezone.utc)  # Monday, 11:00 in Kolkata
    repository = Repository(
        [event(now + timedelta(days=2))],
        [group(alert_minutes_before=[], weekly_digest_enabled=True, weekly_digest_day=0, weekly_digest_time="11:00")],
    )
    telegram = Telegram()
    assert BotService(repository, telegram, now=lambda: now).check_deliveries() == 1
    assert "Weekly Economic Briefing" in telegram.messages[0][1]


def test_calendar_failure_does_not_write_existing_events(monkeypatch):
    class RefreshRepository:
        def __init__(self): self.saved = False
        def load_events(self): return {"baseline": {"id": "baseline"}}
        def save_events(self, events): self.saved = True

    repository = RefreshRepository()
    service = BotService(repository, Telegram())
    monkeypatch.setattr("forex_bot.service.fetch_prepared_events", lambda: (_ for _ in ()).throw(RuntimeError("429")))
    try:
        service.refresh_calendar()
    except RuntimeError:
        pass
    assert not repository.saved
