from __future__ import annotations
from datetime import datetime, timedelta
from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util
from .const import CALENDAR_MATCH_LENGTH, CONF_CALENDAR_TEAM_ONLY, CONF_TEAM, LEAGUE_NAME
from .coordinator import VolleyCoordinator
from .entity import VolleyClockEntity
from .models import VolleyMatch

ONE_DAY = timedelta(days=1)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: VolleyCoordinator = entry.runtime_data
    team_only = bool(entry.options.get(CONF_TEAM)) and entry.options.get(CONF_CALENDAR_TEAM_ONLY, False)
    async_add_entities([VolleyCalendar(coordinator, team_only)])


def _describe(match: VolleyMatch) -> str:
    lines = ["Playoffs" if match.playoff else f"Round {match.round}"]
    if match.sets:
        lines.append("Sets: " + ", ".join(f"{s['home']}-{s['away']}" for s in match.sets))
    if match.is_cancelled:
        lines.append(f"Status: {match.status}")
    if match.video:
        lines.append(f"Highlights: {match.video}")
    return "\n".join(lines)


def _match_event(match: VolleyMatch, prefix: str) -> CalendarEvent:
    summary = match.title if not match.is_cancelled else f"{match.title} ({match.status})"
    if match.start:
        start, end = match.start, match.start + CALENDAR_MATCH_LENGTH
    else:
        # No start time on TheSportsDB: an all-day event.
        start, end = match.day, match.day + ONE_DAY
    return CalendarEvent(
        start=start,
        end=end,
        summary=f"{prefix} · {summary}",
        description=_describe(match),
        location=match.venue,
        uid=f"volley_serie_a_{match.id}",
    )


def _bounds(event: CalendarEvent) -> tuple[datetime, datetime]:
    if isinstance(event.start, datetime):
        return event.start, event.end
    return dt_util.start_of_local_day(event.start), dt_util.start_of_local_day(event.end)


class VolleyCalendar(VolleyClockEntity, CalendarEntity):
    _attr_icon = "mdi:calendar-month"

    def __init__(self, coordinator: VolleyCoordinator, team_only: bool) -> None:
        super().__init__(coordinator, Platform.CALENDAR, "calendar")
        self._team_only = team_only

    def _matches(self) -> list[VolleyMatch]:
        matches = self.coordinator.data.current.matches
        if self._team_only and (team_id := self.team_id):
            matches = [m for m in matches if m.involves(team_id)]
        return matches

    def _events(self) -> list[CalendarEvent]:
        return [_match_event(m, LEAGUE_NAME) for m in self._matches()]

    @property
    def event(self) -> CalendarEvent | None:
        now = self.now()
        # The match being played, else the next one.
        for event in self._events():
            if _bounds(event)[1] > now:
                return event
        return None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        return [
            e
            for e in self._events()
            if (bounds := _bounds(e))[0] < end_date and bounds[1] > start_date
        ]
