from __future__ import annotations
from datetime import datetime, timedelta
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util
from .const import ATTRIBUTION, DOMAIN, ENTITY_PREFIX, NAME
from .coordinator import WecCoordinator

# Entities derived from the clock (next/live session) re-evaluate this often.
CLOCK_TICK = timedelta(minutes=1)


class WecEntity(CoordinatorEntity[WecCoordinator]):
    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION

    def __init__(self, coordinator: WecCoordinator, platform: str, key: str) -> None:
        super().__init__(coordinator)
        entry_id = coordinator.config_entry.entry_id
        self._attr_unique_id = f"{entry_id}_{key}"
        self._attr_translation_key = key
        # Fixed entity IDs whatever the UI language, so the bundled dashboard always works.
        self.entity_id = f"{platform}.{ENTITY_PREFIX}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name=NAME,
            manufacturer="FIA World Endurance Championship",
            model="Season calendar",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://www.fiawec.com",
        )

    @property
    def available(self) -> bool:
        # Keep showing the cached calendar while TheSportsDB is down.
        return self.coordinator.data is not None

    @staticmethod
    def now() -> datetime:
        return dt_util.utcnow()


class WecClockEntity(WecEntity):
    """An entity whose state moves with time, not only with coordinator updates."""

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_track_time_interval(self.hass, self._async_tick, CLOCK_TICK)
        )

    @callback
    def _async_tick(self, _now: datetime) -> None:
        self.async_write_ha_state()
