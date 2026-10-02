from collections import defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from forex_bot.calendar import fetch_prepared_events, reconcile
from forex_bot.filters import (
    event_matches_group,
    event_matches_alert_group,
    local_time,
    normalized_minutes,
    parse_utc,
)
from forex_bot.messages import alert_message, digest_message


ALERT_EARLY_SECONDS = 15
ALERT_LATE_SECONDS = 90
DIGEST_GRACE_SECONDS = 15 * 60
ALERT_CLAIM_STALE_SECONDS = 2 * 60
ALERT_RECOVERY_SECONDS = 15 * 60


class BotService:
    def __init__(self, repository, telegram, now=lambda: datetime.now(timezone.utc)):
        self.repository = repository
        self.telegram = telegram
        self.now = now

    def refresh_calendar(self) -> dict[str, int]:
        # Fetch and validate before any database write: a bad response cannot erase 43+ active records.
        prepared = fetch_prepared_events()
        current, created, changed, removed = reconcile(self.repository.load_events(), prepared)
        self.repository.save_events(current)
        return {"active": sum(event.get("status") == "active" for event in current.values()), "created": len(created), "changed": len(changed), "removed": len(removed)}

    def check_deliveries(self, dry_run: bool = False) -> int:
        now = self.now()
        delivered = 0
        events = self.repository.active_events()
        for group in self.repository.enabled_groups():
            try:
                ZoneInfo(group["timezone"])
            except (KeyError, ValueError):
                continue
            matching = [
                event
                for event in events
                if event_matches_group(event, group)
            ]

            alert_matching = [
                event
                for event in events
                if event_matches_alert_group(event, group)
            ]

            alert_groups = defaultdict(list)

            for event in alert_matching:
                release_time = parse_utc(event["time_utc"])

                for minutes in normalized_minutes(group):
                    scheduled = release_time - timedelta(minutes=minutes)
                    due = _due(now, scheduled)
                    recovery = _recovery_window(now, scheduled)

                    if not due and not recovery:
                        continue

                    # Group only events with the exact same release date/time
                    # and the same alert timing.
                    key = (release_time, minutes)

                    alert_groups[key].append(
                        {
                            "event": event,
                            "scheduled": scheduled,
                            "recovery": not due,
                        }
                    )

            for entries in alert_groups.values():
                if self._deliver_alert_group(entries, group, dry_run):
                    delivered += 1

            delivered += self._deliver_digests(
                matching,
                group,
                now,
                dry_run,
            )
        return delivered

    def _deliver_alert(self, event, group, minutes, scheduled, dry_run, recovery=False):
        row = {"chat_id": str(group["chat_id"]), "event_id": event["id"], "alert_type": _alert_type(minutes), "minutes_before": minutes, "scheduled_for": scheduled.isoformat(), "status": "pending"}
        if dry_run:
            return True
        if not self.repository.claim_alert(row, recovery=recovery):
            return False
        key = {field: row[field] for field in ("chat_id", "event_id", "minutes_before", "scheduled_for")}
        try:
            message_id = self.telegram.send(group["chat_id"], alert_message(event, group, minutes))
            self.repository.complete_alert(key, message_id)
            return True
        except Exception:
            self.repository.fail_alert(key)
            return False

    def _deliver_alert_group(self, entries, group, dry_run=False):
        if not entries:
            return False

        minutes = entries[0]["scheduled"]
        release_time = parse_utc(entries[0]["event"]["time_utc"])
        minutes_before = int((release_time - minutes).total_seconds() / 60)

        claimed = []

        for entry in entries:
            event = entry["event"]
            scheduled = entry["scheduled"]

            row = {
                "chat_id": str(group["chat_id"]),
                "event_id": event["id"],
                "alert_type": _alert_type(minutes_before),
                "minutes_before": minutes_before,
                "scheduled_for": scheduled.isoformat(),
                "status": "pending",
            }

            if dry_run:
                claimed.append((event, row))
                continue

            if self.repository.claim_alert(
                row,
                recovery=entry["recovery"],
            ):
                claimed.append((event, row))

        if not claimed:
            return False

        events = [event for event, _ in claimed]

        try:
            message_id = self.telegram.send(
                group["chat_id"],
                alert_message(events, group, minutes_before),
            )

            if not dry_run:
                for _, row in claimed:
                    key = {
                        field: row[field]
                        for field in (
                            "chat_id",
                            "event_id",
                            "minutes_before",
                            "scheduled_for",
                        )
                    }
                    self.repository.complete_alert(key, message_id)

            return True

        except Exception:
            if not dry_run:
                for _, row in claimed:
                    key = {
                        field: row[field]
                        for field in (
                            "chat_id",
                            "event_id",
                            "minutes_before",
                            "scheduled_for",
                        )
                    }
                    self.repository.fail_alert(key)

            return False

    def _deliver_digests(self, events, group, now, dry_run):
        local_now = now.astimezone(ZoneInfo(group["timezone"]))
        count = 0
        daily_time = group.get("daily_digest_time")
        if group.get("daily_digest_enabled") and _time_due(local_now, daily_time):
            day_events = [event for event in events if local_time(event, group["timezone"]).date() == local_now.date()]
            count += self._deliver_digest(group, "daily", local_now.date(), day_events, dry_run)
        weekly_time = group.get("weekly_digest_time")
        # Python datetime.weekday(): Monday is 0 and Sunday is 6.
        if group.get("weekly_digest_enabled") and local_now.weekday() == int(group.get("weekly_digest_day", 0)) and _time_due(local_now, weekly_time):
            end = local_now.date() + timedelta(days=7)
            week_events = [event for event in events if local_now.date() <= local_time(event, group["timezone"]).date() < end]
            count += self._deliver_digest(group, "weekly", local_now.date(), week_events, dry_run)
        return count

    def _deliver_digest(self, group, kind, digest_date, events, dry_run):
        if dry_run:
            return 1
        if not self.repository.claim_digest(group["chat_id"], kind, digest_date.isoformat()):
            return 0
        try:
            message_id = self.telegram.send(group["chat_id"], digest_message(events, group, kind, digest_date))
            self.repository.complete_digest(group["chat_id"], kind, digest_date.isoformat(), message_id)
            return 1
        except Exception:
            self.repository.fail_digest(group["chat_id"], kind, digest_date.isoformat())
            return 0


def _due(now, scheduled):
    seconds = (scheduled - now).total_seconds()
    return -ALERT_LATE_SECONDS <= seconds <= ALERT_EARLY_SECONDS


def _recovery_window(now, scheduled):
    elapsed = (now - scheduled).total_seconds()
    return ALERT_CLAIM_STALE_SECONDS <= elapsed <= ALERT_RECOVERY_SECONDS


def _alert_type(minutes):
    return "release" if minutes == 0 else (f"before_{minutes}m" if minutes > 0 else f"after_{abs(minutes)}m")


def _time_due(local_now, configured):
    if not isinstance(configured, str):
        return False
    try:
        scheduled = datetime.strptime(configured, "%H:%M:%S").time() if configured.count(":") == 2 else datetime.strptime(configured, "%H:%M").time()
    except ValueError:
        return False
    scheduled_at = local_now.replace(hour=scheduled.hour, minute=scheduled.minute, second=scheduled.second, microsecond=0)
    elapsed = (local_now - scheduled_at).total_seconds()
    return 0 <= elapsed <= DIGEST_GRACE_SECONDS
