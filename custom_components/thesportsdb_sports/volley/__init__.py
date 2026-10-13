"""SuperLega volleyball: fixtures, results, standings, playoffs and a favourite team."""
from __future__ import annotations
from typing import Any
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
from . import binary_sensor, calendar, sensor
from .const import CONF_CALENDAR_TEAM_ONLY, CONF_TEAM, LEAGUE_ID, LEAGUE_NAME as NAME
from .coordinator import VolleyCoordinator as Coordinator

__all__ = ["LEAGUE_ID", "NAME", "Coordinator", "binary_sensor", "calendar", "options_schema", "sensor"]

# The "no favourite team" choice of the options form.
NO_TEAM = "none"


def _teams(entry: ConfigEntry) -> list[SelectOptionDict]:
    """The teams of the current season, plus the configured one if it has been relegated."""
    coordinator = getattr(entry, "runtime_data", None)
    teams = {}
    if coordinator is not None and coordinator.data is not None:
        teams = {t.id: t.name for t in coordinator.data.current.teams.values()}
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
