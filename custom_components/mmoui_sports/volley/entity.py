from __future__ import annotations
from datetime import datetime, timedelta
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import ATTRIBUTION, CONF_TEAM, DOMAIN, LEAGUE_NAME, LEAGUE_ORGANISER, LEAGUE_SLUG, LEAGUE_WEBSITE
from .coordinator import VolleyCoordinator, now
from .models import Team

# Entities derived from the clock re-evaluate this often, so they follow kick-off and midnight.
CLOCK_TICK = timedelta(minutes=1)


class VolleyEntity(CoordinatorEntity[VolleyCoordinator]):
    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION

    def __init__(self, coordinator: VolleyCoordinator, platform: str, key: str) -> None:
        super().__init__(coordinator)
        entry_id = coordinator.config_entry.entry_id
        self._attr_unique_id = f"{entry_id}_{key}"
        self._attr_translation_key = key
        # Fixed entity IDs whatever the UI language, so the bundled dashboard always works.
        self.entity_id = f"{platform}.volley_{LEAGUE_SLUG}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name=LEAGUE_NAME,
            manufacturer=LEAGUE_ORGANISER,
            model="Volleyball league",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=LEAGUE_WEBSITE,
        )

    @property
    def available(self) -> bool:
        # Keep showing the cached season while TheSportsDB is down.
        return self.coordinator.data is not None

    @property
    def team_id(self) -> str | None:
        return self.coordinator.config_entry.options.get(CONF_TEAM) or None

    @property
    def team(self) -> Team | None:
        if (team_id := self.team_id) is None:
            return None
        return self.coordinator.data.current.teams.get(team_id)

    @staticmethod
    def now() -> datetime:
        return now()


class VolleyClockEntity(VolleyEntity):
    """An entity whose state moves with the clock, not only with coordinator updates."""

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_track_time_interval(self.hass, self._async_tick, CLOCK_TICK)
        )

    @callback
    def _async_tick(self, _now: datetime) -> None:
        self.async_write_ha_state()
