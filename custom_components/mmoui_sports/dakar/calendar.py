from __future__ import annotations
from datetime import date, datetime, timedelta
from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util
from .const import CONF_CALENDAR_REST_DAYS
from .coordinator import DakarCoordinator
from .entity import DakarClockEntity
from .models import DakarStage, parse_result

ONE_DAY = timedelta(days=1)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: DakarCoordinator = entry.runtime_data
    async_add_entities([DakarCalendar(coordinator, entry.options.get(CONF_CALENDAR_REST_DAYS, True))])


def _describe(stage: DakarStage) -> str:
    lines = []
    if stage.route:
        lines.append(stage.route)
    if stage.bivouac:
        lines.append(f"Bivouac: {stage.bivouac}")
    if stage.marathon:
        lines.append("Marathon stage: no outside assistance at the bivouac")
    if stage.is_cancelled:
        lines.append(f"Status: {stage.status}")
    for category, table in parse_result(stage.result).items():
        podium = ", ".join(f"{r['position']}. {r['name']}" for r in table["stage"][:3])
        lines.append(podium if category == "ALL" else f"{category}: {podium}")
    if stage.video:
        lines.append(f"Highlights: {stage.video}")
    return "\n".join(lines)


def _stage_event(stage: DakarStage) -> CalendarEvent:
    summary = stage.name if not stage.is_cancelled else f"{stage.name} ({stage.status})"
    if stage.bivouac:
        summary = f"{summary} · {stage.bivouac}"
    return CalendarEvent(
        start=stage.day,
        end=stage.day + ONE_DAY,
        summary=f"Dakar · {summary}",
        description=_describe(stage) or None,
        location=stage.location,
        uid=f"dakar_rally_{stage.id}",
    )


def _rest_day_event(day: date) -> CalendarEvent:
    return CalendarEvent(
        start=day,
        end=day + ONE_DAY,
        summary="Dakar · Rest day",
        uid=f"dakar_rally_rest_{day.isoformat()}",
    )


class DakarCalendar(DakarClockEntity, CalendarEntity):
    _attr_icon = "mdi:calendar-month"

    def __init__(self, coordinator: DakarCoordinator, include_rest_days: bool) -> None:
        super().__init__(coordinator, Platform.CALENDAR, "calendar")
        self._include_rest_days = include_rest_days

    def _events(self) -> list[CalendarEvent]:
        data = self.coordinator.data
        events = [_stage_event(s) for s in data.stages]
        if self._include_rest_days:
            events.extend(_rest_day_event(d) for d in data.rally.rest_days)
        return sorted(events, key=lambda e: e.start)

    @property
    def event(self) -> CalendarEvent | None:
        today = self.today()
        rally = self.coordinator.data.rally
        if stage := rally.stage_on(today):
            return _stage_event(stage)
        if self._include_rest_days and today in rally.rest_days:
            return _rest_day_event(today)
        stage = rally.next_stage(today)
        return _stage_event(stage) if stage else None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        return [
            e
            for e in self._events()
            if dt_util.start_of_local_day(e.start) < end_date
            and dt_util.start_of_local_day(e.end) > start_date
        ]
