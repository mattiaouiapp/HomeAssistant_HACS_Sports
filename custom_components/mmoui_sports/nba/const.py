from __future__ import annotations
from datetime import timedelta
from zoneinfo import ZoneInfo
from ..const import ATTRIBUTION_ESPN as ATTRIBUTION, DOMAIN, COMPETITION_NBA as ENTITY_PREFIX  # noqa: F401

NAME = "NBA"
ORGANISER = "National Basketball Association"
WEBSITE = "https://www.nba.com"

CONF_TEAM = "team"
CONF_CALENDAR_TEAM_ONLY = "calendar_team_only"

ESPN_SPORT = "basketball"
ESPN_LEAGUE = "nba"

# ESPN files NBA games under the US Eastern date: a 7:30 PM game in New York is
# a Tuesday game even if it starts at 1:30 on Wednesday in Europe.
GAME_DAY_TZ = ZoneInfo("America/New_York")
# Game days fetched on every update, relative to the current game day.
DAYS_BEFORE = 1
DAYS_AFTER = 2
# Further game days for the calendar and the next league game, fetched once in a while.
DAYS_AHEAD = 7
AHEAD_REFRESH = timedelta(hours=6)
STANDINGS_REFRESH = timedelta(hours=1)
SCHEDULE_REFRESH = timedelta(hours=1)

UPDATE_INTERVAL = timedelta(hours=1)
UPDATE_INTERVAL_GAME_DAY = timedelta(minutes=15)
UPDATE_INTERVAL_LIVE = timedelta(minutes=1)
# Poll faster from this long before the first game of the day.
GAME_DAY_LEAD = timedelta(hours=1)

# ESPN season types.
SEASON_TYPE_PRESEASON = 1
SEASON_TYPE_REGULAR = 2
SEASON_TYPE_POSTSEASON = 3
SEASON_TYPE_OFFSEASON = 4
SEASON_TYPE_PLAY_IN = 5

STATUS_PRESEASON = "preseason"
STATUS_REGULAR_SEASON = "regular_season"
STATUS_PLAY_IN = "play_in"
STATUS_PLAYOFFS = "playoffs"
STATUS_OFFSEASON = "offseason"
SEASON_STATUSES = [STATUS_PRESEASON, STATUS_REGULAR_SEASON, STATUS_PLAY_IN, STATUS_PLAYOFFS, STATUS_OFFSEASON]
SEASON_TYPE_STATUS = {
    SEASON_TYPE_PRESEASON: STATUS_PRESEASON,
    SEASON_TYPE_REGULAR: STATUS_REGULAR_SEASON,
    SEASON_TYPE_POSTSEASON: STATUS_PLAYOFFS,
    SEASON_TYPE_OFFSEASON: STATUS_OFFSEASON,
    SEASON_TYPE_PLAY_IN: STATUS_PLAY_IN,
}

GAME_PRE = "pre"
GAME_LIVE = "in"
GAME_FINAL = "post"
CANCELLED_STATUSES = ("STATUS_POSTPONED", "STATUS_CANCELED", "STATUS_SUSPENDED")

OUTCOME_WON = "won"
OUTCOME_LOST = "lost"

# Calendar entries use this length when the game has not finished.
CALENDAR_GAME_LENGTH = timedelta(hours=2, minutes=30)
