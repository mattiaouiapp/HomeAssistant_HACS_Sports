from __future__ import annotations
from typing import Any
from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .const import CONF_TEAM
from .coordinator import NbaCoordinator
from .entity import NbaClockEntity
from .models import NbaGame, game_day


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: NbaCoordinator = entry.runtime_data
    entities: list[NbaClockEntity] = [NbaGameLiveSensor(coordinator, "game_live")]
    if entry.options.get(CONF_TEAM):
        entities += [
            NbaGameTodaySensor(coordinator, "team_game_today"),
            NbaGameLiveSensor(coordinator, "team_game_live", team=True),
        ]
    async_add_entities(entities)


class NbaGameSensor(NbaClockEntity, BinarySensorEntity):
    def __init__(self, coordinator: NbaCoordinator, key: str, team: bool = False) -> None:
        super().__init__(coordinator, Platform.BINARY_SENSOR, key)
        self._for_team = team

    def _matches(self) -> list[NbaGame]:
        raise NotImplementedError

    def _relevant(self) -> list[NbaGame]:
        games = self._matches()
        if not self._for_team:
            return games
        team_id = self.team_id
        return [g for g in games if team_id and g.involves(team_id)]

    @property
    def is_on(self) -> bool:
        return bool(self._relevant())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"games": [g.as_attributes() for g in self._relevant()]}


class NbaGameTodaySensor(NbaGameSensor):
    """On for the favourite team's game day (US Eastern date, as the NBA counts it)."""

    _attr_icon = "mdi:calendar-today"

    def __init__(self, coordinator: NbaCoordinator, key: str) -> None:
        super().__init__(coordinator, key, team=True)

    def _matches(self) -> list[NbaGame]:
        today = game_day(self.now())
        return [g for g in self.coordinator.data.all_games() if g.day == today and not g.is_cancelled]


class NbaGameLiveSensor(NbaGameSensor):
    """On while ESPN reports a game in progress."""

    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def _matches(self) -> list[NbaGame]:
        return [g for g in self.coordinator.data.all_games() if g.is_live]
