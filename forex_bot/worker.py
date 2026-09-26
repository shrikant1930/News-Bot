import argparse
import logging
import time

from forex_bot.repository import SupabaseRepository
from forex_bot.service import BotService
from forex_bot.settings import load_settings
from forex_bot.telegram import TelegramClient


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = load_settings()
    service = BotService(SupabaseRepository(settings.supabase_url, settings.supabase_key), TelegramClient(settings.telegram_token))
    last_refresh = 0.0
    while True:
        now = time.monotonic()
        if now - last_refresh >= settings.calendar_refresh_seconds or last_refresh == 0:
            try:
                logging.info("Calendar refresh result: %s", service.refresh_calendar())
                last_refresh = now
            except Exception:
                logging.exception("Calendar refresh failed; stored events were not modified")
        try:
            logging.info("Deliveries processed: %s", service.check_deliveries(args.dry_run))
        except Exception:
            logging.exception("Delivery check failed")
        if args.once:
            return
        time.sleep(settings.check_interval_seconds)


if __name__ == "__main__":
    main()
