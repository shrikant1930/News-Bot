# Forex Economic News Telegram Bot

One Python worker refreshes the economic calendar, stores its durable event identity in Supabase, and delivers group-specific Telegram alerts and briefings.

## Setup

1. Create a virtual environment and install dependencies: `py -m venv .venv` then `.\.venv\Scripts\python -m pip install -r requirements.txt`.
2. Copy `.env.example` to `.env` and supply the deployment secrets there.
3. Apply `schema.sql` in the Supabase SQL editor. It adds durable alert/digest deduplication and retention indexes; it does not alter or delete existing event data.
4. Configure `telegram_group_settings` rows. Required fields are `chat_id`, `timezone`, `currencies`, `impacts`, `include_speeches`, `alert_minutes_before`, and `enabled`. Currency codes are case-insensitive but must be one of USD, EUR, GBP, JPY, CAD, AUD, NZD, or CHF. Digest fields are `daily_digest_enabled`, `daily_digest_time` (`HH:MM` or `HH:MM:SS`), `weekly_digest_enabled`, `weekly_digest_day` (`0=Monday` through `6=Sunday`), and `weekly_digest_time` (`HH:MM` or `HH:MM:SS`). Set `actual_alert_impacts` to any combination of `High`, `Medium`, and `Low` to enable post-release result alerts for that group.

## Run

`python -m forex_bot.worker` starts the worker. Use `python -m forex_bot.worker --once --dry-run` to exercise selection and scheduling without Telegram sends.

`python -m forex_bot.worker --results-only` runs only the lightweight post-release result checker. It uses one narrow result-source request only when active events are one to sixty minutes past their release time.

Calendar refresh defaults to every 30 minutes; alert/digest evaluation defaults to every 30 seconds. Set `CALENDAR_REFRESH_SECONDS` and `CHECK_INTERVAL_SECONDS` for deployment. Run one worker instance unless an external leader lock is added.

Fresh alert claims are not retried, which avoids duplicate delivery after an ambiguous Telegram timeout. Stale `pending` or `failed` alert claims may be recovered after two minutes for up to 15 minutes after their schedule, covering worker crashes while limiting late retries.

## Retention

Enable the supplied `cleanup_forex_news_retention` function as a daily Supabase cron job. Historical event and delivery records are retained for approximately 60 days.
