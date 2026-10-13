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
from .const import CONF_TEAM, OUTCOME_WON, SEASON_STATUSES
from .coordinator import NbaCoordinator
from .entity import NbaClockEntity
from .models import NbaData, NbaGame, game_day


@dataclass(frozen=True, kw_only=True)
class NbaSensorDescription(SensorEntityDescription):
    value_fn: Callable[[NbaData, datetime, str | None], Any]
    attrs_fn: Callable[[NbaData, datetime, str | None], dict[str, Any] | None]
    team: bool = False


def _season_attrs(data: NbaData, now: datetime, _team: str | None) -> dict[str, Any]:
    today = game_day(now)
    return {
        "season": data.season,
        "start": data.season_start.isoformat() if data.season_start else None,
        "end": data.season_end.isoformat() if data.season_end else None,
        "game_day": today.isoformat(),
        "games_today": len(data.games_on(today)),
        "live_games": len(data.live()),
        "logo": "https://a.espncdn.com/i/teamlogos/leagues/500/nba.png",
    }


def _games_attrs(games: list[NbaGame], day: Any) -> dict[str, Any]:
    return {
        "game_day": day.isoformat() if day else None,
        "games": [g.as_attributes() for g in games],
    }


def _last_day(data: NbaData, now: datetime) -> list[NbaGame]:
    return data.last_game_day(game_day(now))


def _standings_value(data: NbaData, conference: str) -> str | None:
    rows = data.standings.get(conference) or []
    if not rows or not any(r["wins"] or r["losses"] for r in rows):
        return None
    return rows[0]["team"]


def _standings_attrs(data: NbaData, conference: str) -> dict[str, Any]:
    return {"season": data.season, "standings": data.standings.get(conference) or []}


def _kickoff(game: NbaGame | None) -> datetime | None:
    return game.start if game else None


def _game_attrs(game: NbaGame | None, now: datetime) -> dict[str, Any] | None:
    if game is None:
        return None
    return {**game.as_attributes(), "days_until": (game.day - game_day(now)).days}


def _team_game_attrs(game: NbaGame | None, now: datetime, team_id: str | None) -> dict[str, Any] | None:
    if game is None or team_id is None:
        return None
    return {**game.team_attributes(team_id), "days_until": (game.day - game_day(now)).days}


def _team_last_value(data: NbaData, now: datetime, team_id: str | None) -> str | None:
    if team_id is None or (game := data.last_game(team_id)) is None:
        return None
    own, other = game.side(team_id), game.opponent(team_id)
    return f"{own.score}-{other.score}"


def _team_row_value(data: NbaData, team_id: str | None) -> int | None:
    if team_id is None or (row := data.team_row(team_id)) is None:
        return None
    return row["position"] if row["wins"] or row["losses"] else None


def _team_row_attrs(data: NbaData, now: datetime, team_id: str | None) -> dict[str, Any] | None:
    if team_id is None or (row := data.team_row(team_id)) is None:
        return None
    return {**row, "record": f"{row['wins']}-{row['losses']}", "season": data.season}


SENSORS: tuple[NbaSensorDescription, ...] = (
    NbaSensorDescription(
        key="season",
        icon="mdi:basketball",
        device_class=SensorDeviceClass.ENUM,
        options=SEASON_STATUSES,
        value_fn=lambda data, now, team: data.status,
        attrs_fn=_season_attrs,
    ),
    NbaSensorDescription(
        key="games_today",
        icon="mdi:basketball-hoop",
        value_fn=lambda data, now, team: len(data.games_on(game_day(now))),
        attrs_fn=lambda data, now, team: _games_attrs(data.games_on(game_day(now)), game_day(now)),
    ),
    NbaSensorDescription(
        key="last_results",
        icon="mdi:scoreboard",
        value_fn=lambda data, now, team: len(_last_day(data, now)),
        attrs_fn=lambda data, now, team: _games_attrs(
            games := _last_day(data, now), games[0].day if games else None
        ),
    ),
    NbaSensorDescription(
        key="next_game",
        icon="mdi:calendar-clock",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda data, now, team: _kickoff(data.next_game(now)),
        attrs_fn=lambda data, now, team: _game_attrs(data.next_game(now), now),
    ),
    NbaSensorDescription(
        key="east_standings",
        icon="mdi:podium",
        value_fn=lambda data, now, team: _standings_value(data, "east"),
        attrs_fn=lambda data, now, team: _standings_attrs(data, "east"),
    ),
    NbaSensorDescription(
        key="west_standings",
        icon="mdi:podium",
        value_fn=lambda data, now, team: _standings_value(data, "west"),
        attrs_fn=lambda data, now, team: _standings_attrs(data, "west"),
    ),
    NbaSensorDescription(
        key="team_next_game",
        icon="mdi:calendar-star",
        device_class=SensorDeviceClass.TIMESTAMP,
        team=True,
        value_fn=lambda data, now, team: _kickoff(data.next_game(now, team)),
        attrs_fn=lambda data, now, team: _team_game_attrs(data.next_game(now, team), now, team),
    ),
    NbaSensorDescription(
        key="team_last_game",
        icon="mdi:basketball",
        team=True,
        value_fn=_team_last_value,
        attrs_fn=lambda data, now, team: _team_game_attrs(data.last_game(team), now, team),
    ),
    NbaSensorDescription(
        key="team_standing",
        icon="mdi:numeric",
        team=True,
        value_fn=lambda data, now, team: _team_row_value(data, team),
        attrs_fn=_team_row_attrs,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: NbaCoordinator = entry.runtime_data
    has_team = bool(entry.options.get(CONF_TEAM))
    async_add_entities(NbaSensor(coordinator, d) for d in SENSORS if has_team or not d.team)


class NbaSensor(NbaClockEntity, SensorEntity):
    entity_description: NbaSensorDescription

    def __init__(self, coordinator: NbaCoordinator, description: NbaSensorDescription) -> None:
        super().__init__(coordinator, Platform.SENSOR, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data, self.now(), self.team_id)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        return self.entity_description.attrs_fn(self.coordinator.data, self.now(), self.team_id)

    @property
    def icon(self) -> str | None:
        if self.entity_description.key == "team_last_game" and self.team_id:
            game = self.coordinator.data.last_game(self.team_id)
            if game and (outcome := game.outcome_for(self.team_id)):
                return "mdi:trophy" if outcome == OUTCOME_WON else "mdi:emoticon-sad-outline"
        return self.entity_description.icon
