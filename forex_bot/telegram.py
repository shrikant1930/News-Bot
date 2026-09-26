from typing import Any

import requests


class TelegramClient:
    def __init__(self, token: str, session: requests.Session | None = None):
        self._token = token
        self._session = session or requests.Session()

    def send(self, chat_id: str | int, text: str) -> int:
        response = self._session.post(
            f"https://api.telegram.org/bot{self._token}/sendMessage",
            json={"chat_id": chat_id, "text": text}, timeout=15,
        )
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        if not payload.get("ok"):
            raise RuntimeError("Telegram rejected the message")
        return int(payload["result"]["message_id"])
