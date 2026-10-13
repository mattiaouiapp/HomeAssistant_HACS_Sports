"""Turns ESPN scoreboards, schedules and standings into NBA games and tables."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any
from homeassistant.util import dt as dt_util
from .const import (
    CANCELLED_STATUSES,
    GAME_DAY_TZ,
    GAME_FINAL,
    GAME_LIVE,
    GAME_PRE,
    OUTCOME_LOST,
    OUTCOME_WON,
    SEASON_TYPE_STATUS,
)


def _int(value: Any) -> int | None:
    if isinstance(value, dict):
        value = value.get("value", value.get("displayValue"))
    try:
        return int(float(value)) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _logo(team: dict[str, Any]) -> str | None:
    if team.get("logo"):
        return team["logo"]
    logos = team.get("logos") or []
    return logos[0].get("href") if logos else None


def _record(competitor: dict[str, Any]) -> str | None:
    """The overall record: "records" on scoreboards, "record" on schedules."""
    for item in competitor.get("records") or []:
        if item.get("type") == "total" or item.get("name") == "overall":
            return item.get("summary")
    for item in competitor.get("record") or []:
        if item.get("type") == "total":
            return item.get("displayValue")
    return None


def game_day(moment: datetime) -> date:
    """The NBA game day a moment belongs to."""
    return moment.astimezone(GAME_DAY_TZ).date()


@dataclass(frozen=True)
class NbaTeam:
    id: str
    abbreviation: str
    name: str
    short_name: str
    logo: str | None
    color: str | None

    @classmethod
    def from_api(cls, team: dict[str, Any]) -> NbaTeam:
        return cls(
            id=str(team.get("id")),
            abbreviation=team.get("abbreviation") or "",
            name=team.get("displayName") or team.get("name") or "",
            short_name=team.get("shortDisplayName") or team.get("name") or "",
            logo=_logo(team),
            color=f"#{team['color']}" if team.get("color") else None,
        )


@dataclass
class NbaSide:
    team: NbaTeam
    home: bool
    score: int | None
    record: str | None
    quarters: list[int]
    leader: dict[str, Any] | None
    winner: bool | None

    @classmethod
    def from_api(cls, competitor: dict[str, Any]) -> NbaSide:
        leader = None
        for category in competitor.get("leaders") or []:
            if category.get("name") == "points" and category.get("leaders"):
                top = category["leaders"][0]
                leader = {
                    "player": (top.get("athlete") or {}).get("displayName"),
                    "points": top.get("displayValue"),
                }
                break
        return cls(
            team=NbaTeam.from_api(competitor.get("team") or {}),
            home=competitor.get("homeAway") == "home",
            score=_int(competitor.get("score")),
            record=_record(competitor),
            quarters=[q for q in (_int(ls) for ls in competitor.get("linescores") or []) if q is not None],
            leader=leader,
            winner=competitor.get("winner"),
        )


@dataclass
class NbaGame:
    id: str
    start: datetime
    state: str
    status: str
    detail: str | None
    period: int | None
    clock: str | None
    season_type: int | None
    home: NbaSide
    away: NbaSide
    venue: str | None
    city: str | None
    broadcasts: list[str]
    headline: str | None
    series: str | None

    @classmethod
    def from_api(cls, event: dict[str, Any]) -> NbaGame | None:
        competition = (event.get("competitions") or [{}])[0]
        start = dt_util.parse_datetime(competition.get("date") or event.get("date") or "")
        sides = [NbaSide.from_api(c) for c in competition.get("competitors") or []]
        home = next((s for s in sides if s.home), None)
        away = next((s for s in sides if not s.home), None)
        if start is None or home is None or away is None:
            return None
        status = competition.get("status") or event.get("status") or {}
        status_type = status.get("type") or {}
        venue = competition.get("venue") or {}
        broadcasts = [n for b in competition.get("broadcasts") or [] for n in b.get("names") or []]
        if not broadcasts:
            broadcasts = [
                b.get("media", {}).get("shortName") for b in competition.get("broadcasts") or [] if b.get("media")
            ]
        notes = competition.get("notes") or []
        return cls(
            id=str(event.get("id")),
            start=start,
            state=status_type.get("state") or GAME_PRE,
            status=status_type.get("name") or "",
            detail=status_type.get("shortDetail") or status_type.get("detail"),
            period=status.get("period"),
            clock=status.get("displayClock"),
            season_type=(event.get("season") or {}).get("type") or (competition.get("type") or {}).get("id"),
            home=home,
            away=away,
            venue=venue.get("fullName"),
            city=(venue.get("address") or {}).get("city"),
            broadcasts=[b for b in broadcasts if b],
            headline=notes[0].get("headline") if notes else None,
            series=(competition.get("series") or {}).get("summary"),
        )

    @property
    def day(self) -> date:
        return game_day(self.start)

    @property
    def is_live(self) -> bool:
        return self.state == GAME_LIVE

    @property
    def is_final(self) -> bool:
        return self.state == GAME_FINAL and not self.is_cancelled

    @property
    def is_cancelled(self) -> bool:
        return self.status in CANCELLED_STATUSES

    @property
    def score(self) -> str | None:
        if self.home.score is None or self.away.score is None or self.state == GAME_PRE:
            return None
        return f"{self.away.score}-{self.home.score}"

    @property
    def title(self) -> str:
        """Away team first, as the NBA does: "GS 104 @ LAL 110"."""
        if self.score is None:
            return f"{self.away.team.abbreviation} @ {self.home.team.abbreviation}"
        return f"{self.away.team.abbreviation} {self.away.score} @ {self.home.team.abbreviation} {self.home.score}"

    @property
    def winner(self) -> NbaTeam | None:
        if not self.is_final or self.home.score is None or self.away.score is None:
            return None
        return self.home.team if self.home.score > self.away.score else self.away.team

    def involves(self, team_id: str) -> bool:
        return team_id in (self.home.team.id, self.away.team.id)

    def side(self, team_id: str) -> NbaSide:
        return self.home if self.home.team.id == team_id else self.away

    def opponent(self, team_id: str) -> NbaSide:
        return self.away if self.home.team.id == team_id else self.home

    def outcome_for(self, team_id: str) -> str | None:
        if (winner := self.winner) is None:
            return None
        return OUTCOME_WON if winner.id == team_id else OUTCOME_LOST

    def summary(self) -> dict[str, Any]:
        return {
            "event_id": self.id,
            "start": self.start.isoformat(),
            "game_day": self.day.isoformat(),
            "state": self.state,
            "status": self.detail,
            "period": self.period,
            "clock": self.clock,
            "live": self.is_live,
            "final": self.is_final,
            "away_team": self.away.team.name,
            "away_abbreviation": self.away.team.abbreviation,
            "away_logo": self.away.team.logo,
            "away_score": self.away.score if self.score else None,
            "away_record": self.away.record,
            "home_team": self.home.team.name,
            "home_abbreviation": self.home.team.abbreviation,
            "home_logo": self.home.team.logo,
            "home_score": self.home.score if self.score else None,
            "home_record": self.home.record,
            "title": self.title,
            "venue": self.venue,
            "broadcasts": self.broadcasts,
            "headline": self.headline,
            "series": self.series,
        }

    def as_attributes(self) -> dict[str, Any]:
        return {
            **self.summary(),
            "city": self.city,
            "away_quarters": self.away.quarters,
            "home_quarters": self.home.quarters,
            "away_leader": self.away.leader,
            "home_leader": self.home.leader,
            "winner": self.winner.name if self.winner else None,
        }

    def team_attributes(self, team_id: str) -> dict[str, Any]:
        own, other = self.side(team_id), self.opponent(team_id)
        return {
            **self.as_attributes(),
            "team": own.team.name,
            "team_logo": own.team.logo,
            "team_score": own.score if self.score else None,
            "opponent": other.team.name,
            "opponent_abbreviation": other.team.abbreviation,
            "opponent_logo": other.team.logo,
            "opponent_score": other.score if self.score else None,
            "opponent_record": other.record,
            "home": own.home,
            "outcome": self.outcome_for(team_id),
        }


def _stats(entry: dict[str, Any]) -> dict[str, Any]:
    return {s.get("name"): s for s in entry.get("stats") or []}


def _value(stats: dict[str, Any], name: str) -> Any:
    stat = stats.get(name) or {}
    return stat.get("value")


def _display(stats: dict[str, Any], name: str) -> str | None:
    stat = stats.get(name) or {}
    return stat.get("displayValue") or stat.get("summary")


def parse_standings(data: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """{"east": [...], "west": [...]} ordered by playoff seed (by winning % before games)."""
    tables: dict[str, list[dict[str, Any]]] = {}
    for conference in data.get("children") or []:
        key = "east" if "east" in (conference.get("name") or "").lower() else "west"
        rows = []
        for entry in (conference.get("standings") or {}).get("entries") or []:
            stats = _stats(entry)
            team = NbaTeam.from_api(entry.get("team") or {})
            rows.append(
                {
                    "team": team.name,
                    "team_id": team.id,
                    "abbreviation": team.abbreviation,
                    "logo": team.logo,
                    "seed": _int(_value(stats, "playoffSeed")),
                    "wins": _int(_value(stats, "wins")) or 0,
                    "losses": _int(_value(stats, "losses")) or 0,
                    "win_percent": _display(stats, "winPercent"),
                    "games_behind": _display(stats, "gamesBehind"),
                    "streak": _display(stats, "streak"),
                    "last_ten": _display(stats, "Last Ten Games"),
                    "home": _display(stats, "Home"),
                    "road": _display(stats, "Road"),
                    "conference": _display(stats, "vs. Conf."),
                    "points_for": _display(stats, "avgPointsFor"),
                    "points_against": _display(stats, "avgPointsAgainst"),
                    "differential": _display(stats, "differential"),
                }
            )
        played = any(r["wins"] or r["losses"] for r in rows)
        rows.sort(
            key=lambda r: (r["seed"] or 99, r["team"])
            if played and any(r["seed"] for r in rows)
            else (-(r["wins"] / max(r["wins"] + r["losses"], 1)), r["team"])
        )
        for position, row in enumerate(rows, start=1):
            row["position"] = position
        tables[key] = rows
    return tables


@dataclass
class NbaData:
    season: str | None
    season_type: int | None
    season_start: date | None
    season_end: date | None
    games: list[NbaGame]
    standings: dict[str, list[dict[str, Any]]]
    teams: dict[str, NbaTeam]
    team_games: list[NbaGame] = field(default_factory=list)

    @property
    def status(self) -> str | None:
        return SEASON_TYPE_STATUS.get(self.season_type) if self.season_type else None

    def games_on(self, day: date) -> list[NbaGame]:
        return [g for g in self.games if g.day == day and not g.is_cancelled]

    def live(self) -> list[NbaGame]:
        return [g for g in self.games if g.is_live]

    def all_games(self) -> list[NbaGame]:
        """League games and the favourite team's season, without duplicates."""
        games = {g.id: g for g in self.team_games}
        games.update({g.id: g for g in self.games})
        return sorted(games.values(), key=lambda g: g.start)

    def next_game(self, now: datetime, team_id: str | None = None) -> NbaGame | None:
        """The game being played, else the next one."""
        games = self.all_games() if team_id else self.games
        for game in games:
            if team_id and not game.involves(team_id):
                continue
            if game.is_cancelled or game.is_final:
                continue
            if game.is_live or game.start >= now or game.state == "pre":
                return game
        return None

    def last_game(self, team_id: str | None = None) -> NbaGame | None:
        games = self.all_games() if team_id else self.games
        done = [g for g in games if g.is_final and (team_id is None or g.involves(team_id))]
        return done[-1] if done else None

    def last_game_day(self, today: date) -> list[NbaGame]:
        """The latest game day with finished games, today's included once they are all over."""
        days = sorted({g.day for g in self.games if g.is_final and g.day <= today}, reverse=True)
        for day in days:
            games = self.games_on(day)
            if day < today or all(g.is_final for g in games):
                return games
        return []

    def team_row(self, team_id: str) -> dict[str, Any] | None:
        for conference, rows in self.standings.items():
            for row in rows:
                if row["team_id"] == team_id:
                    return {**row, "conference_name": conference}
        return None
