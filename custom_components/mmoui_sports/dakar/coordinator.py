from __future__ import annotations
from datetime import date
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
    FIRST_ROUND,
    MAX_ROUNDS,
    RALLY_LEAD_TIME,
    RALLY_TRAIL_TIME,
    STAGE_FORCE_SETTLED_AFTER,
    STAGE_SETTLED_AFTER,
    STORAGE_VERSION,
    UPDATE_INTERVAL,
    UPDATE_INTERVAL_RALLY,
)
from .models import DakarData

_LOGGER = getLogger(__name__)


def today() -> date:
    """Stage dates are calendar days, so compare them with the local date."""
    return dt_util.now().date()


class DakarCoordinator(DataUpdateCoordinator[DakarData]):
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
        """Publish the stored stages right away; returns False when there are none."""
        cached = await self._store.async_load()
        if not cached or not cached.get("events"):
            return False
        self._season = cached.get("season")
        self._league = cached.get("league") or {}
        self._raw_events = cached["events"]
        self._settled_rounds = set(cached.get("settled_rounds") or [])
        self.async_set_updated_data(self._build())
        return True

    def _build(self) -> DakarData:
        return DakarData.from_raw(self._season, self._league, list(self._raw_events.values()))

    def _add(self, events: list[dict[str, Any]]) -> None:
        for event in events:
            self._raw_events[str(event["idEvent"])] = event

    @staticmethod
    def _pick_season(league: dict[str, Any], upcoming: list[dict], past: list[dict]) -> str:
        # strCurrentSeason lags behind for the Dakar (it still said 2025 after the 2026
        # edition), so follow the events: the next stage, else the last one.
        for events in (upcoming, past):
            if events and (season := events[0].get("strSeason")):
                return str(season)
        return league.get("strCurrentSeason") or str(today().year)

    async def _async_update_data(self) -> DakarData:
        try:
            league = await self._client.async_get_league()
            upcoming = await self._client.async_get_next()
            past = await self._client.async_get_past()
            season = self._pick_season(league, upcoming, past)
            if season != self._season:
                # New edition: start over, the last stage of the previous one comes back via past.
                self._season = season
                self._raw_events = {}
                self._settled_rounds = set()
            self._league = {
                k: league.get(k)
                for k in ("strLeague", "strBadge", "strLogo", "strBanner", "strPoster", "strTrophy", "strWebsite")
            }
            self._add(upcoming)
            self._add(past)
            self._add(await self._client.async_get_season(season))
            if not self._client.is_premium:
                await self._async_walk_rounds(season)
        except SportsAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
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

    async def _async_walk_rounds(self, season: str) -> None:
        """The free key returns only 5 events per season: fetch the stages one round at a time."""
        known = self._build().rally.stages
        highest_known = max((s.number for s in known), default=FIRST_ROUND)
        for number in range(FIRST_ROUND, MAX_ROUNDS + 1):
            if number in self._settled_rounds:
                continue
            events = await self._client.async_get_round(season, number)
            if not events and number > max(highest_known, FIRST_ROUND):
                # Past the last stage.
                break
            self._add(events)

    def _mark_settled(self, data: DakarData) -> None:
        now = today()
        for stage in data.rally.stages:
            age = now - stage.day
            if age > STAGE_FORCE_SETTLED_AFTER or (age > STAGE_SETTLED_AFTER and stage.has_result):
                self._settled_rounds.add(stage.number)

    def _adjust_interval(self, data: DakarData) -> None:
        rally = data.rally
        now = today()
        racing = (
            rally.start is not None
            and rally.start - RALLY_LEAD_TIME <= now <= rally.end + RALLY_TRAIL_TIME
        )
        self.update_interval = UPDATE_INTERVAL_RALLY if racing else UPDATE_INTERVAL
