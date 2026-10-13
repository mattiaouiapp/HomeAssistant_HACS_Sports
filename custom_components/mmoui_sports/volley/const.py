from __future__ import annotations
from datetime import timedelta
from ..const import ATTRIBUTION, DOMAIN, STORAGE_VERSION  # noqa: F401

CONF_TEAM = "team"
CONF_CALENDAR_TEAM_ONLY = "calendar_team_only"

LEAGUE_ID = "4544"
LEAGUE_SLUG = "superlega"
LEAGUE_NAME = "SuperLega"
LEAGUE_ORGANISER = "Lega Pallavolo Serie A"
LEAGUE_WEBSITE = "https://www.legavolley.it"


# Regular season rounds are 1..N, every playoff match is filed as round 0.
PLAYOFF_ROUND = 0
MAX_ROUNDS = 40

UPDATE_INTERVAL = timedelta(hours=6)
UPDATE_INTERVAL_MATCHDAY = timedelta(minutes=10)
# While matches missing from the free key's lists are still being looked for.
UPDATE_INTERVAL_GAPS = timedelta(minutes=2)

# Rounds are refreshed on every update from this long before their first match
# until this long after their last one, the others once a day.
ROUND_HOT_BEFORE = timedelta(days=7)
ROUND_HOT_AFTER = timedelta(days=3)
ROUND_REFRESH_COLD = timedelta(hours=24)
# A round stops being refreshed once its last match is this old and has a result.
ROUND_SETTLED_AFTER = timedelta(days=2)
ROUND_FORCE_SETTLED_AFTER = timedelta(days=14)
# A pairing that TheSportsDB could not find is searched again after this long.
MISSING_PAIR_RETRY = timedelta(days=1)
# Bound the gap filling of an update (30 requests are about a minute on the free key),
# with a smaller first load so Home Assistant does not wait for the whole season.
MAX_GAP_SEARCHES = 30
MAX_GAP_SEARCHES_FIRST = 6
# Matches found by name are looked up again until they have a result.
MAX_STALE_LOOKUPS = 10
STALE_LOOKBACK = timedelta(days=14)
# Playoff teams are polled one by one, at most this often, from the end of the
# regular season until this long after the last playoff match.
PLAYOFF_WATCH_INTERVAL = timedelta(hours=1)
PLAYOFF_WATCH_AFTER = timedelta(days=10)

# A match without a result is considered in progress for this long after its start.
MATCH_DURATION = timedelta(hours=2, minutes=30)
# Calendar entries use this length.
CALENDAR_MATCH_LENGTH = timedelta(hours=2)

FINISHED_STATUSES = ("FT", "AOT", "AET", "AP", "MATCH FINISHED", "FINISHED")
CANCELLED_STATUSES = ("PST", "CANC", "ABD", "POSTPONED", "CANCELLED", "SUSP")

STATUS_PRESEASON = "preseason"
STATUS_REGULAR_SEASON = "regular_season"
STATUS_PLAYOFFS = "playoffs"
STATUS_FINISHED = "finished"
SEASON_STATUSES = [STATUS_PRESEASON, STATUS_REGULAR_SEASON, STATUS_PLAYOFFS, STATUS_FINISHED]

OUTCOME_WON = "won"
OUTCOME_LOST = "lost"
