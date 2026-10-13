from __future__ import annotations
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .const import RALLY_STATUSES
from .coordinator import DakarCoordinator
from .entity import DakarClockEntity
from .models import DakarData, DakarStage, parse_result


@dataclass(frozen=True, kw_only=True)
class DakarSensorDescription(SensorEntityDescription):
    value_fn: Callable[[DakarData, date], Any]
    attrs_fn: Callable[[DakarData, date], dict[str, Any] | None]


def _stage_attrs(stage: DakarStage | None, today: date) -> dict[str, Any] | None:
    if stage is None:
        return None
    return {**stage.as_attributes(), "days_until": (stage.day - today).days}


def _status_attrs(data: DakarData, today: date) -> dict[str, Any]:
    rally = data.rally
    current = rally.stage_on(today)
    league = data.league
    return {
        "season": data.season,
        "start": rally.start.isoformat() if rally.start else None,
        "end": rally.end.isoformat() if rally.end else None,
        "days_to_start": (rally.start - today).days if rally.start else None,
        "days_to_finish": (rally.end - today).days if rally.end else None,
        "total_stages": rally.total_stages,
        "stages_completed": rally.completed(today),
        "rest_days": [d.isoformat() for d in rally.rest_days],
        "current_stage": current.name if current else None,
        "bivouac": current.bivouac if current else None,
        "badge": league.get("strBadge"),
        "logo": league.get("strLogo"),
        "banner": league.get("strBanner"),
        "poster": league.get("strPoster"),
        "trophy": league.get("strTrophy"),
        "website": league.get("strWebsite"),
    }


def _last_stage_attrs(data: DakarData, today: date) -> dict[str, Any] | None:
    stage = data.last_stage(today)
    if stage is None:
        return None
    results = parse_result(stage.result)
    return {
        **stage.as_attributes(),
        "results": results,
        "stage_winners": {c: t["stage"][0] for c, t in results.items() if t["stage"]},
        "overall_leaders": {c: t["general"][0] for c, t in results.items() if t["general"]},
        # Unstructured results (a written summary) are only available as text.
        "result_text": None if results else stage.result,
        "description": stage.description,
    }


def _completed_attrs(data: DakarData, today: date) -> dict[str, Any]:
    rally = data.rally
    return {
        "season": data.season,
        "total_stages": rally.total_stages,
        "stages": [s.summary(today) for s in rally.stages],
        "rest_days": [d.isoformat() for d in rally.rest_days],
    }


def _name(stage: DakarStage | None) -> str | None:
    return stage.name if stage else None


def _day(stage: DakarStage | None) -> date | None:
    return stage.day if stage else None


SENSORS: tuple[DakarSensorDescription, ...] = (
    DakarSensorDescription(
        key="rally_status",
        icon="mdi:flag-variant",
        device_class=SensorDeviceClass.ENUM,
        options=RALLY_STATUSES,
        value_fn=lambda data, today: data.rally.status(today),
        attrs_fn=_status_attrs,
    ),
    DakarSensorDescription(
        key="rally_start",
        icon="mdi:calendar-start",
        device_class=SensorDeviceClass.DATE,
        value_fn=lambda data, today: data.rally.start,
        attrs_fn=lambda data, today: {
            "season": data.season,
            "end": data.rally.end.isoformat() if data.rally.end else None,
            "days_to_start": (data.rally.start - today).days if data.rally.start else None,
        },
    ),
    DakarSensorDescription(
        key="next_stage",
        icon="mdi:map-marker-path",
        device_class=SensorDeviceClass.DATE,
        value_fn=lambda data, today: _day(data.rally.next_stage(today)),
        attrs_fn=lambda data, today: _stage_attrs(data.rally.next_stage(today), today),
    ),
    DakarSensorDescription(
        key="current_stage",
        icon="mdi:motorbike",
        value_fn=lambda data, today: _name(data.rally.stage_on(today)),
        attrs_fn=lambda data, today: _stage_attrs(data.rally.stage_on(today), today),
    ),
    DakarSensorDescription(
        key="last_stage",
        icon="mdi:flag-checkered",
        value_fn=lambda data, today: _name(data.last_stage(today)),
        attrs_fn=_last_stage_attrs,
    ),
    DakarSensorDescription(
        key="stages_completed",
        icon="mdi:counter",
        value_fn=lambda data, today: data.rally.completed(today),
        attrs_fn=_completed_attrs,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: DakarCoordinator = entry.runtime_data
    async_add_entities(DakarSensor(coordinator, description) for description in SENSORS)


class DakarSensor(DakarClockEntity, SensorEntity):
    entity_description: DakarSensorDescription

    def __init__(self, coordinator: DakarCoordinator, description: DakarSensorDescription) -> None:
        super().__init__(coordinator, Platform.SENSOR, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data, self.today())

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        return self.entity_description.attrs_fn(self.coordinator.data, self.today())
