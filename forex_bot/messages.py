from datetime import date
from itertools import groupby

from forex_bot.filters import local_time


def alert_message(event: dict, group: dict, minutes_before: int) -> str:
    if minutes_before > 0:
        headline = f"NEWS IN {minutes_before} MINUTES"
    elif minutes_before == 0:
        headline = "NEWS NOW"
    else:
        headline = f"{abs(minutes_before)} MINUTES AFTER NEWS"
    moment = local_time(event, group["timezone"])
    lines = [headline, "", f"{event.get('impact', '').upper()} | {event['currency']}", event["title"], "", moment.strftime("%A, %d %B %Y %I:%M %p")]
    if event.get("forecast"):
        lines.append(f"Forecast: {event['forecast']}")
    if event.get("previous"):
        lines.append(f"Previous: {event['previous']}")
    if event.get("is_speech"):
        lines.append("Speech event")
    return "\n".join(lines)


def digest_message(events: list[dict], group: dict, kind: str, digest_date: date) -> str:
    title = "Daily Economic Briefing" if kind == "daily" else "Weekly Economic Briefing"
    if not events:
        return f"{title}\n\nNo matching events scheduled."
    ordered = sorted(events, key=lambda event: local_time(event, group["timezone"]))
    lines = [title, ""]
    if kind == "daily":
        lines.append(digest_date.strftime("%A, %d %B %Y"))
        lines.append("")
        for event in ordered:
            lines.append(_event_line(event, group))
    else:
        for day, day_events in groupby(ordered, key=lambda event: local_time(event, group["timezone"]).date()):
            lines.extend([day.strftime("%A, %d %B"), *[_event_line(event, group) for event in day_events], ""])
    return "\n".join(lines).rstrip()


def _event_line(event: dict, group: dict) -> str:
    moment = local_time(event, group["timezone"])
    return f"{moment.strftime('%I:%M %p')} | {event['currency']} | {event.get('impact', '')} | {event['title']}"
