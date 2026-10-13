"""Dakar Rally: stages, bivouacs, rest days and results."""
from __future__ import annotations
from typing import Any
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from . import binary_sensor, calendar, sensor
from .const import CONF_CALENDAR_REST_DAYS, DAKAR_LEAGUE_ID as LEAGUE_ID, NAME
from .coordinator import DakarCoordinator as Coordinator

__all__ = ["LEAGUE_ID", "NAME", "Coordinator", "binary_sensor", "calendar", "options_schema", "sensor"]


def options_schema(entry: ConfigEntry) -> dict[Any, Any]:
    return {
        vol.Optional(
            CONF_CALENDAR_REST_DAYS, default=entry.options.get(CONF_CALENDAR_REST_DAYS, True)
        ): bool,
    }
