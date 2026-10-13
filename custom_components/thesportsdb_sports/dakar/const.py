from __future__ import annotations
from datetime import timedelta
from ..const import ATTRIBUTION, DOMAIN, STORAGE_VERSION, COMPETITION_DAKAR as ENTITY_PREFIX  # noqa: F401

NAME = "Dakar Rally"
CONF_CALENDAR_REST_DAYS = "calendar_rest_days"

DAKAR_LEAGUE_ID = "4447"

# TheSportsDB files every stage as its own round: 0 is the Prologue.
FIRST_ROUND = 0
MAX_ROUNDS = 20

UPDATE_INTERVAL = timedelta(hours=6)
UPDATE_INTERVAL_RALLY = timedelta(minutes=30)
# Poll faster from this long before the Prologue until this long after the finish.
RALLY_LEAD_TIME = timedelta(days=1)
RALLY_TRAIL_TIME = timedelta(days=2)

# A stage stops being refreshed once it is this old.
STAGE_SETTLED_AFTER = timedelta(days=2)
STAGE_FORCE_SETTLED_AFTER = timedelta(days=7)

FINISHED_STATUSES = ("FT", "AOT", "AET", "AP", "MATCH FINISHED", "FINISHED")
CANCELLED_STATUSES = ("PST", "CANC", "ABD", "POSTPONED", "CANCELLED")

STATUS_UPCOMING = "upcoming"
STATUS_RACING = "racing"
STATUS_REST_DAY = "rest_day"
STATUS_FINISHED = "finished"
RALLY_STATUSES = [STATUS_UPCOMING, STATUS_RACING, STATUS_REST_DAY, STATUS_FINISHED]
