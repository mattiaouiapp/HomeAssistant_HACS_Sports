from __future__ import annotations
from datetime import datetime
from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .const import CALENDAR_GAME_LENGTH, CONF_CALENDAR_TEAM_ONLY, CONF_TEAM, NAME
from .coordinator import NbaCoordinator
from .entity import NbaClockEntity
from .models import NbaGame


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: NbaCoordinator = entry.runtime_data
    team_only = bool(entry.options.get(CONF_TEAM)) and entry.options.get(CONF_CALENDAR_TEAM_ONLY, False)
    async_add_entities([NbaCalendar(coordinator, team_only)])


def _describe(game: NbaGame) -> str:
    lines = []
    if game.headline:
        lines.append(game.headline)
    if game.series:
        lines.append(game.series)
    if game.broadcasts:
        lines.append("TV: " + ", ".join(game.broadcasts))
    for side in (game.away, game.home):
        if side.leader and game.score:
            lines.append(f"{side.team.abbreviation}: {side.leader['player']} {side.leader['points']} pts")
    if game.is_cancelled:
        lines.append(f"Status: {game.detail}")
    return "\n".join(lines)


def _game_event(game: NbaGame) -> CalendarEvent:
    return CalendarEvent(
        start=game.start,
        end=game.start + CALENDAR_GAME_LENGTH,
        summary=f"{NAME} · {game.title}",
        description=_describe(game) or None,
        location=", ".join(p for p in (game.venue, game.city) if p) or None,
        uid=f"mmoui_sports_nba_{game.id}",
    )


class NbaCalendar(NbaClockEntity, CalendarEntity):
    _attr_icon = "mdi:calendar-month"

    def __init__(self, coordinator: NbaCoordinator, team_only: bool) -> None:
        super().__init__(coordinator, Platform.CALENDAR, "calendar")
        self._team_only = team_only

    def _games(self) -> list[NbaGame]:
        games = self.coordinator.data.all_games()
        if self._team_only and (team_id := self.team_id):
            games = [g for g in games if g.involves(team_id)]
        return games

    @property
    def event(self) -> CalendarEvent | None:
        now = self.now()
        game = next((g for g in self._games() if g.start + CALENDAR_GAME_LENGTH > now), None)
        return _game_event(game) if game else None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        return [
            _game_event(g)
            for g in self._games()
            if g.start < end_date and g.start + CALENDAR_GAME_LENGTH > start_date
        ]
