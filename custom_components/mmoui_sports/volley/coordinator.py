from __future__ import annotations
import asyncio
from datetime import date, datetime
from logging import getLogger
from typing import Any
import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from ..api import SportsApiClient, SportsApiError, SportsAuthError
from .const import (
    DOMAIN,
    MAX_GAP_SEARCHES,
    MAX_GAP_SEARCHES_FIRST,
    MAX_ROUNDS,
    MAX_STALE_LOOKUPS,
    MISSING_PAIR_RETRY,
    PLAYOFF_ROUND,
    PLAYOFF_WATCH_AFTER,
    PLAYOFF_WATCH_INTERVAL,
    ROUND_FORCE_SETTLED_AFTER,
    ROUND_HOT_AFTER,
    ROUND_HOT_BEFORE,
    ROUND_REFRESH_COLD,
    ROUND_SETTLED_AFTER,
    STALE_LOOKBACK,
    STATUS_FINISHED,
    STORAGE_VERSION,
    UPDATE_INTERVAL,
    UPDATE_INTERVAL_GAPS,
    UPDATE_INTERVAL_LIVE,
    UPDATE_INTERVAL_MATCHDAY,
    UPDATE_INTERVAL_RESULTS,
    UPDATE_INTERVAL_RETRY,
)
from . import lvc
from .models import VolleyData, VolleyRound, VolleySeason

_LOGGER = getLogger(__name__)

LVC_TIMEOUT = aiohttp.ClientTimeout(total=20)


def _has_score(event: dict[str, Any]) -> bool:
    return event.get("intHomeScore") not in (None, "") and event.get("intAwayScore") not in (None, "")


def now() -> datetime:
    """Match days are calendar days, so work with the local time."""
    return dt_util.now()


class VolleyCoordinator(DataUpdateCoordinator[VolleyData]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: SportsApiClient) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=UPDATE_INTERVAL)
        self.config_entry = entry
        self._client = client
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")
        self._season: str | None = None
        self._league_info: dict[str, Any] = {}
        self._raw_events: dict[str, dict[str, Any]] = {}
        self._settled_rounds: set[int] = set()
        # When each round was last fetched, and pairings TheSportsDB could not find.
        self._round_fetched: dict[int, datetime] = {}
        self._missing_pairs: dict[str, datetime] = {}
        self._playoffs_watched: datetime | None = None
        self._gaps_pending = False
        self._incomplete = False
        # The last update that went to TheSportsDB, the others only read the live board.
        self._last_full: datetime | None = None

    async def async_load_cache(self) -> bool:
        """Publish the stored season right away; returns False when there is none."""
        cached = await self._store.async_load()
        if not cached or not cached.get("events"):
            return False
        self._season = cached.get("season")
        self._league_info = cached.get("league") or {}
        self._raw_events = cached["events"]
        self._settled_rounds = set(cached.get("settled_rounds") or [])
        self._round_fetched = {
            int(k): t for k, v in (cached.get("round_fetched") or {}).items() if (t := dt_util.parse_datetime(v))
        }
        self._missing_pairs = {
            k: t for k, v in (cached.get("missing_pairs") or {}).items() if (t := dt_util.parse_datetime(v))
        }
        if watched := cached.get("playoffs_watched"):
            self._playoffs_watched = dt_util.parse_datetime(watched)
        self.async_set_updated_data(self._build())
        return True

    def _build(self) -> VolleyData:
        return VolleyData.from_raw(
            self._season,
            self._league_info,
            list(self._raw_events.values()),
            dt_util.get_default_time_zone(),
        )

    def _add(self, events: list[dict[str, Any]]) -> None:
        for event in events:
            event_id = str(event["idEvent"])
            known = self._raw_events.get(event_id)
            # The free key's lists come from a cache that lags behind the match pages:
            # an older copy without the score must not replace one that has it.
            if known is not None and _has_score(known) and not _has_score(event):
                continue
            self._raw_events[event_id] = event

    def _raw_team_names(self) -> dict[str, str]:
        """TheSportsDB's own team names, needed to search a match by name."""
        names: dict[str, str] = {}
        for event in self._raw_events.values():
            for side in ("Home", "Away"):
                if (team_id := event.get(f"id{side}Team")) and (name := event.get(f"str{side}Team")):
                    names[str(team_id)] = str(name)
        return names

    @staticmethod
    def _pick_season(league: dict[str, Any], upcoming: list[dict], past: list[dict]) -> str:
        # Seasons are "2026-2027": the newest of the league's current season and the
        # seasons of the next and last matches, which move first when a season starts.
        seasons = [str(s) for s in (league.get("strCurrentSeason"),) if s]
        seasons += [str(e["strSeason"]) for e in upcoming + past if e.get("strSeason")]
        if seasons:
            return max(seasons)
        year = now().year
        return f"{year}-{year + 1}" if now().month >= 7 else f"{year - 1}-{year}"

    async def _async_update_data(self) -> VolleyData:
        current = now()
        if self._live_only(current):
            await self._async_board_results()
            return await self._async_finish(current)

        first_load = self.data is None
        self._gaps_pending = False
        self._incomplete = False
        self._last_full = current
        try:
            league = await self._client.async_get_league()
            upcoming = await self._client.async_get_next()
            past = await self._client.async_get_past()
            season = self._pick_season(league, upcoming, past)
            if season != self._season:
                # New season: start over, the last match of the previous one comes back via past.
                self._season = season
                self._raw_events = {}
                self._settled_rounds = set()
                self._round_fetched = {}
                self._missing_pairs = {}
                self._playoffs_watched = None
            self._league_info = {
                k: league.get(k)
                for k in ("strLeague", "strBadge", "strLogo", "strBanner", "strPoster", "strTrophy", "strWebsite")
            }
            self._add(upcoming)
            self._add(past)
        except SportsAuthError as err:
            # The public keys cannot be revoked: a 403 on them is TheSportsDB throttling,
            # and asking to re-authenticate would stop every update until confirmed.
            if self._client.is_premium:
                raise ConfigEntryAuthFailed(str(err)) from err
            raise UpdateFailed(f"TheSportsDB refused the request: {err}") from err
        except SportsApiError as err:
            raise UpdateFailed(f"TheSportsDB request failed: {err}") from err

        try:
            self._add(await self._client.async_get_season(season))
            if not self._client.is_premium:
                await self._async_walk_rounds(season, current)
                await self._async_fill_gaps(
                    season, current, MAX_GAP_SEARCHES_FIRST if first_load else MAX_GAP_SEARCHES
                )
                await self._async_refresh_stale(current)
                await self._async_watch_playoffs(current)
        except SportsApiError as err:
            # An update makes dozens of requests on the free key: keep what came back
            # instead of throwing it away, or a single rate limited request would
            # freeze results and standings, and try again soon.
            _LOGGER.warning("SuperLega update incomplete, retrying soon: %s", err)
            self._incomplete = True
        await self._async_board_results()
        return await self._async_finish(current)

    def _live_only(self, current: datetime) -> bool:
        """While a match is being played, TheSportsDB is only asked every UPDATE_INTERVAL_MATCHDAY."""
        if self.data is None or self._last_full is None or current - self._last_full >= UPDATE_INTERVAL_MATCHDAY:
            return False
        return bool(self._build().current.live(current))

    async def _async_finish(self, current: datetime) -> VolleyData:
        data = self._build()
        self._mark_settled(data.current, current)
        await self._store.async_save(
            {
                "season": self._season,
                "league": self._league_info,
                "events": self._raw_events,
                "settled_rounds": sorted(self._settled_rounds),
                "round_fetched": {str(k): v.isoformat() for k, v in self._round_fetched.items()},
                "missing_pairs": {k: v.isoformat() for k, v in self._missing_pairs.items()},
                "playoffs_watched": self._playoffs_watched.isoformat() if self._playoffs_watched else None,
            }
        )
        self._adjust_interval(data.current, current)
        return data

    async def _async_board_results(self) -> None:
        """Lega Volley's live board has the results of the current round long before TheSportsDB."""
        season = self._build().current
        if not season.rounds:
            return
        try:
            async with async_get_clientsession(self.hass).get(lvc.LVC_URL, timeout=LVC_TIMEOUT) as resp:
                resp.raise_for_status()
                html = (await resp.read()).decode("utf-8", "replace")
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            _LOGGER.debug("Lega Volley live board unavailable: %s", err)
            return
        lvc.apply(lvc.parse(html, season.total_rounds // 2), season, self._raw_events)

    @staticmethod
    def _is_hot(rnd: VolleyRound, today: date) -> bool:
        return rnd.first_day - ROUND_HOT_BEFORE <= today <= rnd.last_day + ROUND_HOT_AFTER

    async def _async_walk_rounds(self, season: str, current: datetime) -> None:
        """The free key returns only 5 events per request: fetch the season one round at a time."""
        known = self._build().current
        highest_known = max((r.number for r in known.rounds), default=0)
        today = current.date()
        for number in range(1, MAX_ROUNDS + 1):
            if number in self._settled_rounds:
                continue
            rnd = known.round(number)
            fetched = self._round_fetched.get(number)
            if (
                rnd is not None
                and not self._is_hot(rnd, today)
                and fetched is not None
                and current - fetched < ROUND_REFRESH_COLD
            ):
                continue
            events = await self._client.async_get_round(season, number)
            self._round_fetched[number] = current
            if not events and number > highest_known:
                # Past the last published round.
                break
            self._add(events)

        # Playoff matches are all filed as round 0: look for them once the regular
        # season is nearly over.
        regular_end = known.regular_season_end
        if (
            PLAYOFF_ROUND not in self._settled_rounds
            and regular_end is not None
            and today >= regular_end - ROUND_HOT_BEFORE
        ):
            self._add(await self._client.async_get_round(season, PLAYOFF_ROUND))

    def _gap_candidates(
        self, rnd: VolleyRound, season: VolleySeason, seen: set[tuple[str, str]], current: datetime
    ) -> list[tuple[str, str]]:
        """Home/away pairings that may be the matches missing from a round.

        Every team plays every round, so the teams missing from a round play each
        other, and in a double round robin each home/away pairing happens once.
        """
        if len(rnd.matches) >= len(season.teams) // 2:
            return []
        missing = sorted(set(season.teams) - rnd.team_ids())
        candidates = []
        for home in missing:
            for away in missing:
                tried = self._missing_pairs.get(f"{home}|{away}")
                if home == away or (home, away) in seen or (tried and current - tried < MISSING_PAIR_RETRY):
                    continue
                candidates.append((home, away))
        return candidates

    async def _async_fill_gaps(self, season: str, current: datetime, budget: int) -> None:
        """Find the matches the free key leaves out of each round by searching them by name."""
        known = self._build().current
        names = self._raw_team_names()
        seen = {(m.home.id, m.away.id) for m in known.regular}
        today = current.date()
        # Played rounds first, they make the standings; then the closest ones.
        rounds = sorted(known.rounds, key=lambda r: (r.day > today, abs((r.day - today).days)))
        for rnd in rounds:
            if rnd.number in self._settled_rounds:
                continue
            found: set[str] = set()
            for home, away in self._gap_candidates(rnd, known, seen, current):
                if home in found or away in found or home not in names or away not in names:
                    continue
                if budget <= 0:
                    self._gaps_pending = True
                    return
                budget -= 1
                events = [
                    e
                    for e in await self._client.async_search_match(names[home], names[away], season)
                    if str(e.get("strSeason")) == season
                ]
                self._add(events)
                key = f"{home}|{away}"
                if any(str(e.get("intRound")) != str(PLAYOFF_ROUND) for e in events):
                    # The pairing's regular season match, maybe filed under another round.
                    seen.add((home, away))
                    self._missing_pairs.pop(key, None)
                    if any(str(e.get("intRound")) == str(rnd.number) for e in events):
                        found |= {home, away}
                else:
                    # Not published yet, or only a playoff match of the pairing came back.
                    self._missing_pairs[key] = current

    async def _async_refresh_stale(self, current: datetime) -> None:
        """Look finished matches up one by one until they have a result.

        The round lists lag behind, sometimes by days, and the matches found by
        name are not in them at all: the match page has the score first.
        """
        season = self._build().current
        stale = [
            m
            for m in season.active
            if not m.has_result
            and m.is_done(current)
            and m.day >= current.date() - STALE_LOOKBACK
        ]
        for match in stale[:MAX_STALE_LOOKUPS]:
            self._add(await self._client.async_get_event(match.id))

    async def _async_watch_playoffs(self, current: datetime) -> None:
        """The free key lists only 5 playoff matches: follow each playoff team's next and last match."""
        season = self._build().current
        regular_end = season.regular_season_end
        today = current.date()
        if regular_end is None or today <= regular_end or PLAYOFF_ROUND in self._settled_rounds:
            return
        if season.playoffs and season.playoffs[-1].day + PLAYOFF_WATCH_AFTER < today:
            return
        if self._playoffs_watched and current - self._playoffs_watched < PLAYOFF_WATCH_INTERVAL:
            return
        self._playoffs_watched = current
        teams = {t.id for m in season.playoffs for t in (m.home, m.away)} or set(season.teams)
        for team_id in sorted(teams):
            self._add(await self._client.async_get_team_last(team_id))
            self._add(await self._client.async_get_team_next(team_id))

    def _mark_settled(self, season: VolleySeason, current: datetime) -> None:
        today = current.date()
        seen = {(m.home.id, m.away.id) for m in season.regular}
        for rnd in season.rounds:
            age = today - rnd.last_day
            complete = len(rnd.matches) >= len(season.teams) // 2
            # A round with missing matches settles only once every pairing has been searched.
            searched = not self._gap_candidates(rnd, season, seen, current)
            if (age > ROUND_SETTLED_AFTER and rnd.finished and complete) or (
                age > ROUND_FORCE_SETTLED_AFTER and searched
            ):
                self._settled_rounds.add(rnd.number)
        if season.playoffs and season.status(current) == STATUS_FINISHED:
            if today - season.playoffs[-1].day > ROUND_FORCE_SETTLED_AFTER:
                self._settled_rounds.add(PLAYOFF_ROUND)

    @staticmethod
    def _results_pending(season: VolleySeason, current: datetime) -> bool:
        """Finished matches still waiting for TheSportsDB to publish their score."""
        return any(
            m.is_done(current) and not m.has_result and m.day >= current.date() - STALE_LOOKBACK
            for m in season.active
        )

    def _adjust_interval(self, season: VolleySeason, current: datetime) -> None:
        if season.live(current):
            self.update_interval = UPDATE_INTERVAL_LIVE
        elif self._incomplete:
            self.update_interval = UPDATE_INTERVAL_RETRY
        elif self._gaps_pending:
            self.update_interval = UPDATE_INTERVAL_GAPS
        elif season.matches_on(current.date()):
            self.update_interval = UPDATE_INTERVAL_MATCHDAY
        elif self._results_pending(season, current):
            self.update_interval = UPDATE_INTERVAL_RESULTS
        else:
            self.update_interval = UPDATE_INTERVAL
