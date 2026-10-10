"""
SIMULATED result-alert smoke test.

Uses synthetic results and an in-memory repository. It sends one clearly
labelled simulated result message to the Telegram test group you specify.
It does not call the external result source or write to Supabase.

Keep this file out of Git commits; delete it after testing.
"""

import os
from datetime import datetime, timedelta, timezone

from forex_bot.service import BotService
from forex_bot.telegram import TelegramClient


class FakeResultSource:
    def __init__(self, source_events):
        self.source_events = source_events

    def fetch(self, start, end):
        return self.source_events


class FakeRepository:
    def __init__(self, events, group):
        self._events = events
        self._group = group
        self._claimed = set()
        self.sent_message_ids = []
        self.failed_keys = []

    def active_events(self):
        return self._events

    def enabled_groups(self):
        return [self._group]

    def claim_result_alert(self, row):
        key = (row["chat_id"], row["event_id"], row["release_time"])
        if key in self._claimed:
            return False
        self._claimed.add(key)
        return True

    def complete_result_alert(self, key, message_id):
        self.sent_message_ids.append(message_id)

    def fail_result_alert(self, key):
        self.failed_keys.append(key)


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        print(
            "TELEGRAM_BOT_TOKEN is not set. Stop this script and set it in "
            "PowerShell first; see the instructions provided with this file."
        )
        raise SystemExit(2)

    print("\n=== SIMULATED RESULT ALERT TEST ===")
    print("This sends synthetic data to a test group you choose.")
    print("It does NOT call the external results source or write to Supabase.")
    chat_id = input("TEST GROUP chat ID: ").strip()
    if not chat_id:
        print("No chat ID supplied; stopping.")
        raise SystemExit(2)

    now = datetime.now(timezone.utc)
    release_time = now - timedelta(minutes=2)
    release_iso = release_time.isoformat()

    examples = [
        {
            "id": "SIMULATED-CPI",
            "title": "SIMULATED TEST — CPI m/m",
            "actual": "0.4%",
            "forecast": "0.3%",
            "previous": "0.2%",
        },
        {
            "id": "SIMULATED-CORE-CPI",
            "title": "SIMULATED TEST — Core CPI m/m",
            "actual": "0.3%",
            "forecast": "0.2%",
            "previous": "0.2%",
        },
        {
            "id": "SIMULATED-RETAIL-SALES",
            "title": "SIMULATED TEST — Retail Sales",
            "actual": "0.1%",
            "forecast": "0.2%",
            "previous": "0.3%",
        },
    ]

    events = []
    source_events = []
    for item in examples:
        event = {
            "id": item["id"],
            "title": item["title"],
            "currency": "USD",
            "impact": "High",
            "is_speech": False,
            "time_utc": release_iso,
            "forecast": item["forecast"],
            "previous": item["previous"],
            "status": "active",
        }
        events.append(event)
        source_events.append(
            {
                "name": item["title"],
                "currency": "USD",
                "time": release_iso,
                "actual": item["actual"],
                "forecast": item["forecast"],
                "previous": item["previous"],
            }
        )

    group = {
        "chat_id": chat_id,
        "group_title": "SIMULATED TEST ONLY",
        "enabled": True,
        "timezone": "Asia/Kolkata",
        "currencies": ["USD"],
        "actual_alert_impacts": ["High"],
    }

    repository = FakeRepository(events, group)
    telegram = TelegramClient(token)
    service = BotService(
        repository,
        telegram,
        result_source=FakeResultSource(source_events),
        now=lambda: now,
    )

    delivered = service.check_results()

    if delivered and repository.sent_message_ids:
        print("\nSUCCESS: a simulated grouped result message was sent.")
        print(f"Telegram message ID: {repository.sent_message_ids[-1]}")
        print("Expected: one message containing three clearly labelled SIMULATED results.")
    else:
        print("\nThe simulated result was not delivered.")
        print(f"Service delivery count: {delivered}")
        print(f"Recorded send failures: {len(repository.failed_keys)}")
        print(
            "The real result matcher may reject the synthetic event structure; "
            "if so, use a dedicated Telegram formatting smoke test instead."
        )


if __name__ == "__main__":
    main()
