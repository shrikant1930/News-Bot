from datetime import datetime, timedelta, timezone

from forex_bot.filters import event_matches_group
from forex_bot.repository import _stale_claim
from forex_bot.service import BotService, _time_due


class Repository:
    def __init__(self, events, groups):
        self.events, self.groups = events, groups
        self.claimed_alerts, self.claimed_digests = set(), set()

    def active_events(self): return self.events
    def enabled_groups(self): return self.groups
    def claim_alert(self, row, recovery=False):
        key = (row["chat_id"], row["event_id"], row["minutes_before"], row["scheduled_for"])
        if recovery:
            return False
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
    value = {"chat_id": "100", "timezone": "Asia/Kolkata", "currencies": ["USD"], "impacts": ["High"], "alert_impacts": ["High"], "include_speeches": False, "alert_minutes_before": [60, 15, 5, 0], "daily_digest_enabled": False, "weekly_digest_enabled": False}
    value.update(extra); return value


def test_alert_claim_prevents_duplicate_after_restart_window():
    now = datetime(2026, 1, 1, 10, tzinfo=timezone.utc)
    repository, telegram = Repository([event(now)], [group()]), Telegram()
    service = BotService(repository, telegram, now=lambda: now)
    assert service.check_deliveries() == 1
    assert service.check_deliveries() == 0
    assert len(telegram.messages) == 1


def test_speech_alerts_respect_alert_impacts():
    now = datetime(2026, 1, 1, 10, tzinfo=timezone.utc)

    low_speech = event(now, impact="Low", speech=True)
    high_speech = event(now, impact="High", speech=True)

    blocked = BotService(
        Repository([low_speech], [group(include_speeches=True, alert_impacts=["High"])]),
        Telegram(),
        now=lambda: now,
    )
    assert blocked.check_deliveries() == 0

    allowed_telegram = Telegram()
    allowed = BotService(
        Repository([high_speech], [group(include_speeches=True, alert_impacts=["High"])]),
        allowed_telegram,
        now=lambda: now,
    )
    assert allowed.check_deliveries() == 1


def test_currency_filters_are_case_insensitive_and_reject_unsupported_codes():
    assert event_matches_group(event(datetime.now(timezone.utc), currency="usd"), group(currencies=["Usd", "eur", "not-a-currency"]))
    assert not event_matches_group(event(datetime.now(timezone.utc), currency="XXX"), group(currencies=["xxx", "USD"]))


def test_daily_digest_is_local_timezone_filtered_and_deduplicated():
    now = datetime(2026, 1, 1, 5, 30, tzinfo=timezone.utc)  # 11:00 in Kolkata
    repository, telegram = Repository([event(now + timedelta(hours=1))], [group(alert_minutes_before=[], daily_digest_enabled=True, daily_digest_time="11:00")]), Telegram()
    service = BotService(repository, telegram, now=lambda: now)
    assert service.check_deliveries() == 1
    assert service.check_deliveries() == 0
    assert "Daily Economic Briefing" in telegram.messages[0][1]


def test_daily_digest_accepts_seconds_and_startup_grace_period():
    now = datetime(2026, 1, 1, 5, 32, 15, tzinfo=timezone.utc)  # 11:02:15 in Kolkata
    repository = Repository(
        [event(now + timedelta(hours=1))],
        [group(alert_minutes_before=[], daily_digest_enabled=True, daily_digest_time="11:00:00")],
    )
    telegram = Telegram()
    assert BotService(repository, telegram, now=lambda: now).check_deliveries() == 1
    assert "Daily Economic Briefing" in telegram.messages[0][1]
    assert _time_due(now.astimezone().replace(hour=11, minute=14, second=59), "11:00:00")
    assert not _time_due(now.astimezone().replace(hour=11, minute=15, second=1), "11:00:00")


def test_weekly_digest_is_sent_on_configured_local_day():
    now = datetime(2026, 1, 4, 5, 30, tzinfo=timezone.utc)  # Sunday, 11:00 in Kolkata
    repository = Repository(
        [event(now + timedelta(days=2))],
        [group(alert_minutes_before=[], weekly_digest_enabled=True, weekly_digest_day=6, weekly_digest_time="11:00:00")],
    )
    telegram = Telegram()
    assert BotService(repository, telegram, now=lambda: now).check_deliveries() == 1
    assert "Weekly Economic Briefing" in telegram.messages[0][1]


def test_stale_claim_is_recovered_within_recovery_window():
    class RecoveryRepository(Repository):
        def __init__(self, events, groups):
            super().__init__(events, groups)
            self.recovery_attempts = []

        def claim_alert(self, row, recovery=False):
            self.recovery_attempts.append(recovery)
            return recovery

    now = datetime(2026, 1, 1, 10, 3, tzinfo=timezone.utc)
    repository = RecoveryRepository(
        [event(now - timedelta(minutes=3))],
        [group(alert_minutes_before=[0])],
    )
    telegram = Telegram()

    service = BotService(repository, telegram, now=lambda: now)

    assert service.check_deliveries() == 1
    assert repository.recovery_attempts == [True]
    assert len(telegram.messages) == 1


def test_stale_claim_requires_pending_or_failed_status_and_two_minutes():
    now = datetime(2026, 1, 1, 10, tzinfo=timezone.utc)
    assert not _stale_claim({"status": "sent", "claimed_at": (now - timedelta(days=1)).isoformat()}, now)
    assert not _stale_claim({"status": "pending", "claimed_at": (now - timedelta(minutes=1)).isoformat()}, now)
    assert _stale_claim({"status": "pending", "claimed_at": (now - timedelta(minutes=2)).isoformat()}, now)
    assert _stale_claim({"status": "failed", "claimed_at": None}, now)


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
