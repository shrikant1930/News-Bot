from datetime import datetime, timedelta, timezone
from typing import Any

from supabase import Client, create_client


class SupabaseRepository:
    def __init__(self, url: str, key: str):
        self.client: Client = create_client(url, key)

    def load_events(self) -> dict[str, dict[str, Any]]:
        rows = self.client.table("economic_events").select("*").execute().data or []
        return {row["id"]: row for row in rows}

    def save_events(self, events: dict[str, dict[str, Any]]) -> None:
        if events:
            self.client.table("economic_events").upsert(list(events.values()), on_conflict="id").execute()

    def active_events(self) -> list[dict[str, Any]]:
        return self.client.table("economic_events").select("*").eq("status", "active").order("time_utc").execute().data or []

    def enabled_groups(self) -> list[dict[str, Any]]:
        return self.client.table("telegram_group_settings").select("*").eq("enabled", True).execute().data or []

    def claim_alert(self, row: dict[str, Any], recovery: bool = False) -> bool:
        """Claim before delivery; unique index makes the claim restart-safe.

        Fresh pending deliveries are never retried. A stale claim can be
        reclaimed atomically after a worker crash or confirmed send failure.
        """
        key = _alert_key(row)
        claimed_at = _utc_now()
        pending_row = {**row, "status": "pending", "claimed_at": claimed_at.isoformat()}
        if not recovery:
            try:
                self.client.table("alert_log").insert(pending_row).execute()
                return True
            except Exception:
                pass
        try:
            rows = self.client.table("alert_log").select("status,claimed_at").match(key).limit(1).execute().data or []
            if not rows or not _stale_claim(rows[0], claimed_at):
                return False
            previous = rows[0]
            query = self.client.table("alert_log").update({"status": "pending", "claimed_at": claimed_at.isoformat()}).match(key).eq("status", previous["status"])
            if previous.get("claimed_at") is not None:
                query = query.eq("claimed_at", previous["claimed_at"])
            updated = query.select("status").execute().data or []
            return bool(updated)
        except Exception:
            return False

    def complete_alert(self, key: dict[str, Any], message_id: int) -> None:
        self.client.table("alert_log").update({"status": "sent", "sent_at": _utc_iso(), "telegram_message_id": message_id}).match(key).execute()

    def fail_alert(self, key: dict[str, Any]) -> None:
        self.client.table("alert_log").update({"status": "failed"}).match(key).execute()

    def claim_digest(self, chat_id: str | int, digest_type: str, digest_date: str) -> bool:
        row = {"chat_id": str(chat_id), "digest_type": digest_type, "digest_date": digest_date}
        try:
            self.client.table("digest_log").insert(row).execute()
            return True
        except Exception:
            return False

    def complete_digest(self, chat_id: str | int, digest_type: str, digest_date: str, message_id: int) -> None:
        self.client.table("digest_log").update({"status": "sent", "sent_at": _utc_iso(), "telegram_message_id": message_id}).match({"chat_id": str(chat_id), "digest_type": digest_type, "digest_date": digest_date}).execute()

    def fail_digest(self, chat_id: str | int, digest_type: str, digest_date: str) -> None:
        self.client.table("digest_log").update({"status": "failed"}).match({"chat_id": str(chat_id), "digest_type": digest_type, "digest_date": digest_date}).execute()


def _utc_iso() -> str:
    return _utc_now().isoformat()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _alert_key(row: dict[str, Any]) -> dict[str, Any]:
    return {field: row[field] for field in ("chat_id", "event_id", "minutes_before", "scheduled_for")}


def _stale_claim(row: dict[str, Any], now: datetime) -> bool:
    if row.get("status") not in {"pending", "failed"}:
        return False
    value = row.get("claimed_at")
    if not value:
        return True
    try:
        claimed_at = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return True
    if claimed_at.tzinfo is None:
        claimed_at = claimed_at.replace(tzinfo=timezone.utc)
    return claimed_at.astimezone(timezone.utc) <= now - timedelta(minutes=2)

