from __future__ import annotations
from typing import Any
from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .coordinator import WecCoordinator
from .entity import WecClockEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: WecCoordinator = entry.runtime_data
    async_add_entities([WecRaceWeekendSensor(coordinator), WecSessionLiveSensor(coordinator)])


class WecRaceWeekendSensor(WecClockEntity, BinarySensorEntity):
    _attr_icon = "mdi:calendar-star"

    def __init__(self, coordinator: WecCoordinator) -> None:
        super().__init__(coordinator, Platform.BINARY_SENSOR, "race_weekend")

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.current_round(self.now()) is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        round_ = self.coordinator.data.current_round(self.now())
        if round_ is None:
            return None
        return {
            "event_name": round_.name,
            "round": round_.number,
            "circuit": round_.venue,
            "country": round_.country,
            "start": round_.start.isoformat(),
            "end": round_.end.isoformat(),
        }


class WecSessionLiveSensor(WecClockEntity, BinarySensorEntity):
    """On while a session with a confirmed start time is (estimated to be) running."""

    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(self, coordinator: WecCoordinator) -> None:
        super().__init__(coordinator, Platform.BINARY_SENSOR, "session_live")

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.live_session(self.now()) is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        session = self.coordinator.data.live_session(self.now())
        return session.as_attributes() if session else None
