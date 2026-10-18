"""Minimal async client for the TheSportsDB v1 API, scoped to one league."""
from __future__ import annotations
import asyncio
import json
from logging import getLogger
from time import monotonic
from typing import Any
import aiohttp
from .const import API_BASE_URL, FREE_API_KEYS, FREE_REQUEST_SPACING, PREMIUM_REQUEST_SPACING

_LOGGER = getLogger(__name__)

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)
# A 429 means the minute is used up: wait for it to roll over.
RATE_LIMIT_RETRY_DELAY = 60


class SportsApiError(Exception):
    """TheSportsDB could not be reached or returned garbage."""


class SportsAuthError(SportsApiError):
    """The API key was rejected."""


class _Throttle:
    """Shared by every client: the per-minute limit counts all the requests to TheSportsDB."""

    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.last_request = 0.0


_THROTTLE = _Throttle()


class SportsApiClient:
    def __init__(self, session: aiohttp.ClientSession, api_key: str, league_id: str) -> None:
        self._session = session
        self._api_key = api_key
        self._league_id = league_id

    @property
    def is_premium(self) -> bool:
        return self._api_key not in FREE_API_KEYS

    async def _get(self, endpoint: str, **params: Any) -> dict[str, Any]:
        url = f"{API_BASE_URL}/{self._api_key}/{endpoint}"
        spacing = PREMIUM_REQUEST_SPACING if self.is_premium else FREE_REQUEST_SPACING
        # Serialise requests so a full season refresh never trips the per-minute limit.
        async with _THROTTLE.lock:
            for attempt in (1, 2):
                wait = _THROTTLE.last_request + spacing - monotonic()
                if wait > 0:
                    await asyncio.sleep(wait)
                _THROTTLE.last_request = monotonic()
                try:
                    async with self._session.get(url, params=params, timeout=REQUEST_TIMEOUT) as resp:
                        if resp.status == 429 and attempt == 1:
                            _LOGGER.debug("TheSportsDB rate limit hit, retrying in %ss", RATE_LIMIT_RETRY_DELAY)
                            await asyncio.sleep(RATE_LIMIT_RETRY_DELAY)
                            continue
                        if resp.status in (401, 403):
                            raise SportsAuthError(f"API key rejected ({resp.status})")
                        resp.raise_for_status()
                        # TheSportsDB sometimes answers JSON as text/html, and empty
                        # results as an empty body.
                        text = await resp.text()
                        data = json.loads(text) if text.strip() else {}
                except SportsApiError:
                    raise
                except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
                    raise SportsApiError(f"{endpoint}: {err}") from err
                if not isinstance(data, dict):
                    # An invalid key returns a bare list.
                    raise SportsAuthError(f"{endpoint}: unexpected response")
                return data
        raise SportsApiError(f"{endpoint}: rate limited")

    def _events(self, data: dict[str, Any], key: str = "events") -> list[dict[str, Any]]:
        events = data.get(key) or []
        return [
            e
            for e in events
            if isinstance(e, dict)
            and e.get("idEvent")
            and str(e.get("idLeague") or self._league_id) == self._league_id
        ]

    async def async_get_league(self) -> dict[str, Any]:
        data = await self._get("lookupleague.php", id=self._league_id)
        leagues = data.get("leagues") or []
        if not leagues:
            raise SportsAuthError("League lookup returned nothing")
        return leagues[0]

    async def async_get_season(self, season: str) -> list[dict[str, Any]]:
        return self._events(await self._get("eventsseason.php", id=self._league_id, s=season))

    async def async_get_round(self, season: str, round_number: int) -> list[dict[str, Any]]:
        return self._events(
            await self._get("eventsround.php", id=self._league_id, r=round_number, s=season)
        )

    async def async_get_day(self, day: str) -> list[dict[str, Any]]:
        return self._events(await self._get("eventsday.php", d=day, l=self._league_id))

    async def async_get_next(self) -> list[dict[str, Any]]:
        return self._events(await self._get("eventsnextleague.php", id=self._league_id))

    async def async_get_past(self) -> list[dict[str, Any]]:
        return self._events(await self._get("eventspastleague.php", id=self._league_id))

    async def async_get_event(self, event_id: str) -> list[dict[str, Any]]:
        return self._events(await self._get("lookupevent.php", id=event_id))

    async def async_search_match(self, home: str, away: str, season: str) -> list[dict[str, Any]]:
        """The match between two teams in a season (the free key returns only the latest one)."""
        name = f"{home} vs {away}".replace(" ", "_")
        return self._events(await self._get("searchevents.php", e=name, s=season), key="event")

    async def async_get_team_next(self, team_id: str) -> list[dict[str, Any]]:
        return self._events(await self._get("eventsnext.php", id=team_id))

    async def async_get_team_last(self, team_id: str) -> list[dict[str, Any]]:
        return self._events(await self._get("eventslast.php", id=team_id), key="results")
