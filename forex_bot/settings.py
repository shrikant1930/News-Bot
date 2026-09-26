import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    supabase_url: str
    supabase_key: str
    telegram_token: str
    calendar_refresh_seconds: int = 1800
    check_interval_seconds: int = 30


def load_settings() -> Settings:
    load_dotenv()
    values = {
        "supabase_url": os.getenv("SUPABASE_URL", ""),
        "supabase_key": os.getenv("SUPABASE_SECRET_KEY", ""),
        "telegram_token": os.getenv("TELEGRAM_BOT_TOKEN", ""),
    }
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise RuntimeError("Missing required environment configuration: " + ", ".join(missing))
    return Settings(
        **values,
        calendar_refresh_seconds=int(os.getenv("CALENDAR_REFRESH_SECONDS", "1800")),
        check_interval_seconds=int(os.getenv("CHECK_INTERVAL_SECONDS", "30")),
    )
