from __future__ import annotations
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .coordinator import WecCoordinator
from .entity import WecClockEntity
from .models import WecData, WecEvent, parse_result


@dataclass(frozen=True, kw_only=True)
class WecSensorDescription(SensorEntityDescription):
    value_fn: Callable[[WecData, datetime], Any]
    attrs_fn: Callable[[WecData, datetime], dict[str, Any] | None]


def _round_sessions(data: WecData, event: WecEvent) -> list[dict[str, Any]]:
    round_ = data.round_of(event)
    if round_ is None:
        return []
    return [
        {
            "name": e.name,
            "kind": e.kind,
            "start": e.start.isoformat(),
            "time_confirmed": e.time_confirmed,
            "status": e.status,
        }
        for e in round_.events
    ]


def _event_attrs(data: WecData, event: WecEvent | None) -> dict[str, Any] | None:
    if event is None:
        return None
    return {
        **event.as_attributes(),
        "poster": event.poster,
        "thumb": event.thumb,
        "banner": event.banner,
        "track_map": event.map,
        "sessions": _round_sessions(data, event),
    }


def _next_race_value(data: WecData, now: datetime) -> datetime | None:
    race = data.next_race(now)
    return race.start if race else None


def _next_session_value(data: WecData, now: datetime) -> datetime | None:
    session = data.next_session(now)
    return session.start if session else None


def _next_session_attrs(data: WecData, now: datetime) -> dict[str, Any] | None:
    session = data.next_session(now)
    return session.as_attributes() if session else None


def _last_race_value(data: WecData, now: datetime) -> str | None:
    race = data.last_race(now)
    return race.name if race else None


def _last_race_attrs(data: WecData, now: datetime) -> dict[str, Any] | None:
    race = data.last_race(now)
    if race is None:
        return None
    results, standings = parse_result(race.result)
    return {
        **_event_attrs(data, race),
        "results": results,
        "winners": {cls: rows[0] for cls, rows in results.items()},
        "standings": standings,
    }


def _winner_value(data: WecData, now: datetime) -> str | None:
    race = data.last_race(now)
    if race is None:
        return None
    results, _ = parse_result(race.result)
    if not results:
        return None
    # The first class listed is the top class (Hypercar).
    winner = next(iter(results.values()))[0]
    return f"#{winner['car_number']} {winner['team']}"


def _winner_attrs(data: WecData, now: datetime) -> dict[str, Any] | None:
    race = data.last_race(now)
    if race is None:
        return None
    results, _ = parse_result(race.result)
    return {
        "race": race.name,
        "date": race.start.date().isoformat(),
        **{
            cls.lower(): f"#{rows[0]['car_number']} {rows[0]['team']}"
            for cls, rows in results.items()
        },
    }


def _completed_value(data: WecData, now: datetime) -> int:
    return sum(1 for r in data.season_races() if r.end <= now and not r.is_cancelled)


def _completed_attrs(data: WecData, now: datetime) -> dict[str, Any]:
    races = data.season_races()
    return {
        "season": data.season,
        "total_races": len(races),
        "races": [
            {
                "round": r.round,
                "name": r.name,
                "date": r.start.date().isoformat(),
                "circuit": r.venue,
                "country": r.country,
                "status": r.status,
                "finished": r.end <= now,
                "cancelled": r.is_cancelled,
            }
            for r in races
        ],
    }


SENSORS: tuple[WecSensorDescription, ...] = (
    WecSensorDescription(
        key="next_race",
        icon="mdi:flag-checkered",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_next_race_value,
        attrs_fn=lambda data, now: _event_attrs(data, data.next_race(now)),
    ),
    WecSensorDescription(
        key="next_session",
        icon="mdi:timer-outline",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_next_session_value,
        attrs_fn=_next_session_attrs,
    ),
    WecSensorDescription(
        key="last_race",
        icon="mdi:trophy-outline",
        value_fn=_last_race_value,
        attrs_fn=_last_race_attrs,
    ),
    WecSensorDescription(
        key="last_race_winner",
        icon="mdi:trophy",
        value_fn=_winner_value,
        attrs_fn=_winner_attrs,
    ),
    WecSensorDescription(
        key="races_completed",
        icon="mdi:counter",
        value_fn=_completed_value,
        attrs_fn=_completed_attrs,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: WecCoordinator = entry.runtime_data
    async_add_entities(WecSensor(coordinator, description) for description in SENSORS)


class WecSensor(WecClockEntity, SensorEntity):
    entity_description: WecSensorDescription

    def __init__(self, coordinator: WecCoordinator, description: WecSensorDescription) -> None:
        super().__init__(coordinator, Platform.SENSOR, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data, self.now())

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        return self.entity_description.attrs_fn(self.coordinator.data, self.now())
