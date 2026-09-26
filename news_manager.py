import requests
import json
import uuid
import re
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta


# ============================================================
# SETTINGS
# ============================================================

CALENDAR_URL = (
    "https://nfs.faireconomy.media/"
    "ff_calendar_thisweek.json"
)

CURRENCIES = {
    "USD", "EUR", "GBP", "JPY",
    "CAD", "AUD", "NZD", "CHF"
}

IMPACTS = {
    "High",
    "Medium",
}

SPEECH_KEYWORDS = {
    "speaks",
    "speech",
    "testifies",
    "testimony",
    "remarks",
    "address",
    "press conference",
}

STORAGE_FILE = Path("news_events.json")

# Maximum distance used when trying to identify
# a rescheduled event across different dates.
MAX_RESCHEDULE_HOURS = 120


# ============================================================
# CALENDAR DOWNLOAD
# ============================================================

def get_calendar():

    headers = {
        "User-Agent": (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/142.0.0.0 Safari/537.36"
        )
    }

    response = requests.get(
        CALENDAR_URL,
        headers=headers,
        timeout=15
    )

    if response.status_code == 429:

        raise RuntimeError(
            "Calendar feed is rate-limiting us "
            "(HTTP 429)."
        )

    response.raise_for_status()

    data = response.json()

    # An empty calendar response is NEVER treated
    # as a legitimate replacement for our database.
    if not data:

        raise RuntimeError(
            "Calendar feed returned 0 events."
        )

    return data


# ============================================================
# TEXT / IDENTITY HELPERS
# ============================================================

def normalize_title(title):

    """
    Normalize title for matching.

    This keeps the actual title untouched while
    creating a comparison-friendly version.
    """

    title = str(title).strip().lower()

    title = re.sub(
        r"\s+",
        " ",
        title
    )

    return title


def make_match_key(
    currency,
    title
):

    return (
        f"{currency.strip().upper()}|"
        f"{normalize_title(title)}"
    )


def make_new_id():

    """
    Persistent ID for a genuinely new event.

    Once stored, this ID is never regenerated
    unless the event is genuinely unmatched.
    """

    return uuid.uuid4().hex


# ============================================================
# EVENT HELPERS
# ============================================================

def is_speech(title):

    title_lower = title.lower()

    return any(
        keyword in title_lower
        for keyword in SPEECH_KEYWORDS
    )


def parse_event_time(date_string):

    event_time = datetime.fromisoformat(
        date_string
    )

    return event_time.astimezone(
        timezone.utc
    )


def prepare_event(raw_event):

    title = raw_event.get(
        "title",
        ""
    ).strip()

    currency = raw_event.get(
        "country",
        ""
    ).strip().upper()

    impact = raw_event.get(
        "impact",
        ""
    ).strip()

    date_string = raw_event.get(
        "date",
        ""
    )

    event_time_utc = parse_event_time(
        date_string
    )

    return {

        "title": title,

        "currency": currency,

        "impact": impact,

        "time_utc":
            event_time_utc.isoformat(),

        "forecast":
            raw_event.get(
                "forecast",
                ""
            ),

        "previous":
            raw_event.get(
                "previous",
                ""
            ),

        "is_speech":
            is_speech(title),

        # Internal matching fields.
        "_datetime":
            event_time_utc,

        "_date":
            event_time_utc.date().isoformat(),

        "_match_key":
            make_match_key(
                currency,
                title
            ),
    }


def should_include(event):

    currency = event.get(
        "country",
        ""
    ).strip().upper()

    impact = event.get(
        "impact",
        ""
    ).strip()

    title = event.get(
        "title",
        ""
    )

    if currency not in CURRENCIES:
        return False

    # Speeches always pass.
    if is_speech(title):
        return True

    return impact in IMPACTS


# ============================================================
# STORAGE
# ============================================================

def load_existing():

    if not STORAGE_FILE.exists():
        return {}

    try:

        with open(
            STORAGE_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            data = json.load(file)

        if isinstance(data, dict):
            return data

        return {}

    except Exception:

        return {}


def save_events(events):

    temporary_file = Path(
        "news_events.tmp"
    )

    with open(
        temporary_file,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            events,
            file,
            indent=2,
            ensure_ascii=False
        )

    temporary_file.replace(
        STORAGE_FILE
    )


# ============================================================
# STORED EVENT CONVERSION
# ============================================================

def stored_to_prepared(event):

    event_time = datetime.fromisoformat(
        event["time_utc"]
    ).astimezone(
        timezone.utc
    )

    return {

        "title":
            event.get(
                "title",
                ""
            ),

        "currency":
            event.get(
                "currency",
                ""
            ).upper(),

        "impact":
            event.get(
                "impact",
                ""
            ),

        "time_utc":
            event_time.isoformat(),

        "forecast":
            event.get(
                "forecast",
                ""
            ),

        "previous":
            event.get(
                "previous",
                ""
            ),

        "is_speech":
            bool(
                event.get(
                    "is_speech",
                    False
                )
            ),

        "_datetime":
            event_time,

        "_date":
            event_time.date().isoformat(),

        "_match_key":
            event.get(
                "match_key"
            )
            or make_match_key(
                event.get(
                    "currency",
                    ""
                ),
                event.get(
                    "title",
                    ""
                )
            ),
    }


def clean_event_for_storage(
    prepared,
    event_id,
    old_event=None
):

    now = datetime.now(
        timezone.utc
    ).isoformat()

    result = {

        "id":
            event_id,

        "match_key":
            prepared["_match_key"],

        "title":
            prepared["title"],

        "currency":
            prepared["currency"],

        "impact":
            prepared["impact"],

        "time_utc":
            prepared["time_utc"],

        "forecast":
            prepared["forecast"],

        "previous":
            prepared["previous"],

        "is_speech":
            prepared["is_speech"],

        "status":
            "active",

        "updated_at":
            now,
    }

    if old_event:

        result["created_at"] = old_event.get(
            "created_at",
            now
        )

    else:

        result["created_at"] = now

    return result


# ============================================================
# EVENT MATCHING
# ============================================================

def find_best_match(
    new_event,
    existing,
    used_ids,
    same_date_only
):

    best_id = None
    best_difference = None

    new_time = new_event[
        "_datetime"
    ]

    new_match_key = new_event[
        "_match_key"
    ]

    for event_id, old_event in existing.items():

        if event_id in used_ids:
            continue

        old_match_key = (
            old_event.get(
                "match_key"
            )
            or make_match_key(
                old_event.get(
                    "currency",
                    ""
                ),
                old_event.get(
                    "title",
                    ""
                )
            )
        )

        if old_match_key != new_match_key:
            continue

        try:

            old_time = datetime.fromisoformat(
                old_event[
                    "time_utc"
                ]
            ).astimezone(
                timezone.utc
            )

        except Exception:

            continue

        if same_date_only:

            if (
                old_time.date()
                != new_time.date()
            ):

                continue

        difference = abs(
            (
                new_time
                - old_time
            ).total_seconds()
        )

        if not same_date_only:

            if (
                difference
                > MAX_RESCHEDULE_HOURS * 3600
            ):

                continue

        if (
            best_difference is None
            or difference < best_difference
        ):

            best_difference = difference
            best_id = event_id

    return best_id


def detect_changes(
    old,
    new
):

    changes = []

    if old.get(
        "time_utc"
    ) != new.get(
        "time_utc"
    ):

        changes.append(
            "time changed"
        )

    if old.get(
        "impact"
    ) != new.get(
        "impact"
    ):

        changes.append(
            "impact changed"
        )

    if old.get(
        "forecast"
    ) != new.get(
        "forecast"
    ):

        changes.append(
            "forecast changed"
        )

    if old.get(
        "previous"
    ) != new.get(
        "previous"
    ):

        changes.append(
            "previous changed"
        )

    return changes


# ============================================================
# RECONCILIATION
# ============================================================

def reconcile_events(
    existing,
    prepared_events
):

    used_ids = set()

    assignments = {}

    # Sort by time so duplicate events are handled
    # in chronological order.
    prepared_sorted = sorted(
        prepared_events,
        key=lambda event:
            event["_datetime"]
    )

    # --------------------------------------------------------
    # PASS 1
    #
    # Match same currency/title AND same date.
    # --------------------------------------------------------

    for index, new_event in enumerate(
        prepared_sorted
    ):

        event_id = find_best_match(
            new_event,
            existing,
            used_ids,
            same_date_only=True
        )

        if event_id:

            assignments[index] = event_id
            used_ids.add(event_id)


    # --------------------------------------------------------
    # PASS 2
    #
    # Match rescheduled events across dates.
    # --------------------------------------------------------

    for index, new_event in enumerate(
        prepared_sorted
    ):

        if index in assignments:
            continue

        event_id = find_best_match(
            new_event,
            existing,
            used_ids,
            same_date_only=False
        )

        if event_id:

            assignments[index] = event_id
            used_ids.add(event_id)


    # --------------------------------------------------------
    # BUILD CURRENT DATA
    # --------------------------------------------------------

    current = {}

    new_events = []

    changed_events = []


    for index, new_event in enumerate(
        prepared_sorted
    ):

        if index in assignments:

            event_id = assignments[
                index
            ]

            old_event = existing[
                event_id
            ]

            stored_event = (
                clean_event_for_storage(
                    new_event,
                    event_id,
                    old_event
                )
            )

            # Restore active status if it was previously
            # missing from the feed.
            stored_event[
                "status"
            ] = "active"

            changes = detect_changes(
                old_event,
                stored_event
            )

            if changes:

                changed_events.append({

                    "event":
                        stored_event,

                    "old":
                        old_event,

                    "changes":
                        changes,
                })

        else:

            event_id = make_new_id()

            stored_event = (
                clean_event_for_storage(
                    new_event,
                    event_id
                )
            )

            new_events.append(
                stored_event
            )

        current[event_id] = (
            stored_event
        )


    # --------------------------------------------------------
    # RETAIN EVENTS THAT DISAPPEARED
    #
    # We don't delete them immediately.
    # They stay available so a temporarily missing
    # event can regain its original ID later.
    # --------------------------------------------------------

    removed_events = []

    for event_id, old_event in existing.items():

        if event_id in used_ids:
            continue

        if event_id in current:
            continue

        retained = dict(
            old_event
        )

        retained[
            "status"
        ] = "not_in_feed"

        if (
            "not_in_feed_since"
            not in retained
        ):

            retained[
                "not_in_feed_since"
            ] = datetime.now(
                timezone.utc
            ).isoformat()

        current[event_id] = retained

        removed_events.append(
            retained
        )


    return (
        current,
        new_events,
        changed_events,
        removed_events
    )


# ============================================================
# DISPLAY
# ============================================================

def get_symbol(event):

    if event.get(
        "is_speech",
        False
    ):

        if event.get(
            "impact"
        ) == "High":

            return "🎤🔴"

        return "🎤"

    if event.get(
        "impact"
    ) == "High":

        return "🔴"

    return "🟠"


# ============================================================
# REFRESH
# ============================================================

def refresh_calendar():

    print()
    print("=" * 70)
    print("REFRESHING ECONOMIC CALENDAR")
    print("=" * 70)


    # --------------------------------------------------------
    # DOWNLOAD
    # --------------------------------------------------------

    try:

        raw_events = get_calendar()

    except Exception as error:

        print()
        print(
            f"⚠️ Calendar refresh failed: {error}"
        )

        print(
            "Existing stored events were "
            "NOT modified."
        )

        print("=" * 70)

        return load_existing()


    print(
        f"Downloaded {len(raw_events)} events."
    )


    # --------------------------------------------------------
    # FILTER
    # --------------------------------------------------------

    relevant_raw_events = [

        event

        for event in raw_events

        if should_include(event)
    ]


    prepared_events = []

    for event in relevant_raw_events:

        try:

            prepared_events.append(
                prepare_event(event)
            )

        except Exception as error:

            print(
                f"⚠️ Skipping malformed event: "
                f"{error}"
            )


    if not prepared_events:

        print()
        print(
            "⚠️ No relevant events were "
            "processed."
        )

        print(
            "Stored events were NOT modified."
        )

        print("=" * 70)

        return load_existing()


    # --------------------------------------------------------
    # LOAD EXISTING
    # --------------------------------------------------------

    existing = load_existing()


    # --------------------------------------------------------
    # RECONCILE
    # --------------------------------------------------------

    (
        current,
        new_events,
        changed_events,
        removed_events
    ) = reconcile_events(
        existing,
        prepared_events
    )


    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------

    save_events(
        current
    )


    active_count = sum(
        1
        for event in current.values()
        if event.get(
            "status",
            "active"
        ) == "active"
    )


    retained_count = sum(
        1
        for event in current.values()
        if event.get(
            "status"
        ) == "not_in_feed"
    )


    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    print()

    print(
        f"Relevant active events: "
        f"{active_count}"
    )

    print(
        f"New events detected: "
        f"{len(new_events)}"
    )

    print(
        f"Changed events detected: "
        f"{len(changed_events)}"
    )

    print(
        f"Events no longer in feed: "
        f"{len(removed_events)}"
    )

    print(
        f"Previously stored records: "
        f"{len(existing)}"
    )

    print(
        f"Total stored records: "
        f"{len(current)}"
    )


    # --------------------------------------------------------
    # NEW EVENTS
    # --------------------------------------------------------

    if new_events:

        print()
        print(
            "NEW EVENTS:"
        )

        for event in new_events:

            symbol = get_symbol(
                event
            )

            print(
                f"{symbol} "
                f"{event['currency']} - "
                f"{event['title']}"
            )


    # --------------------------------------------------------
    # CHANGED EVENTS
    # --------------------------------------------------------

    if changed_events:

        print()
        print(
            "CHANGED EVENTS:"
        )

        for item in changed_events:

            event = item["event"]
            old = item["old"]

            print()
            print(
                f"🔄 "
                f"{event['currency']} - "
                f"{event['title']}"
            )

            for change in item[
                "changes"
            ]:

                if change == "time changed":

                    print(
                        "   Time:"
                    )

                    print(
                        f"      Old: "
                        f"{old['time_utc']}"
                    )

                    print(
                        f"      New: "
                        f"{event['time_utc']}"
                    )

                elif change == "impact changed":

                    print(
                        "   Impact:"
                    )

                    print(
                        f"      Old: "
                        f"{old.get('impact')}"
                    )

                    print(
                        f"      New: "
                        f"{event.get('impact')}"
                    )

                elif change == "forecast changed":

                    print(
                        "   Forecast:"
                    )

                    print(
                        f"      Old: "
                        f"{old.get('forecast')}"
                    )

                    print(
                        f"      New: "
                        f"{event.get('forecast')}"
                    )

                elif change == "previous changed":

                    print(
                        "   Previous:"
                    )

                    print(
                        f"      Old: "
                        f"{old.get('previous')}"
                    )

                    print(
                        f"      New: "
                        f"{event.get('previous')}"
                    )


    # --------------------------------------------------------
    # REMOVED EVENTS
    # --------------------------------------------------------

    if removed_events:

        print()
        print(
            "NO LONGER IN FEED:"
        )

        for event in removed_events:

            print(
                f"⚪ "
                f"{event.get('currency')} - "
                f"{event.get('title')}"
            )


    print()
    print("=" * 70)

    return current


# ============================================================
# SELF TEST
# ============================================================

def run_self_test():

    print()
    print("=" * 70)
    print("RUNNING EVENT IDENTITY SELF-TEST")
    print("=" * 70)

    existing = load_existing()

    if not existing:

        print(
            "❌ No stored events found."
        )

        print(
            "Run the calendar refresh first."
        )

        return


    active_events = [

        event

        for event in existing.values()

        if event.get(
            "status",
            "active"
        ) == "active"
    ]


    if not active_events:

        print(
            "❌ No active events found."
        )

        return


    # --------------------------------------------------------
    # TEST 1: RESCHEDULE
    # --------------------------------------------------------

    original = active_events[0]

    prepared = stored_to_prepared(
        original
    )

    prepared[
        "_datetime"
    ] = (
        prepared["_datetime"]
        + timedelta(hours=1)
    )

    prepared[
        "_date"
    ] = prepared[
        "_datetime"
    ].date().isoformat()

    prepared[
        "time_utc"
    ] = prepared[
        "_datetime"
    ].isoformat()


    test_existing = {
        original["id"]:
            original
    }


    matched_id = find_best_match(
        prepared,
        test_existing,
        set(),
        same_date_only=False
    )


    if matched_id == original["id"]:

        print(
            "✅ Reschedule test passed"
        )

    else:

        print(
            "❌ Reschedule test FAILED"
        )


    # --------------------------------------------------------
    # TEST 2: DUPLICATE EVENTS
    # --------------------------------------------------------

    base = stored_to_prepared(
        original
    )

    duplicate_one = dict(
        base
    )

    duplicate_two = dict(
        base
    )

    duplicate_one[
        "_datetime"
    ] = base[
        "_datetime"
    ]

    duplicate_two[
        "_datetime"
    ] = (
        base["_datetime"]
        + timedelta(hours=2)
    )

    duplicate_one[
        "_date"
    ] = duplicate_one[
        "_datetime"
    ].date().isoformat()

    duplicate_two[
        "_date"
    ] = duplicate_two[
        "_datetime"
    ].date().isoformat()

    duplicate_one[
        "time_utc"
    ] = duplicate_one[
        "_datetime"
    ].isoformat()

    duplicate_two[
        "time_utc"
    ] = duplicate_two[
        "_datetime"
    ].isoformat()


    fake_id_one = "test-event-1"
    fake_id_two = "test-event-2"


    fake_existing = {

        fake_id_one: {
            "id":
                fake_id_one,

            "match_key":
                base["_match_key"],

            "title":
                base["title"],

            "currency":
                base["currency"],

            "impact":
                base["impact"],

            "time_utc":
                duplicate_one["time_utc"],

            "forecast":
                base["forecast"],

            "previous":
                base["previous"],

            "is_speech":
                base["is_speech"],

            "status":
                "active",
        },

        fake_id_two: {
            "id":
                fake_id_two,

            "match_key":
                base["_match_key"],

            "title":
                base["title"],

            "currency":
                base["currency"],

            "impact":
                base["impact"],

            "time_utc":
                duplicate_two["time_utc"],

            "forecast":
                base["forecast"],

            "previous":
                base["previous"],

            "is_speech":
                base["is_speech"],

            "status":
                "active",
        }
    }


    simulated_one = dict(
        duplicate_one
    )

    simulated_two = dict(
        duplicate_two
    )

    simulated_one[
        "_datetime"
    ] += timedelta(
        minutes=30
    )

    simulated_two[
        "_datetime"
    ] += timedelta(
        minutes=30
    )

    simulated_one[
        "time_utc"
    ] = simulated_one[
        "_datetime"
    ].isoformat()

    simulated_two[
        "time_utc"
    ] = simulated_two[
        "_datetime"
    ].isoformat()


    (
        result,
        _new,
        _changed,
        _removed
    ) = reconcile_events(
        fake_existing,
        [
            simulated_one,
            simulated_two
        ]
    )


    matched_test_ids = {

        event_id

        for event_id in result

        if event_id in {
            fake_id_one,
            fake_id_two
        }
    }


    if matched_test_ids == {
        fake_id_one,
        fake_id_two
    }:

        print(
            "✅ Duplicate-event test passed"
        )

    else:

        print(
            "❌ Duplicate-event test FAILED"
        )


    # --------------------------------------------------------
    # TEST 3: NEW EVENT
    # --------------------------------------------------------

    new_event = dict(
        base
    )

    new_event[
        "title"
    ] = "TEST - Brand New Event"

    new_event[
        "_match_key"
    ] = make_match_key(
        new_event[
            "currency"
        ],
        new_event[
            "title"
        ]
    )


    (
        result,
        new_events,
        _changed,
        _removed
    ) = reconcile_events(
        existing,
        [new_event]
    )


    if len(new_events) == 1:

        print(
            "✅ New-event test passed"
        )

    else:

        print(
            "❌ New-event test FAILED"
        )


    print()
    print(
        "Self-test complete."
    )

    print("=" * 70)


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    if (
        len(sys.argv) > 1
        and sys.argv[1] == "--test"
    ):

        run_self_test()

    else:

        refresh_calendar()