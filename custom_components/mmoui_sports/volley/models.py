"""Turns raw TheSportsDB events into volleyball matches, rounds and standings."""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone, tzinfo
from typing import Any
from .const import (
    CANCELLED_STATUSES,
    FINISHED_STATUSES,
    LIVE_MAX_DURATION,
    MATCH_DURATION,
    OUTCOME_LOST,
    OUTCOME_WON,
    PLAYOFF_ROUND,
    STATUS_FINISHED,
    STATUS_PLAYOFFS,
    STATUS_PRESEASON,
    STATUS_REGULAR_SEASON,
)

# strResult lists the sets as "home away" pairs, one label per set:
#   " Volley Perugia First:<br>25 27 <br>Second<br>26 24 <br>Third<br>25 22 <br>Forth<br><br>Fifth<br> "
# TheSportsDB often leaves the fourth set empty even when it was played.
_SET_LABELS = {"first": 1, "second": 2, "third": 3, "forth": 4, "fourth": 4, "fifth": 5}
_SET_LABEL = re.compile(r"\b(first|second|third|forth|fourth|fifth)\b", re.I)
_SET_SCORE = re.compile(r"^\s*(\d{1,2})\s+(\d{1,2})\s*$")
_SPACES = re.compile(r"\s+")

SETS_TO_WIN = 3
# Lega Volley points: 3 for a 3-0 or 3-1 win, 2 for a 3-2 win, 1 for a 2-3 defeat.
_POINTS = {(3, 0): 3, (3, 1): 3, (3, 2): 2, (2, 3): 1}
# Playoffs are over this long after the last known playoff match.
PLAYOFF_GRACE = timedelta(days=4)


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    value = _SPACES.sub(" ", str(value)).strip()
    return value or None


def _int(value: Any) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def parse_sets(text: str | None) -> list[dict[str, int]]:
    """Set scores from strResult, numbered so a missing fourth set stays visible."""
    sets: list[dict[str, int]] = []
    if not text:
        return sets
    current: int | None = None
    for chunk in str(text).split("<br>"):
        if match := _SET_LABEL.search(chunk):
            current = _SET_LABELS[match.group(1).lower()]
            continue
        if current is not None and (match := _SET_SCORE.match(chunk)):
            sets.append({"set": current, "home": int(match.group(1)), "away": int(match.group(2))})
            current = None
    return sets


@dataclass(frozen=True)
class Team:
    id: str
    name: str
    badge: str | None

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "badge": self.badge}


@dataclass
class VolleyMatch:
    id: str
    season: str | None
    round: int | None
    day: date
    start: datetime | None
    home: Team
    away: Team
    home_score: int | None
    away_score: int | None
    sets: list[dict[str, int]]
    status: str | None
    venue: str | None
    video: str | None
    thumb: str | None
    # From the Lega Volley live board while the match is being played.
    live_score: str | None = None
    live_sets: list[str] = field(default_factory=list)

    @classmethod
    def from_api(cls, raw: dict[str, Any], tz: tzinfo) -> VolleyMatch | None:
        home = _team(raw.get("idHomeTeam"), raw.get("strHomeTeam"), raw.get("strHomeTeamBadge"))
        away = _team(raw.get("idAwayTeam"), raw.get("strAwayTeam"), raw.get("strAwayTeamBadge"))
        start = _parse_start(raw)
        day = start.astimezone(tz).date() if start else _parse_day(raw)
        if home is None or away is None or day is None:
            return None
        return cls(
            id=str(raw["idEvent"]),
            season=_clean(raw.get("strSeason")),
            round=_int(raw.get("intRound")),
            day=day,
            start=start,
            home=home,
            away=away,
            home_score=_int(raw.get("intHomeScore")),
            away_score=_int(raw.get("intAwayScore")),
            sets=parse_sets(raw.get("strResult")),
            status=_clean(raw.get("strStatus")),
            venue=_clean(raw.get("strVenue")),
            video=_clean(raw.get("strVideo")),
            thumb=_clean(raw.get("strThumb")),
            live_score=_clean(raw.get("strLiveScore")),
            live_sets=[str(s) for s in raw.get("strLiveSets") or []],
        )

    @property
    def playoff(self) -> bool:
        return self.round == PLAYOFF_ROUND

    @property
    def is_cancelled(self) -> bool:
        return (self.status or "").upper() in CANCELLED_STATUSES

    @property
    def has_result(self) -> bool:
        if self.home_score is None or self.away_score is None:
            return False
        # A volleyball match ends when a team wins three sets; TheSportsDB sometimes
        # stores 0-0 for matches that have not been played.
        return max(self.home_score, self.away_score) == SETS_TO_WIN or (
            (self.status or "").upper() in FINISHED_STATUSES and self.home_score + self.away_score > 0
        )

    @property
    def end(self) -> datetime | None:
        return self.start + MATCH_DURATION if self.start else None

    @property
    def winner(self) -> Team | None:
        if not self.has_result or self.home_score == self.away_score:
            return None
        return self.home if self.home_score > self.away_score else self.away

    def involves(self, team_id: str) -> bool:
        return team_id in (self.home.id, self.away.id)

    def opponent(self, team_id: str) -> Team:
        return self.away if self.home.id == team_id else self.home

    def sets_for(self, team_id: str) -> tuple[int, int] | None:
        """(sets won, sets lost) from the point of view of a team."""
        if not self.has_result:
            return None
        if self.home.id == team_id:
            return self.home_score, self.away_score
        return self.away_score, self.home_score

    def outcome_for(self, team_id: str) -> str | None:
        if (sets := self.sets_for(team_id)) is None or sets[0] == sets[1]:
            return None
        return OUTCOME_WON if sets[0] > sets[1] else OUTCOME_LOST

    def is_live(self, now: datetime) -> bool:
        """Started and no result yet: a long match stays live while the board has its score."""
        if self.has_result or self.is_cancelled or self.start is None:
            return False
        end = self.start + LIVE_MAX_DURATION if self.live_score else self.end
        return self.start <= now < end

    def is_done(self, now: datetime) -> bool:
        """The result is in, or the match is over even if TheSportsDB has no score yet."""
        if self.has_result:
            return True
        if self.start is not None:
            return now >= self.end and not self.is_live(now)
        return self.day < now.date()

    @property
    def score(self) -> str | None:
        return f"{self.home_score}-{self.away_score}" if self.has_result else None

    @property
    def title(self) -> str:
        if self.has_result:
            return f"{self.home.name} {self.home_score}-{self.away_score} {self.away.name}"
        return f"{self.home.name} - {self.away.name}"

    def as_attributes(self, now: datetime | None = None) -> dict[str, Any]:
        attrs = {
            "event_id": self.id,
            "season": self.season,
            "round": self.round,
            "playoff": self.playoff,
            "date": self.day.isoformat(),
            "start": self.start.isoformat() if self.start else None,
            "home_team": self.home.name,
            "home_team_id": self.home.id,
            "home_badge": self.home.badge,
            "away_team": self.away.name,
            "away_team_id": self.away.id,
            "away_badge": self.away.badge,
            "home_score": self.home_score if self.has_result else None,
            "away_score": self.away_score if self.has_result else None,
            "score": self.score,
            "sets": self.sets,
            "winner": self.winner.name if self.winner else None,
            "title": self.title,
            "status": self.status,
            "cancelled": self.is_cancelled,
            "venue": self.venue,
            "video": self.video,
            "thumb": self.thumb,
        }
        if now is not None:
            live = self.is_live(now)
            attrs["live"] = live
            attrs["live_score"] = self.live_score if live else None
            attrs["live_sets"] = self.live_sets if live else []
        return attrs

    def summary(self, now: datetime) -> dict[str, Any]:
        """The short form used in match lists."""
        return {
            "event_id": self.id,
            "round": self.round,
            "date": self.day.isoformat(),
            "start": self.start.isoformat() if self.start else None,
            "home_team": self.home.name,
            "home_badge": self.home.badge,
            "away_team": self.away.name,
            "away_badge": self.away.badge,
            "score": self.score,
            "sets": [f"{s['home']}-{s['away']}" for s in self.sets],
            "venue": self.venue,
            "cancelled": self.is_cancelled,
            "live": self.is_live(now),
            "live_score": self.live_score if self.is_live(now) else None,
            "live_sets": self.live_sets if self.is_live(now) else [],
            "done": self.is_done(now),
        }

    def team_attributes(self, team_id: str, now: datetime) -> dict[str, Any]:
        """A match seen from one team: opponent, home or away, outcome."""
        opponent = self.opponent(team_id)
        sets = self.sets_for(team_id)
        return {
            **self.as_attributes(now),
            "opponent": opponent.name,
            "opponent_id": opponent.id,
            "opponent_badge": opponent.badge,
            "home": self.home.id == team_id,
            "sets_won": sets[0] if sets else None,
            "sets_lost": sets[1] if sets else None,
            "outcome": self.outcome_for(team_id),
            "points": self.points_for(team_id) if not self.playoff else None,
        }

    def points_for(self, team_id: str) -> int | None:
        if (sets := self.sets_for(team_id)) is None:
            return None
        return _POINTS.get(sets, 0)


def _team(team_id: Any, name: Any, badge: Any) -> Team | None:
    team_id, name = _clean(team_id), _clean(name)
    if not team_id or not name:
        return None
    return Team(team_id, name, _clean(badge))


def _parse_start(raw: dict[str, Any]) -> datetime | None:
    # strTimestamp is UTC; 00:00 means TheSportsDB has no start time.
    value = _clean(raw.get("strTimestamp"))
    if not value or (_clean(raw.get("strTime")) or "00:00:00").startswith("00:00"):
        return None
    try:
        start = datetime.fromisoformat(value)
    except ValueError:
        return None
    return start if start.tzinfo else start.replace(tzinfo=timezone.utc)


def _parse_day(raw: dict[str, Any]) -> date | None:
    value = _clean(raw.get("dateEvent")) or (_clean(raw.get("strTimestamp")) or "")[:10]
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _match_key(match: VolleyMatch) -> tuple[date, datetime, str]:
    return match.day, match.start or datetime.combine(match.day, datetime.min.time(), timezone.utc), match.id


@dataclass
class VolleyRound:
    number: int
    matches: list[VolleyMatch]

    @property
    def active(self) -> list[VolleyMatch]:
        return [m for m in self.matches if not m.is_cancelled]

    @property
    def day(self) -> date:
        """The day most of the round is played: anticipated and postponed matches do not move it."""
        days = sorted(m.day for m in (self.active or self.matches))
        return days[len(days) // 2]

    @property
    def first_day(self) -> date:
        return min(m.day for m in self.matches)

    @property
    def last_day(self) -> date:
        return max(m.day for m in self.matches)

    @property
    def finished(self) -> bool:
        return all(m.has_result for m in self.active)

    def team_ids(self) -> set[str]:
        return {t.id for m in self.matches for t in (m.home, m.away)}

    def summary(self, now: datetime) -> dict[str, Any]:
        return {
            "round": self.number,
            "date": self.day.isoformat(),
            "first_date": self.first_day.isoformat(),
            "last_date": self.last_day.isoformat(),
            "finished": self.finished,
            "matches": [m.summary(now) for m in self.matches],
        }


@dataclass
class StandingRow:
    team: Team
    played: int = 0
    won: int = 0
    lost: int = 0
    won_full: int = 0
    won_tiebreak: int = 0
    lost_tiebreak: int = 0
    lost_full: int = 0
    sets_won: int = 0
    sets_lost: int = 0
    points: int = 0
    form: list[str] = field(default_factory=list)

    @property
    def set_ratio(self) -> float:
        if self.sets_lost:
            return self.sets_won / self.sets_lost
        return float("inf") if self.sets_won else 0.0

    def add(self, match: VolleyMatch) -> None:
        won, lost = match.sets_for(self.team.id)
        self.played += 1
        self.sets_won += won
        self.sets_lost += lost
        self.points += match.points_for(self.team.id)
        if won > lost:
            self.won += 1
            if lost == SETS_TO_WIN - 1:
                self.won_tiebreak += 1
            else:
                self.won_full += 1
            self.form.append("W")
        else:
            self.lost += 1
            if won == SETS_TO_WIN - 1:
                self.lost_tiebreak += 1
            else:
                self.lost_full += 1
            self.form.append("L")

    def as_dict(self, position: int) -> dict[str, Any]:
        ratio = self.set_ratio
        return {
            "position": position,
            "team": self.team.name,
            "team_id": self.team.id,
            "badge": self.team.badge,
            "points": self.points,
            "played": self.played,
            "won": self.won,
            "lost": self.lost,
            "won_3_0_3_1": self.won_full,
            "won_3_2": self.won_tiebreak,
            "lost_2_3": self.lost_tiebreak,
            "lost_1_3_0_3": self.lost_full,
            "sets_won": self.sets_won,
            "sets_lost": self.sets_lost,
            # None when the team has not lost a set yet.
            "set_ratio": round(ratio, 3) if ratio != float("inf") else None,
            "form": "".join(self.form[-5:]),
        }


@dataclass
class VolleySeason:
    season: str | None
    matches: list[VolleyMatch]

    def __post_init__(self) -> None:
        self.regular = [m for m in self.matches if m.round and m.round > 0]
        self.playoffs = [m for m in self.matches if m.playoff]
        rounds: dict[int, list[VolleyMatch]] = {}
        for match in self.regular:
            rounds.setdefault(match.round, []).append(match)
        self.rounds = [VolleyRound(n, rounds[n]) for n in sorted(rounds)]
        teams: dict[str, Team] = {}
        for match in self.matches:
            for team in (match.home, match.away):
                # Keep a badge when only some events carry it.
                if team.id not in teams or (team.badge and not teams[team.id].badge):
                    teams[team.id] = team
        self.teams = dict(sorted(teams.items(), key=lambda t: t[1].name.lower()))

    @property
    def active(self) -> list[VolleyMatch]:
        return [m for m in self.matches if not m.is_cancelled]

    @property
    def start(self) -> date | None:
        return self.matches[0].day if self.matches else None

    @property
    def end(self) -> date | None:
        return self.matches[-1].day if self.matches else None

    @property
    def regular_season_end(self) -> date | None:
        return max((m.day for m in self.regular), default=None)

    @property
    def total_rounds(self) -> int:
        """Rounds of the double round robin, even when TheSportsDB has not published them all."""
        known = max((r.number for r in self.rounds), default=0)
        return max(known, 2 * (len(self.teams) - 1)) if self.rounds else 0

    def round(self, number: int) -> VolleyRound | None:
        return next((r for r in self.rounds if r.number == number), None)

    def rounds_played(self, today: date) -> int:
        return sum(1 for r in self.rounds if r.day < today or (r.day == today and r.finished))

    def next_round(self, today: date) -> VolleyRound | None:
        upcoming = [r for r in self.rounds if r.day >= today and not r.finished]
        return min(upcoming, key=lambda r: (r.day, r.number), default=None)

    def last_round(self, today: date) -> VolleyRound | None:
        played = [r for r in self.rounds if r.day < today or (r.day == today and r.finished)]
        return max(played, key=lambda r: (r.day, r.number), default=None)

    def matches_on(self, day: date) -> list[VolleyMatch]:
        return [m for m in self.active if m.day == day]

    def live(self, now: datetime) -> list[VolleyMatch]:
        return [m for m in self.active if m.is_live(now)]

    def next_match(self, now: datetime, team_id: str | None = None) -> VolleyMatch | None:
        return next(
            (
                m
                for m in self.active
                if not m.is_done(now) and not m.is_live(now) and (team_id is None or m.involves(team_id))
            ),
            None,
        )

    def team_matches(self, team_id: str) -> list[VolleyMatch]:
        return [m for m in self.matches if m.involves(team_id)]

    def standings(self) -> list[dict[str, Any]]:
        """Regular season table computed from the results (penalty points are not known)."""
        rows = {team_id: StandingRow(team) for team_id, team in self.teams.items()}
        for match in self.regular:
            if match.has_result and not match.is_cancelled:
                for team in (match.home, match.away):
                    rows[team.id].add(match)
        ordered = sorted(
            rows.values(),
            key=lambda r: (-r.points, -r.won, -r.set_ratio, -r.sets_won, r.team.name.lower()),
        )
        return [row.as_dict(position) for position, row in enumerate(ordered, start=1)]

    def playoff_series(self, now: datetime) -> list[dict[str, Any]]:
        """Playoff matches grouped by pairing, in the order the series started."""
        series: dict[frozenset[str], list[VolleyMatch]] = {}
        for match in self.playoffs:
            series.setdefault(frozenset((match.home.id, match.away.id)), []).append(match)
        result = []
        for matches in sorted(series.values(), key=lambda ms: _match_key(ms[0])):
            first = matches[0]
            # Name the series after the team at home in game 1, the higher seed.
            team_a, team_b = first.home, first.away
            wins = {team_a.id: 0, team_b.id: 0}
            for match in matches:
                if match.winner:
                    wins[match.winner.id] += 1
            result.append(
                {
                    "team_a": team_a.name,
                    "team_a_badge": team_a.badge,
                    "team_b": team_b.name,
                    "team_b_badge": team_b.badge,
                    "wins_a": wins[team_a.id],
                    "wins_b": wins[team_b.id],
                    "first_date": matches[0].day.isoformat(),
                    "last_date": matches[-1].day.isoformat(),
                    "matches": [m.summary(now) for m in matches],
                }
            )
        return result

    def status(self, now: datetime) -> str | None:
        today = now.date()
        if not self.matches:
            return None
        if today < self.start:
            return STATUS_PRESEASON
        regular_end = self.regular_season_end
        if regular_end is not None and today <= regular_end:
            return STATUS_REGULAR_SEASON
        if self.playoffs:
            last = self.playoffs[-1]
            if any(not m.is_done(now) for m in self.playoffs) or last.day + PLAYOFF_GRACE >= today:
                return STATUS_PLAYOFFS
        return STATUS_FINISHED


@dataclass
class VolleyData:
    season: str | None
    league: dict[str, Any]
    current: VolleySeason
    # Every known match, the previous season's last ones included.
    matches: list[VolleyMatch]

    @classmethod
    def from_raw(
        cls,
        season: str | None,
        league: dict[str, Any],
        raw_events: list[dict[str, Any]],
        tz: tzinfo,
    ) -> VolleyData:
        matches = sorted(
            (m for m in (VolleyMatch.from_api(e, tz) for e in raw_events) if m is not None),
            key=_match_key,
        )
        return cls(
            season=season,
            league=league,
            current=VolleySeason(season, [m for m in matches if season is None or m.season == season]),
            matches=matches,
        )

    def last_match(self, team_id: str | None = None) -> VolleyMatch | None:
        """The latest result, from the previous season when this one has not started."""
        done = [
            m
            for m in self.matches
            if m.has_result and not m.is_cancelled and (team_id is None or m.involves(team_id))
        ]
        return done[-1] if done else None
