from __future__ import annotations
from typing import Any
from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .const import CONF_TEAM
from .coordinator import VolleyCoordinator
from .entity import VolleyClockEntity
from .models import VolleyMatch


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: VolleyCoordinator = entry.runtime_data
    entities: list[VolleyClockEntity] = [
        VolleyMatchTodaySensor(coordinator, "match_today"),
        VolleyMatchLiveSensor(coordinator, "match_live"),
    ]
    if entry.options.get(CONF_TEAM):
        entities += [
            VolleyMatchTodaySensor(coordinator, "team_match_today", team=True),
            VolleyMatchLiveSensor(coordinator, "team_match_live", team=True),
        ]
    async_add_entities(entities)


class VolleyMatchSensor(VolleyClockEntity, BinarySensorEntity):
    def __init__(self, coordinator: VolleyCoordinator, key: str, team: bool = False) -> None:
        super().__init__(coordinator, Platform.BINARY_SENSOR, key)
        self._for_team = team

    def _matches(self) -> list[VolleyMatch]:
        raise NotImplementedError

    def _relevant(self) -> list[VolleyMatch]:
        matches = self._matches()
        if not self._for_team:
            return matches
        team_id = self.team_id
        return [m for m in matches if team_id and m.involves(team_id)]

    @property
    def is_on(self) -> bool:
        return bool(self._relevant())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        now = self.now()
        return {"matches": [m.summary(now) for m in self._relevant()]}


class VolleyMatchTodaySensor(VolleyMatchSensor):
    """On for the whole day of a match."""

    _attr_icon = "mdi:calendar-today"

    def _matches(self) -> list[VolleyMatch]:
        return self.coordinator.data.current.matches_on(self.now().date())


class VolleyMatchLiveSensor(VolleyMatchSensor):
    """On from the start time until the result is in; `matches` carries the live scores."""

    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def _matches(self) -> list[VolleyMatch]:
        return self.coordinator.data.current.live(self.now())
