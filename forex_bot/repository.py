from datetime import datetime, timezone
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

    def claim_alert(self, row: dict[str, Any]) -> bool:
        """Claim before delivery; unique index makes the claim restart-safe.

        A failed send remains claimed because Telegram has no idempotency key.
        Retrying a timed-out request could deliver the same alert twice.
        """
        try:
            self.client.table("alert_log").insert(row).execute()
            return True
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
    return datetime.now(timezone.utc).isoformat()

