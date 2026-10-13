"""NBA from ESPN: games and live scores, standings, playoffs and a favourite team."""
from __future__ import annotations
from typing import Any
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
from ..espn import EspnApiClient
from . import binary_sensor, calendar, sensor
from .const import CONF_CALENDAR_TEAM_ONLY, CONF_TEAM, ESPN_LEAGUE, ESPN_SPORT, NAME
from .coordinator import NbaCoordinator as Coordinator

__all__ = ["NAME", "Coordinator", "binary_sensor", "calendar", "create_client", "options_schema", "sensor"]

# ESPN needs no API key.
USES_API_KEY = False
NO_TEAM = "none"


def create_client(hass: HomeAssistant, entry: ConfigEntry) -> EspnApiClient:
    return EspnApiClient(async_get_clientsession(hass), ESPN_SPORT, ESPN_LEAGUE)


def _teams(entry: ConfigEntry) -> list[SelectOptionDict]:
    coordinator = getattr(entry, "runtime_data", None)
    teams = {}
    if coordinator is not None and coordinator.data is not None:
        teams = {t.id: t.name for t in coordinator.data.teams.values()}
    current = entry.options.get(CONF_TEAM)
    if current and current not in teams:
        teams[current] = current
    return [SelectOptionDict(value=NO_TEAM, label="-")] + [
        SelectOptionDict(value=team_id, label=name) for team_id, name in teams.items()
    ]


def options_schema(entry: ConfigEntry) -> dict[Any, Any]:
    return {
        vol.Optional(CONF_TEAM, default=entry.options.get(CONF_TEAM) or NO_TEAM): SelectSelector(
            SelectSelectorConfig(options=_teams(entry), mode=SelectSelectorMode.DROPDOWN)
        ),
        vol.Optional(
            CONF_CALENDAR_TEAM_ONLY, default=entry.options.get(CONF_CALENDAR_TEAM_ONLY, False)
        ): bool,
    }


def clean_options(options: dict[str, Any]) -> dict[str, Any]:
    team = options.get(CONF_TEAM)
    return {**options, CONF_TEAM: None if team in (None, NO_TEAM) else team}
