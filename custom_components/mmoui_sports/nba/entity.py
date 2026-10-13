from __future__ import annotations
from datetime import datetime, timedelta
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import ATTRIBUTION, CONF_TEAM, DOMAIN, ENTITY_PREFIX, NAME, ORGANISER, WEBSITE
from .coordinator import NbaCoordinator, now

# Entities derived from the clock re-evaluate this often, so they follow tip-off and the game day.
CLOCK_TICK = timedelta(minutes=1)


class NbaEntity(CoordinatorEntity[NbaCoordinator]):
    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION

    def __init__(self, coordinator: NbaCoordinator, platform: str, key: str) -> None:
        super().__init__(coordinator)
        entry_id = coordinator.config_entry.entry_id
        self._attr_unique_id = f"{entry_id}_{key}"
        self._attr_translation_key = f"nba_{key}"
        # Fixed entity IDs whatever the UI language, so the bundled dashboard always works.
        self.entity_id = f"{platform}.{ENTITY_PREFIX}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name=NAME,
            manufacturer=ORGANISER,
            model="Basketball league",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=WEBSITE,
        )

    @property
    def available(self) -> bool:
        return self.coordinator.data is not None

    @property
    def team_id(self) -> str | None:
        return self.coordinator.config_entry.options.get(CONF_TEAM) or None

    @staticmethod
    def now() -> datetime:
        return now()


class NbaClockEntity(NbaEntity):
    """An entity whose state moves with the clock, not only with coordinator updates."""

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(async_track_time_interval(self.hass, self._async_tick, CLOCK_TICK))

    @callback
    def _async_tick(self, _now: datetime) -> None:
        self.async_write_ha_state()
