"""The competitions this integration follows, one config entry each."""
from __future__ import annotations
from types import ModuleType
from homeassistant.config_entries import ConfigEntry
from . import dakar, nba, volley, wec
from .const import CONF_COMPETITION, COMPETITION_DAKAR, COMPETITION_NBA, COMPETITION_SUPERLEGA, COMPETITION_WEC

COMPETITIONS: dict[str, ModuleType] = {
    COMPETITION_WEC: wec,
    COMPETITION_DAKAR: dakar,
    COMPETITION_SUPERLEGA: volley,
    COMPETITION_NBA: nba,
}


def competition_of(entry: ConfigEntry) -> ModuleType:
    return COMPETITIONS[entry.data[CONF_COMPETITION]]


def uses_api_key(competition: ModuleType) -> bool:
    """TheSportsDB competitions take the API key; ESPN ones need none."""
    return getattr(competition, "USES_API_KEY", True)
