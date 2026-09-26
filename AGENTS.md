\# Forex Economic News Telegram Bot



\## Project Goal



Build one Python application that:



\- Downloads economic calendar data.

\- Stores events in Supabase.

\- Sends alerts to Telegram.

\- Supports multiple Telegram groups.

\- Uses different settings for each Telegram group.

\- Sends daily and weekly economic-news briefings.

\- Eventually runs in the cloud so the user's PC does not need to stay on.



\## Architecture



Use:



One Python application

\+ one Telegram bot

\+ one Supabase database

\+ multiple Telegram groups.



Do NOT create a separate Python application for each group.



Group-specific behavior must come from Supabase.



\## Current Working Components



The existing repository already contains working code for:



\- Calendar retrieval

\- Currency and impact filtering

\- Speech detection

\- Persistent event identity

\- Duplicate-event handling

\- Reschedule detection

\- Supabase storage

\- Telegram messaging

\- Configurable group settings

\- Alert timing



Inspect the existing implementation before replacing it.



Do not unnecessarily rewrite working logic.



\## Event Filtering



Supported currencies:



USD

EUR

GBP

JPY

CAD

AUD

NZD

CHF



Normal economic events:

\- High impact

\- Medium impact



Speeches:

\- Include when enabled for the Telegram group.

\- Speech events may be included regardless of their calendar impact label.



\## Event Identity



Event identity is important.



The system must:



\- Preserve duplicate events with the same title.

\- Detect event rescheduling.

\- Detect impact changes.

\- Detect forecast changes.

\- Detect previous-value changes.

\- Preserve persistent event IDs.

\- Avoid falsely treating duplicate events as the same event.

\- Never overwrite valid stored events because of a failed calendar request.



The existing event identity implementation has already passed tests for:



\- Rescheduling

\- Duplicate events

\- New events



Preserve this behavior unless an actual defect is demonstrated.



\## Supabase



Use Supabase as the persistent source of truth.



Current tables include:



\### economic\_events



Stores calendar events.



\### telegram\_group\_settings



Stores per-group configuration.



\### alert\_log



Stores alert history.



Historical alert data should NOT be deleted after each event.



Approximately 60 days of history should be retained.



\## Telegram Group Settings



Each Telegram group can independently configure:



\- chat\_id

\- group\_title

\- timezone

\- currencies

\- impact levels

\- speech inclusion

\- alert intervals

\- daily digest enabled

\- daily digest time

\- weekly digest enabled

\- weekly digest day

\- weekly digest time

\- enabled/disabled state



Use IANA timezone names.



Examples:



Asia/Kolkata

America/New\_York



Do not hardcode UTC offsets.



\## Event Alerts



Alerts must be configurable per group.



Supported examples include:



\- 60 minutes before

\- 15 minutes before

\- 5 minutes before

\- at release

\- post-news alerts



Prevent duplicate alerts.



The same alert must never be sent twice for the same:



group + event + alert schedule.



Use alert\_log for deduplication.



\## Daily Briefing



Each group may receive a daily briefing.



The daily briefing must:



\- Use the group's timezone.

\- Use the group's currency filter.

\- Use the group's impact filter.

\- Respect speech settings.

\- Show only that day's events.

\- Sort events chronologically.



\## Weekly Briefing



Each group may receive a weekly briefing.



The weekly briefing must:



\- Use the group's timezone.

\- Use the group's filters.

\- Show upcoming events for the week.

\- Group events by calendar day.

\- Sort events chronologically.



The schedule must be configurable per group.



\## Reliability



Handle safely:



\- HTTP 429 from calendar source

\- Calendar timeout

\- Network failure

\- Malformed calendar event

\- Empty calendar response

\- Supabase failure

\- Telegram API failure



A failed or empty calendar request must NEVER wipe valid existing events.



Do not repeatedly poll the calendar source unnecessarily.



Calendar refreshing and alert checking should be separate operations.



\## Secrets



Never hardcode:



\- Telegram bot token

\- Supabase secret key



Use environment variables.



Never commit `.env`.



Never expose production credentials.



\## Deployment



Eventually deploy the worker to a cloud environment so the user's PC can be turned off.



Supabase remains persistent storage.



\## Data Retention



Keep approximately 60 days of:



\- economic event history

\- Telegram alert history

\- digest history if stored



Use scheduled database cleanup.



\## Development Rules



Before making changes:



1\. Inspect the existing repository.

2\. Understand the current architecture.

3\. Identify duplicate or obsolete files.

4\. Run safe existing tests.



When making changes:



\- Make incremental changes.

\- Preserve working behavior.

\- Add tests for important logic.

\- Run tests after changes.

\- Do not modify production data unnecessarily.

\- Do not change Supabase schema without explaining the reason.

\- Do not expose secrets.



\## Important Current State



The existing local system has already successfully demonstrated:



\- 43 relevant calendar events stored in Supabase.

\- Supabase refresh with 43 active events.

\- Telegram messaging.

\- Group-specific settings.

\- Alert-engine timing tests.

\- Duplicate-event tests.

\- Reschedule tests.

\- End-to-end Telegram alert test.



Treat this as the working baseline.

