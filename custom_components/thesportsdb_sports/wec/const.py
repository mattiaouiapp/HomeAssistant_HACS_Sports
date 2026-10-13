from __future__ import annotations
from datetime import timedelta
from ..const import ATTRIBUTION, DOMAIN, STORAGE_VERSION, COMPETITION_WEC as ENTITY_PREFIX  # noqa: F401

NAME = "FIA WEC"
CONF_CALENDAR_SESSIONS = "calendar_sessions"

WEC_LEAGUE_ID = "4413"

# Round numbers TheSportsDB uses for the WEC season. 500 is the pre-season Prologue.
MAX_ROUNDS = 15
EXTRA_ROUNDS = (500,)

UPDATE_INTERVAL = timedelta(hours=6)
UPDATE_INTERVAL_WEEKEND = timedelta(minutes=30)

# A round stops being refreshed once its race is this old.
ROUND_SETTLED_AFTER = timedelta(days=2)
ROUND_FORCE_SETTLED_AFTER = timedelta(days=7)

FINISHED_STATUSES = ("FT", "AOT", "AET", "AP", "MATCH FINISHED", "FINISHED")
CANCELLED_STATUSES = ("PST", "CANC", "ABD", "POSTPONED", "CANCELLED")

KIND_RACE = "race"
KIND_QUALIFYING = "qualifying"
KIND_HYPERPOLE = "hyperpole"
KIND_PRACTICE = "practice"
KIND_WARMUP = "warmup"
KIND_TEST = "test"

# Estimated session lengths, TheSportsDB has start times only.
SESSION_DURATIONS = {
    KIND_PRACTICE: timedelta(minutes=90),
    KIND_QUALIFYING: timedelta(minutes=20),
    KIND_HYPERPOLE: timedelta(minutes=15),
    KIND_WARMUP: timedelta(minutes=15),
    KIND_TEST: timedelta(hours=4),
}
DEFAULT_RACE_DURATION = timedelta(hours=6)
