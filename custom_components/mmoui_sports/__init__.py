from __future__ import annotations
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from .api import SportsApiClient
from .competitions import competition_of
from .const import CONF_API_KEY, DEFAULT_API_KEY, DOMAIN, STORAGE_VERSION

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.CALENDAR,
]

type SportsConfigEntry = ConfigEntry[DataUpdateCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: SportsConfigEntry) -> bool:
    competition = competition_of(entry)
    if create_client := getattr(competition, "create_client", None):
        client = create_client(hass, entry)
    else:
        api_key = entry.options.get(CONF_API_KEY) or entry.data.get(CONF_API_KEY) or DEFAULT_API_KEY
        client = SportsApiClient(async_get_clientsession(hass), api_key, competition.LEAGUE_ID)
    coordinator = competition.Coordinator(hass, entry, client)

    # A first load on the free key walks the season one round at a time and takes
    # a minute or two because of the rate limit. With a stored season, start from
    # that and refresh in the background instead of blocking Home Assistant startup.
    if await coordinator.async_load_cache():
        entry.async_create_background_task(
            hass, coordinator.async_refresh(), f"{DOMAIN}_{entry.entry_id}_initial_refresh"
        )
    else:
        await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_reload(hass: HomeAssistant, entry: SportsConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: SportsConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: SportsConfigEntry) -> None:
    await Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}").async_remove()
