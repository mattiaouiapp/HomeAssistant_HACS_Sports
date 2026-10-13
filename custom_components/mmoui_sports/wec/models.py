"""Turns raw TheSportsDB events into races, sessions and rounds."""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from .const import (
    CANCELLED_STATUSES,
    DEFAULT_RACE_DURATION,
    FINISHED_STATUSES,
    KIND_HYPERPOLE,
    KIND_PRACTICE,
    KIND_QUALIFYING,
    KIND_RACE,
    KIND_TEST,
    KIND_WARMUP,
    SESSION_DURATIONS,
)

# Order matters: "Hyperpole Qualifying" is a hyperpole, not a qualifying.
_KIND_PATTERNS = (
    (KIND_TEST, re.compile(r"\b(prologue|test|rookie)\b", re.I)),
    (KIND_HYPERPOLE, re.compile(r"\bhyperpole\b", re.I)),
    (KIND_QUALIFYING, re.compile(r"\bqualifying\b", re.I)),
    (KIND_WARMUP, re.compile(r"\bwarm[ -]?up\b", re.I)),
    (KIND_PRACTICE, re.compile(r"\b(free practice|practice|fp\d)\b", re.I)),
)
_SESSION_SUFFIX = re.compile(
    r"\s+(free practice|practice|fp\d|qualifying|hyperpole|warm[ -]?up)\b.*$", re.I
)
_RACE_HOURS = re.compile(r"(\d+)\s*hours?\b", re.I)
_RACE_KM = re.compile(r"(\d+)\s*km\b", re.I)
# Result entries come in several shapes depending on who typed them in:
#   "1 /TOYOTA GAZOO RACING #8 /6:00:10.939"
#   "1. #15 BMW M Team WRT (Magnussen/Marciello/Vanthoor) - 242 laps - 6:00:26.462"
#   "HYPERCAR: 1. #8 Toyota Racing 1:29.694 - Buemi/Hartley/Hirakawa; 2. #12 ..."
#   "1 (Pole) / #23 / Heart of Racing Team / Aston Martin Vantage AMR LMGT3 / 1m33.350s"
_RESULT_COLUMNS = re.compile(r"^(\d+)(?:\s*\([^)]*\))?\s*/\s*#(\d+)\s*/\s*(.+)$")
_RESULT_LINE = re.compile(r"^(\d+)\s*/?\s*(.+?)\s*#(\d+)\s*/\s*(.*)$")
_COLUMN_HEADER = re.compile(r"^pos\b", re.I)
_PARENTHESISED = re.compile(r"\s*\([^)]*\)")
_RESULT_ENTRY = re.compile(r"^(\d+)\.\s*#(\d+)\s+(.+)$")
_INLINE_CLASS = re.compile(r"^([A-Za-z0-9][\w &/]{0,30}):\s*(\d+\..*)$")
_INLINE_SPLIT = re.compile(r";\s*(?=\d+\.\s*#)")
_DRIVERS_IN_PARENS = re.compile(r"\s*\(([^)]*/[^)]*|[^)\d]+)\)\s*$")
_TIME_AT_END = re.compile(r"\s+(\+?\d+(?::\d{2})*\.\d+s?)$")
_LAPS = re.compile(r"^(\d+)\s*laps?$", re.I)
_GAP = re.compile(r"^\+?\d+(?::\d{2})*(?:\.\d+)?s?$|^\+\d+\s*laps?$", re.I)
_STANDING_LINE = re.compile(r"^(\d+)\s*/\s*#?(\d+)\s*/\s*(.+?)\s*/\s*(\d+(?:[.,]\d+)?)\s*$")
_AVERAGE_RACE_SPEED_KMH = 180


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def detect_kind(name: str) -> str:
    for kind, pattern in _KIND_PATTERNS:
        if pattern.search(name):
            return kind
    return KIND_RACE


def race_duration(name: str) -> timedelta:
    if match := _RACE_HOURS.search(name):
        return timedelta(hours=int(match.group(1)))
    if match := _RACE_KM.search(name):
        return timedelta(hours=round(int(match.group(1)) / _AVERAGE_RACE_SPEED_KMH))
    return DEFAULT_RACE_DURATION


def _parse_entry(position: str, car_number: str, rest: str) -> dict[str, Any]:
    """Split "Team (Drivers) - 242 laps - +2.254s" style text into its fields."""
    parts = [p.strip() for p in re.split(r"\s+-\s+", rest) if p.strip()]
    team = parts.pop(0) if parts else rest
    drivers: list[str] = []
    laps: int | None = None
    time_: str | None = None
    if match := _DRIVERS_IN_PARENS.search(team):
        drivers = [d.strip() for d in match.group(1).split("/") if d.strip()]
        team = team[: match.start()]
    if match := _TIME_AT_END.search(team):
        time_ = match.group(1)
        team = team[: match.start()]
    for part in parts:
        if match := _LAPS.match(part):
            laps = int(match.group(1))
        elif _GAP.match(part):
            time_ = part
        elif "/" in part and not drivers:
            drivers = [d.strip() for d in part.split("/") if d.strip()]
    entry: dict[str, Any] = {
        "position": int(position),
        "team": team.strip(" ,"),
        "car_number": car_number,
        "time": time_,
    }
    if drivers:
        entry["drivers"] = drivers
    if laps is not None:
        entry["laps"] = laps
    return entry


def _result_lines(text: str) -> list[str]:
    """One entry per line, expanding "CLASS: 1. ...; 2. ..." into a header and its entries."""
    lines: list[str] = []
    for raw_line in text.replace("\r", "").split("\n"):
        line = raw_line.strip()
        if match := _INLINE_CLASS.match(line):
            lines.append(match.group(1))
            lines.extend(_INLINE_SPLIT.split(match.group(2)))
        else:
            lines.append(line)
    return lines


def parse_result(text: str | None) -> tuple[dict[str, list[dict]], dict[str, list[dict]]]:
    """Parse the free-form race result: class podiums, then championship standings."""
    results: dict[str, list[dict]] = {}
    standings: dict[str, list[dict]] = {}
    if not text:
        return results, standings
    target = results
    current_class: str | None = None
    for raw_line in _result_lines(text):
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("---"):
            target = standings
            current_class = None
            continue
        lowered = line.lower()
        if "standings" in lowered or lowered.startswith("place"):
            target = standings
            current_class = None
            continue
        if target is standings:
            if (match := _STANDING_LINE.match(line)) and current_class:
                standings[current_class].append(
                    {
                        "position": int(match.group(1)),
                        "car_number": match.group(2),
                        "drivers": [d.strip().title() for d in match.group(3).split(",") if d.strip()],
                        "points": float(match.group(4).replace(",", ".")),
                    }
                )
                continue
        elif _COLUMN_HEADER.match(line):
            # "Pos / Car # / Team / Car / Gap" with no class above it: a single-class session.
            current_class = current_class or "OVERALL"
            results.setdefault(current_class, [])
            continue
        elif (match := _RESULT_ENTRY.match(line)) and current_class:
            results[current_class].append(_parse_entry(*match.groups()))
            continue
        elif (match := _RESULT_COLUMNS.match(line)) and current_class:
            columns = [c.strip() for c in match.group(3).split(" / ")]
            results[current_class].append(
                {
                    "position": int(match.group(1)),
                    "team": columns[0],
                    "car_number": match.group(2),
                    "time": _PARENTHESISED.sub("", columns[-1]) if len(columns) > 1 else None,
                }
            )
            continue
        elif (match := _RESULT_LINE.match(line)) and current_class:
            results[current_class].append(
                {
                    "position": int(match.group(1)),
                    "team": match.group(2).strip(" /"),
                    "car_number": match.group(3),
                    "time": match.group(4).strip() or None,
                }
            )
            continue
        if not line[0].isdigit():
            current_class = _PARENTHESISED.sub("", line).rstrip(":").strip().upper()
            target.setdefault(current_class, [])
    return (
        {k: v for k, v in results.items() if v},
        {k: v for k, v in standings.items() if v},
    )


@dataclass
class WecEvent:
    id: str
    name: str
    kind: str
    season: str | None
    round: int | None
    start: datetime
    time_confirmed: bool
    duration: timedelta
    venue: str | None
    city: str | None
    country: str | None
    status: str | None
    result: str | None
    poster: str | None
    thumb: str | None
    banner: str | None
    map: str | None

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> WecEvent | None:
        name = _clean(raw.get("strEvent"))
        start = _parse_start(raw)
        if not name or start is None:
            return None
        start, time_confirmed = start
        kind = detect_kind(name)
        try:
            round_number = int(raw["intRound"]) if raw.get("intRound") else None
        except (TypeError, ValueError):
            round_number = None
        return cls(
            id=str(raw["idEvent"]),
            name=name,
            kind=kind,
            season=_clean(raw.get("strSeason")),
            round=round_number,
            start=start,
            time_confirmed=time_confirmed,
            duration=race_duration(name) if kind == KIND_RACE else SESSION_DURATIONS[kind],
            venue=_clean(raw.get("strVenue")),
            city=_clean(raw.get("strCity")),
            country=_clean(raw.get("strCountry")),
            status=_clean(raw.get("strStatus")),
            result=_clean(raw.get("strResult")),
            poster=_clean(raw.get("strPoster")),
            thumb=_clean(raw.get("strThumb")),
            banner=_clean(raw.get("strBanner")),
            map=_clean(raw.get("strMap")),
        )

    @property
    def end(self) -> datetime:
        if not self.time_confirmed:
            # Unknown start time: the event may run any time that (UTC) day.
            return max(self.start + self.duration, self.start + timedelta(days=1))
        return self.start + self.duration

    @property
    def event_name(self) -> str:
        """The race weekend this session belongs to."""
        return _SESSION_SUFFIX.sub("", self.name).strip(" -–") or self.name

    @property
    def is_finished(self) -> bool:
        return (self.status or "").upper() in FINISHED_STATUSES or (
            self.kind == KIND_RACE and bool(self.result)
        )

    @property
    def is_cancelled(self) -> bool:
        return (self.status or "").upper() in CANCELLED_STATUSES

    @property
    def location(self) -> str | None:
        return ", ".join(p for p in (self.venue, self.country) if p) or None

    def as_attributes(self) -> dict[str, Any]:
        return {
            "event_id": self.id,
            "name": self.name,
            "event_name": self.event_name,
            "kind": self.kind,
            "round": self.round,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "time_confirmed": self.time_confirmed,
            "circuit": self.venue,
            "city": self.city,
            "country": self.country,
            "status": self.status,
            "cancelled": self.is_cancelled,
        }


def _parse_start(raw: dict[str, Any]) -> tuple[datetime, bool] | None:
    timestamp = _clean(raw.get("strTimestamp"))
    day = _clean(raw.get("dateEvent"))
    clock = _clean(raw.get("strTime"))
    try:
        if timestamp:
            start = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        elif day:
            start = datetime.combine(date.fromisoformat(day), time.fromisoformat(clock or "00:00:00"))
        else:
            return None
    except ValueError:
        return None
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    start = start.astimezone(timezone.utc)
    # TheSportsDB stores "time not announced yet" as midnight UTC.
    time_confirmed = start.time() != time(0, 0)
    return start, time_confirmed


@dataclass
class WecRound:
    number: int
    season: str | None
    events: list[WecEvent] = field(default_factory=list)

    @property
    def race(self) -> WecEvent | None:
        races = [e for e in self.events if e.kind == KIND_RACE]
        return races[-1] if races else None

    @property
    def sessions(self) -> list[WecEvent]:
        return [e for e in self.events if e.kind != KIND_RACE]

    @property
    def name(self) -> str:
        if race := self.race:
            return race.name
        return self.events[-1].event_name

    @property
    def is_test(self) -> bool:
        return all(e.kind == KIND_TEST for e in self.events)

    @property
    def start(self) -> datetime:
        return self.events[0].start

    @property
    def end(self) -> datetime:
        return max(e.end for e in self.events)

    @property
    def venue(self) -> str | None:
        return next((e.venue for e in self.events if e.venue), None)

    @property
    def country(self) -> str | None:
        return next((e.country for e in self.events if e.country), None)


@dataclass
class WecData:
    season: str | None
    league: dict[str, Any]
    events: list[WecEvent]
    rounds: list[WecRound]

    @classmethod
    def from_raw(cls, season: str | None, league: dict[str, Any], raw_events: list[dict]) -> WecData:
        events = sorted(
            (e for e in map(WecEvent.from_api, raw_events) if e is not None),
            key=lambda e: (e.start, e.kind == KIND_RACE, e.name),
        )
        rounds: dict[tuple[str | None, int], WecRound] = {}
        for event in events:
            if event.round is None:
                continue
            key = (event.season, event.round)
            rounds.setdefault(key, WecRound(event.round, event.season)).events.append(event)
        for round_ in rounds.values():
            # A postponed race takes its weekend with it, the sessions keep no status of their own.
            if (race := round_.race) and race.is_cancelled:
                for session in round_.sessions:
                    session.status = session.status or race.status
        return cls(
            season=season,
            league=league,
            events=events,
            rounds=sorted(rounds.values(), key=lambda r: r.start),
        )

    @property
    def races(self) -> list[WecEvent]:
        return [e for e in self.events if e.kind == KIND_RACE]

    def season_races(self) -> list[WecEvent]:
        return [e for e in self.races if self.season is None or e.season == self.season]

    def next_race(self, now: datetime) -> WecEvent | None:
        return next((e for e in self.races if e.end > now and not e.is_cancelled), None)

    def last_race(self, now: datetime) -> WecEvent | None:
        finished = [e for e in self.races if e.end <= now and not e.is_cancelled]
        return finished[-1] if finished else None

    def next_session(self, now: datetime) -> WecEvent | None:
        return next((e for e in self.events if e.start > now and not e.is_cancelled), None)

    def live_session(self, now: datetime) -> WecEvent | None:
        live = [
            e for e in self.events
            if e.time_confirmed and not e.is_cancelled and e.start <= now < e.end
        ]
        # The race beats any overlapping support session.
        return max(live, key=lambda e: (e.kind == KIND_RACE, e.start), default=None)

    def current_round(self, now: datetime) -> WecRound | None:
        return next(
            (r for r in self.rounds if not r.is_test and r.start <= now < r.end), None
        )

    def round_of(self, event: WecEvent) -> WecRound | None:
        return next(
            (r for r in self.rounds if r.number == event.round and r.season == event.season),
            None,
        )
