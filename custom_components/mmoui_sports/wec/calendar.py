from __future__ import annotations
from datetime import date, datetime, timedelta
from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util
from .const import CONF_CALENDAR_SESSIONS, KIND_RACE
from .coordinator import WecCoordinator
from .entity import WecClockEntity
from .models import WecEvent, parse_result


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: WecCoordinator = entry.runtime_data
    async_add_entities([WecCalendar(coordinator, entry.options.get(CONF_CALENDAR_SESSIONS, True))])


def _describe(event: WecEvent) -> str:
    lines = []
    if event.round is not None and event.round < 100:
        lines.append(f"Round {event.round}")
    if not event.time_confirmed:
        lines.append("Start time not announced yet")
    if event.is_cancelled:
        lines.append(f"Status: {event.status}")
    results, _ = parse_result(event.result)
    for cls, rows in results.items():
        lines.append(f"{cls}: " + ", ".join(f"{r['position']}. #{r['car_number']} {r['team']}" for r in rows[:3]))
    return "\n".join(lines)


def _to_calendar_event(event: WecEvent) -> CalendarEvent:
    if event.time_confirmed:
        start: datetime | date = event.start
        end: datetime | date = event.end
    else:
        start = event.start.date()
        end = start + timedelta(days=1)
    summary = event.name if not event.is_cancelled else f"{event.name} ({event.status})"
    return CalendarEvent(
        start=start,
        end=end,
        summary=f"WEC · {summary}",
        description=_describe(event) or None,
        location=event.location,
        uid=f"fia_wec_{event.id}",
    )


class WecCalendar(WecClockEntity, CalendarEntity):
    _attr_icon = "mdi:calendar-month"

    def __init__(self, coordinator: WecCoordinator, include_sessions: bool) -> None:
        super().__init__(coordinator, Platform.CALENDAR, "calendar")
        self._include_sessions = include_sessions

    def _events(self) -> list[WecEvent]:
        events = self.coordinator.data.events
        if self._include_sessions:
            return events
        return [e for e in events if e.kind == KIND_RACE]

    @property
    def event(self) -> CalendarEvent | None:
        now = self.now()
        upcoming = next(
            (e for e in self._events() if e.end > now and not e.is_cancelled), None
        )
        return _to_calendar_event(upcoming) if upcoming else None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        start_utc = dt_util.as_utc(start_date)
        end_utc = dt_util.as_utc(end_date)
        return [
            _to_calendar_event(e)
            for e in self._events()
            if e.start < end_utc and e.end > start_utc
        ]
