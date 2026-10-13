from __future__ import annotations
from typing import Any
from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .coordinator import DakarCoordinator
from .entity import DakarClockEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: DakarCoordinator = entry.runtime_data
    async_add_entities([DakarRallyInProgressSensor(coordinator), DakarStageTodaySensor(coordinator)])


class DakarRallyInProgressSensor(DakarClockEntity, BinarySensorEntity):
    """On from the Prologue to the finish, rest days included."""

    _attr_icon = "mdi:calendar-star"

    def __init__(self, coordinator: DakarCoordinator) -> None:
        super().__init__(coordinator, Platform.BINARY_SENSOR, "rally_in_progress")

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.rally.in_progress(self.today())

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        rally = self.coordinator.data.rally
        if rally.start is None:
            return None
        return {
            "season": rally.season,
            "start": rally.start.isoformat(),
            "end": rally.end.isoformat(),
            "total_stages": rally.total_stages,
            "stages_completed": rally.completed(self.today()),
        }


class DakarStageTodaySensor(DakarClockEntity, BinarySensorEntity):
    """On during the day of a stage (or the Prologue)."""

    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(self, coordinator: DakarCoordinator) -> None:
        super().__init__(coordinator, Platform.BINARY_SENSOR, "stage_today")

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.rally.stage_on(self.today()) is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        stage = self.coordinator.data.rally.stage_on(self.today())
        return stage.as_attributes() if stage else None
