from __future__ import annotations
from datetime import date, datetime, timedelta
from logging import getLogger
from typing import Any
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from ..espn import EspnApiClient, EspnApiError
from .const import (
    AHEAD_REFRESH,
    CONF_TEAM,
    DAYS_AFTER,
    DAYS_AHEAD,
    DAYS_BEFORE,
    DOMAIN,
    ENTITY_PREFIX,
    GAME_DAY_LEAD,
    SCHEDULE_REFRESH,
    SEASON_TYPE_PLAY_IN,
    SEASON_TYPE_POSTSEASON,
    SEASON_TYPE_PRESEASON,
    SEASON_TYPE_REGULAR,
    STANDINGS_REFRESH,
    UPDATE_INTERVAL,
    UPDATE_INTERVAL_GAME_DAY,
    UPDATE_INTERVAL_LIVE,
)
from .models import NbaData, NbaGame, NbaTeam, game_day, parse_standings

_LOGGER = getLogger(__name__)


def now() -> datetime:
    return dt_util.now()


class NbaCoordinator(DataUpdateCoordinator[NbaData]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: EspnApiClient) -> None:
        super().__init__(hass, _LOGGER, name=f"{DOMAIN}_{ENTITY_PREFIX}", update_interval=UPDATE_INTERVAL)
        self.config_entry = entry
        self._client = client
        # Raw ESPN events per game day, and when the slower parts were last fetched.
        self._days: dict[date, list[dict[str, Any]]] = {}
        self._ahead_fetched: datetime | None = None
        self._around_fetched: datetime | None = None
        # Finished games already reflected in the standings and the team schedule.
        self._finals_seen: set[str] = set()
        self._standings: dict[str, list[dict[str, Any]]] = {}
        self._standings_fetched: datetime | None = None
        self._schedule: list[dict[str, Any]] = []
        self._schedule_fetched: datetime | None = None
        self._teams: dict[str, NbaTeam] = {}
        self._league: dict[str, Any] = {}

    @property
    def team_id(self) -> str | None:
        return self.config_entry.options.get(CONF_TEAM) or None

    async def async_load_cache(self) -> bool:
        # ESPN answers in a few requests: no stored copy needed.
        return False

    async def _async_update_data(self) -> NbaData:
        current = now()
        today = game_day(current)
        try:
            if not self._teams:
                self._teams = {
                    t.id: t for t in (NbaTeam.from_api(raw) for raw in await self._client.async_get_teams())
                }
            # During games only today's scoreboard is refreshed every minute; the
            # days around it every quarter of an hour.
            hot = [today]
            if self._due(self._around_fetched, UPDATE_INTERVAL_GAME_DAY, current):
                hot = [today + timedelta(days=d) for d in range(-DAYS_BEFORE, DAYS_AFTER + 1)]
                self._around_fetched = current
            if self._due(self._ahead_fetched, AHEAD_REFRESH, current):
                hot += [today + timedelta(days=d) for d in range(DAYS_AFTER + 1, DAYS_AHEAD + 1)]
                self._ahead_fetched = current
            for day in hot:
                data = await self._client.async_get_scoreboard(day)
                if day == today:
                    self._league = (data.get("leagues") or [{}])[0]
                self._days[day] = data.get("events") or []
            # Keep a week of finished game days, enough for "last results".
            self._days = {d: e for d, e in self._days.items() if d >= today - timedelta(days=7)}

            season_type = self._season_type()
            finals = {g.id for g in self._games() if g.is_final}
            new_results = bool(finals - self._finals_seen)
            if self._due(self._standings_fetched, STANDINGS_REFRESH, current) or new_results:
                # The regular season table also stands during the play-in and the playoffs.
                self._standings = parse_standings(await self._client.async_get_standings(SEASON_TYPE_REGULAR))
                self._standings_fetched = current

            if self.team_id and (
                self._due(self._schedule_fetched, SCHEDULE_REFRESH, current)
                or new_results
            ):
                types = {SEASON_TYPE_REGULAR}
                if season_type in (SEASON_TYPE_PRESEASON, SEASON_TYPE_POSTSEASON, SEASON_TYPE_PLAY_IN):
                    types.add(season_type)
                self._schedule = []
                for kind in sorted(types):
                    data = await self._client.async_get_team_schedule(self.team_id, kind)
                    self._schedule += data.get("events") or []
                self._schedule_fetched = current
            self._finals_seen = finals
        except EspnApiError as err:
            raise UpdateFailed(f"ESPN request failed: {err}") from err

        data = self._build()
        self._adjust_interval(data, current)
        return data

    @staticmethod
    def _due(last: datetime | None, every: timedelta, current: datetime) -> bool:
        return last is None or current - last >= every

    def _season_type(self) -> int | None:
        try:
            return int((self._league.get("season") or {}).get("type", {}).get("type"))
        except (TypeError, ValueError):
            return None

    def _games(self) -> list[NbaGame]:
        games = {}
        for events in self._days.values():
            for event in events:
                if (game := NbaGame.from_api(event)) is not None:
                    games[game.id] = game
        return sorted(games.values(), key=lambda g: g.start)

    def _build(self) -> NbaData:
        season = self._league.get("season") or {}
        team_games = [g for g in (NbaGame.from_api(e) for e in self._schedule) if g is not None]
        return NbaData(
            season=season.get("displayName") or (str(season["year"]) if season.get("year") else None),
            season_type=self._season_type(),
            season_start=_date(self._league.get("calendarStartDate")),
            season_end=_date(self._league.get("calendarEndDate")),
            games=self._games(),
            standings=self._standings,
            teams=dict(sorted(self._teams.items(), key=lambda t: t[1].name)),
            team_games=sorted(team_games, key=lambda g: g.start),
        )

    def _adjust_interval(self, data: NbaData, current: datetime) -> None:
        if data.live():
            self.update_interval = UPDATE_INTERVAL_LIVE
        elif any(
            not g.is_final and not g.is_cancelled and g.start - GAME_DAY_LEAD <= current
            for g in data.games_on(game_day(current))
        ):
            # Tip-off is close or a game should be on: catch the start and the result.
            self.update_interval = UPDATE_INTERVAL_LIVE
        elif data.games_on(game_day(current)):
            self.update_interval = UPDATE_INTERVAL_GAME_DAY
        else:
            self.update_interval = UPDATE_INTERVAL


def _date(value: Any) -> date | None:
    parsed = dt_util.parse_datetime(value) if isinstance(value, str) else None
    return game_day(parsed) if parsed else None
