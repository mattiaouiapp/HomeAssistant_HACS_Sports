"""Minimal async client for ESPN's public site API (no key needed)."""
from __future__ import annotations
import asyncio
from datetime import date
from typing import Any
import aiohttp

API_BASE_URL = "https://site.api.espn.com/apis"
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)


class EspnApiError(Exception):
    """ESPN could not be reached or returned garbage."""


class EspnApiClient:
    def __init__(self, session: aiohttp.ClientSession, sport: str, league: str) -> None:
        self._session = session
        self._path = f"sports/{sport}/{league}"

    async def _get(self, url: str, **params: Any) -> dict[str, Any]:
        try:
            async with self._session.get(url, params=params, timeout=REQUEST_TIMEOUT) as resp:
                resp.raise_for_status()
                data = await resp.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
            raise EspnApiError(f"{url}: {err}") from err
        if not isinstance(data, dict):
            raise EspnApiError(f"{url}: unexpected response")
        return data

    async def async_get_scoreboard(self, day: date) -> dict[str, Any]:
        """The games of one day, as ESPN counts it (US Eastern time for the NBA)."""
        return await self._get(
            f"{API_BASE_URL}/site/v2/{self._path}/scoreboard", dates=day.strftime("%Y%m%d")
        )

    async def async_get_standings(self, season_type: int) -> dict[str, Any]:
        return await self._get(f"{API_BASE_URL}/v2/{self._path}/standings", seasontype=season_type)

    async def async_get_team_schedule(self, team_id: str, season_type: int) -> dict[str, Any]:
        return await self._get(
            f"{API_BASE_URL}/site/v2/{self._path}/teams/{team_id}/schedule", seasontype=season_type
        )

    async def async_get_teams(self) -> list[dict[str, Any]]:
        data = await self._get(f"{API_BASE_URL}/site/v2/{self._path}/teams")
        try:
            return [t["team"] for t in data["sports"][0]["leagues"][0]["teams"]]
        except (KeyError, IndexError, TypeError) as err:
            raise EspnApiError(f"teams: {err}") from err
