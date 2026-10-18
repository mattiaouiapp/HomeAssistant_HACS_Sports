from __future__ import annotations
from datetime import date, timedelta
from logging import getLogger
from typing import Any
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from ..api import SportsApiClient, SportsApiError, SportsAuthError
from .const import (
    DOMAIN,
    EXTRA_ROUNDS,
    MAX_ROUNDS,
    ROUND_FORCE_SETTLED_AFTER,
    ROUND_SETTLED_AFTER,
    STORAGE_VERSION,
    UPDATE_INTERVAL,
    UPDATE_INTERVAL_WEEKEND,
)
from .models import WecData, WecEvent, WecRound

_LOGGER = getLogger(__name__)

# The free key returns at most this many events per round.
FREE_ROUND_CAP = 5
# Day lookups needed to find the race (and capped sessions) after the last known session.
DAYS_AFTER_LAST_SESSION = 2
MAX_DAY_LOOKUPS = 6


class WecCoordinator(DataUpdateCoordinator[WecData]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: SportsApiClient) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=UPDATE_INTERVAL)
        self.config_entry = entry
        self._client = client
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")
        self._season: str | None = None
        self._league: dict[str, Any] = {}
        self._raw_events: dict[str, dict[str, Any]] = {}
        self._settled_rounds: set[int] = set()

    async def async_load_cache(self) -> bool:
        """Publish the stored calendar right away; returns False when there is none."""
        cached = await self._store.async_load()
        if not cached or not cached.get("events"):
            return False
        self._season = cached.get("season")
        self._league = cached.get("league") or {}
        self._raw_events = cached["events"]
        self._settled_rounds = set(cached.get("settled_rounds") or [])
        self.async_set_updated_data(self._build())
        return True

    def _build(self) -> WecData:
        return WecData.from_raw(self._season, self._league, list(self._raw_events.values()))

    def _add(self, events: list[dict[str, Any]]) -> None:
        for event in events:
            self._raw_events[str(event["idEvent"])] = event

    async def _async_update_data(self) -> WecData:
        try:
            league = await self._client.async_get_league()
            season = league.get("strCurrentSeason") or str(dt_util.utcnow().year)
            if season != self._season:
                # New season: start over, last season's races still arrive via the past endpoint.
                self._season = season
                self._raw_events = {}
                self._settled_rounds = set()
            self._league = {
                k: league.get(k)
                for k in ("strLeague", "strCurrentSeason", "strBadge", "strLogo", "strWebsite")
            }

            self._add(await self._client.async_get_season(season))
            if not self._client.is_premium:
                await self._async_fill_free_rounds(season)
            self._add(await self._client.async_get_next())
            self._add(await self._client.async_get_past())
        except SportsAuthError as err:
            # The public keys cannot be revoked: a 403 on them is TheSportsDB throttling,
            # and asking to re-authenticate would stop every update until confirmed.
            if self._client.is_premium:
                raise ConfigEntryAuthFailed(str(err)) from err
            raise UpdateFailed(f"TheSportsDB refused the request: {err}") from err
        except SportsApiError as err:
            raise UpdateFailed(f"TheSportsDB request failed: {err}") from err

        data = self._build()
        self._mark_settled(data)
        await self._store.async_save(
            {
                "season": self._season,
                "league": self._league,
                "events": self._raw_events,
                "settled_rounds": sorted(self._settled_rounds),
            }
        )
        self._adjust_interval(data)
        return data

    async def _async_fill_free_rounds(self, season: str) -> None:
        """Work around the free key caps: walk every round, then look up race days."""
        known = self._build()
        highest_known = max((r.number for r in known.rounds if r.number < 100), default=0)
        for number in range(1, MAX_ROUNDS + 1):
            if number in self._settled_rounds:
                continue
            events = await self._client.async_get_round(season, number)
            if not events and number > highest_known:
                # Past the end of the calendar.
                break
            await self._async_fill_round(number, events)
        for number in EXTRA_ROUNDS:
            if number not in self._settled_rounds:
                await self._async_fill_round(number, await self._client.async_get_round(season, number))

    async def _async_fill_round(self, number: int, events: list[dict[str, Any]]) -> None:
        if not events:
            return
        self._add(events)
        round_ = self._round(number)
        if round_ is not None and (len(events) >= FREE_ROUND_CAP or round_.race is None):
            for day in self._days_to_check(round_):
                self._add(await self._client.async_get_day(day))

    def _round(self, number: int) -> WecRound | None:
        return next(
            (r for r in self._build().rounds if r.number == number and r.season == self._season),
            None,
        )

    @staticmethod
    def _days_to_check(round_: WecRound) -> list[str]:
        first: date = round_.start.date()
        last: date = max(e.start for e in round_.events).date() + timedelta(days=DAYS_AFTER_LAST_SESSION)
        days = [first + timedelta(days=i) for i in range((last - first).days + 1)]
        # The race comes last, so the latest days matter most when capping.
        return [day.isoformat() for day in days[-MAX_DAY_LOOKUPS:]]

    def _mark_settled(self, data: WecData) -> None:
        now = dt_util.utcnow()
        for round_ in data.rounds:
            if round_.season != self._season:
                continue
            race: WecEvent | None = round_.race
            age = now - round_.end
            if age > ROUND_FORCE_SETTLED_AFTER:
                self._settled_rounds.add(round_.number)
            elif race and age > ROUND_SETTLED_AFTER and (race.is_finished or race.is_cancelled):
                self._settled_rounds.add(round_.number)

    def _adjust_interval(self, data: WecData) -> None:
        now = dt_util.utcnow()
        weekend = data.current_round(now) is not None
        if not weekend and (nxt := data.next_session(now)):
            weekend = nxt.start - now < timedelta(days=1)
        if not weekend and (last := data.last_race(now)):
            # Keep polling until the result shows up.
            weekend = not last.result and now - last.end < ROUND_SETTLED_AFTER
        self.update_interval = UPDATE_INTERVAL_WEEKEND if weekend else UPDATE_INTERVAL
