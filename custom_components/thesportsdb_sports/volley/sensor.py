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
from homeassistant.util import dt as dt_util
from .const import CONF_TEAM, OUTCOME_LOST, OUTCOME_WON, SEASON_STATUSES
from .coordinator import VolleyCoordinator
from .entity import VolleyClockEntity
from .models import VolleyData, VolleyMatch, VolleyRound


@dataclass(frozen=True, kw_only=True)
class VolleySensorDescription(SensorEntityDescription):
    value_fn: Callable[[VolleyData, datetime, str | None], Any]
    attrs_fn: Callable[[VolleyData, datetime, str | None], dict[str, Any] | None]
    team: bool = False


def _kickoff(match: VolleyMatch | None) -> datetime | None:
    if match is None:
        return None
    return match.start or dt_util.start_of_local_day(match.day)


def _match_attrs(match: VolleyMatch | None, now: datetime) -> dict[str, Any] | None:
    if match is None:
        return None
    return {**match.as_attributes(now), "days_until": (match.day - now.date()).days}


def _team_match_attrs(match: VolleyMatch | None, now: datetime, team_id: str | None) -> dict[str, Any] | None:
    if match is None or team_id is None:
        return None
    return {**match.team_attributes(team_id, now), "days_until": (match.day - now.date()).days}


def _round_attrs(rnd: VolleyRound | None, now: datetime) -> dict[str, Any] | None:
    if rnd is None:
        return None
    return {**rnd.summary(now), "days_until": (rnd.day - now.date()).days}


def _round_number(rnd: VolleyRound | None) -> int | None:
    return rnd.number if rnd else None


def _season_attrs(data: VolleyData, now: datetime, _team: str | None) -> dict[str, Any]:
    season = data.current
    today = now.date()
    league = data.league
    played = [m for m in season.active if m.has_result]
    return {
        "season": data.season,
        "start": season.start.isoformat() if season.start else None,
        "end": season.end.isoformat() if season.end else None,
        "regular_season_end": season.regular_season_end.isoformat() if season.regular_season_end else None,
        "days_to_start": (season.start - today).days if season.start else None,
        "teams": len(season.teams),
        "total_rounds": season.total_rounds,
        "rounds_played": season.rounds_played(today),
        "matches_known": len(season.active),
        "matches_played": len(played),
        "matches_today": len(season.matches_on(today)),
        "live_matches": len(season.live(now)),
        "badge": league.get("strBadge"),
        "logo": league.get("strLogo"),
        "banner": league.get("strBanner"),
        "poster": league.get("strPoster"),
        "trophy": league.get("strTrophy"),
        "website": league.get("strWebsite"),
    }


def _leader(data: VolleyData) -> str | None:
    table = data.current.standings()
    if not table or not table[0]["played"]:
        return None
    return table[0]["team"]


def _standings_attrs(data: VolleyData, now: datetime, _team: str | None) -> dict[str, Any]:
    season = data.current
    return {
        "season": data.season,
        "rounds_played": season.rounds_played(now.date()),
        "total_rounds": season.total_rounds,
        "standings": season.standings(),
    }


def _team_row(data: VolleyData, team_id: str | None) -> dict[str, Any] | None:
    """The team's line of the table, once the season has results."""
    if team_id is None or _leader(data) is None:
        return None
    return next((r for r in data.current.standings() if r["team_id"] == team_id), None)


def _team_position_attrs(data: VolleyData, now: datetime, team_id: str | None) -> dict[str, Any] | None:
    if (row := _team_row(data, team_id)) is None:
        return None
    table = data.current.standings()
    above = table[row["position"] - 2] if row["position"] > 1 else None
    return {
        **row,
        "season": data.season,
        "teams": len(table),
        "points_behind_leader": table[0]["points"] - row["points"],
        "points_behind_next": above["points"] - row["points"] if above else None,
        "matches": [m.summary(now) for m in data.current.team_matches(team_id)],
    }


def _team_last_value(data: VolleyData, now: datetime, team_id: str | None) -> str | None:
    if team_id is None or (match := data.last_match(team_id)) is None:
        return None
    won, lost = match.sets_for(team_id)
    return f"{won}-{lost}"


def _playoffs_attrs(data: VolleyData, now: datetime, _team: str | None) -> dict[str, Any]:
    return {"season": data.season, "series": data.current.playoff_series(now)}


SENSORS: tuple[VolleySensorDescription, ...] = (
    VolleySensorDescription(
        key="season",
        icon="mdi:volleyball",
        device_class=SensorDeviceClass.ENUM,
        options=SEASON_STATUSES,
        value_fn=lambda data, now, team: data.current.status(now),
        attrs_fn=_season_attrs,
    ),
    VolleySensorDescription(
        key="standings",
        icon="mdi:podium",
        value_fn=lambda data, now, team: _leader(data),
        attrs_fn=_standings_attrs,
    ),
    VolleySensorDescription(
        key="next_round",
        icon="mdi:calendar-arrow-right",
        value_fn=lambda data, now, team: _round_number(data.current.next_round(now.date())),
        attrs_fn=lambda data, now, team: _round_attrs(data.current.next_round(now.date()), now),
    ),
    VolleySensorDescription(
        key="last_round",
        icon="mdi:calendar-check",
        value_fn=lambda data, now, team: _round_number(data.current.last_round(now.date())),
        attrs_fn=lambda data, now, team: _round_attrs(data.current.last_round(now.date()), now),
    ),
    VolleySensorDescription(
        key="next_match",
        icon="mdi:whistle",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda data, now, team: _kickoff(data.current.next_match(now)),
        attrs_fn=lambda data, now, team: _match_attrs(data.current.next_match(now), now),
    ),
    VolleySensorDescription(
        key="last_result",
        icon="mdi:scoreboard",
        value_fn=lambda data, now, team: (m.title if (m := data.last_match()) else None),
        attrs_fn=lambda data, now, team: _match_attrs(data.last_match(), now),
    ),
    VolleySensorDescription(
        key="playoffs",
        icon="mdi:tournament",
        value_fn=lambda data, now, team: sum(1 for m in data.current.playoffs if m.has_result),
        attrs_fn=_playoffs_attrs,
    ),
    VolleySensorDescription(
        key="team_position",
        icon="mdi:numeric",
        team=True,
        value_fn=lambda data, now, team: (r["position"] if (r := _team_row(data, team)) else None),
        attrs_fn=_team_position_attrs,
    ),
    VolleySensorDescription(
        key="team_next_match",
        icon="mdi:calendar-star",
        device_class=SensorDeviceClass.TIMESTAMP,
        team=True,
        value_fn=lambda data, now, team: _kickoff(data.current.next_match(now, team)),
        attrs_fn=lambda data, now, team: _team_match_attrs(data.current.next_match(now, team), now, team),
    ),
    VolleySensorDescription(
        key="team_last_match",
        icon="mdi:volleyball",
        team=True,
        value_fn=_team_last_value,
        attrs_fn=lambda data, now, team: _team_match_attrs(data.last_match(team), now, team),
    ),
)

# Outcome icons for the favourite team's last match.
_OUTCOME_ICONS = {OUTCOME_WON: "mdi:trophy", OUTCOME_LOST: "mdi:emoticon-sad-outline"}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: VolleyCoordinator = entry.runtime_data
    has_team = bool(entry.options.get(CONF_TEAM))
    async_add_entities(
        VolleySensor(coordinator, description)
        for description in SENSORS
        if has_team or not description.team
    )


class VolleySensor(VolleyClockEntity, SensorEntity):
    entity_description: VolleySensorDescription

    def __init__(self, coordinator: VolleyCoordinator, description: VolleySensorDescription) -> None:
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
        if self.entity_description.key == "team_last_match" and self.team_id:
            match = self.coordinator.data.last_match(self.team_id)
            if match and (outcome := match.outcome_for(self.team_id)):
                return _OUTCOME_ICONS[outcome]
        return self.entity_description.icon
