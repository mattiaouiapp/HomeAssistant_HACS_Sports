"""Turns raw TheSportsDB events into Dakar stages and rallies."""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any
from .const import (
    CANCELLED_STATUSES,
    FINISHED_STATUSES,
    STATUS_FINISHED,
    STATUS_RACING,
    STATUS_REST_DAY,
    STATUS_UPCOMING,
)

# "Prologue", "Prolouge" (sic), "Stage 4 Marathon", "Stage 3  Bisha > Al Henakiyah"
_PROLOGUE = re.compile(r"^prol\w*", re.I)
_STAGE = re.compile(r"^stage\s*(\d+)", re.I)
_MARATHON = re.compile(r"\bmarathon\b", re.I)
_ROUTE = re.compile(r"([^>]+?)\s*>\s*(.+)$")
_SPACES = re.compile(r"\s+")
# Results come as a tab separated table, stage classification on the left and
# general classification on the right:
#   "1\tAustralia Daniel Sanders\tKTM\t04:41:27\t\t1\tAustralia Daniel Sanders\tKTM\t04:58:18\t"
# or as a plain text summary, which is kept as is.
_CATEGORY = re.compile(
    r"\b(bikes?|motos?|cars?|ultimate|trucks?|challenger|ssv|quads?|classic|stock|mission)\b", re.I
)
DEFAULT_CATEGORY = "ALL"


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    value = _SPACES.sub(" ", str(value)).strip()
    return value or None


def _place(value: Any) -> str | None:
    """TheSportsDB mixes "AL HENAKIYAH", "Alula" and "Shubaytah"; make them consistent."""
    value = _clean(value)
    if value and value.isupper():
        value = value.title()
    return value


def _row(cells: list[str]) -> dict[str, Any] | None:
    cells = (cells + [""] * 5)[:5]
    if not cells[0].isdigit() or not cells[1]:
        return None
    return {
        "position": int(cells[0]),
        "name": cells[1],
        "team": cells[2] or None,
        "time": cells[3] or None,
        "gap": cells[4] or None,
    }


def parse_result(text: str | None) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """Parse the tab separated result table into {category: {"stage": [...], "general": [...]}}."""
    results: dict[str, dict[str, list[dict[str, Any]]]] = {}
    if not text:
        return results
    category = DEFAULT_CATEGORY
    for raw_line in text.replace("\r", "").split("\n"):
        cells = [c.strip() for c in raw_line.split("\t")]
        if not any(cells):
            continue
        if not cells[0].isdigit():
            if match := _CATEGORY.search(" ".join(cells)):
                category = match.group(1).upper()
            continue
        if (stage := _row(cells[:5])) is None:
            continue
        table = results.setdefault(category, {"stage": [], "general": []})
        table["stage"].append(stage)
        if len(cells) > 5 and (general := _row(cells[5:10])):
            table["general"].append(general)
    return results


@dataclass
class DakarStage:
    id: str
    name: str
    number: int
    prologue: bool
    marathon: bool
    season: str | None
    day: date
    start_town: str | None
    finish_town: str | None
    bivouac: str | None
    country: str | None
    status: str | None
    result: str | None
    description: str | None
    poster: str | None
    thumb: str | None
    video: str | None

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> DakarStage | None:
        raw_name = _clean(raw.get("strEvent"))
        day = _parse_day(raw)
        if not raw_name or day is None:
            return None
        try:
            round_number = int(raw["intRound"]) if raw.get("intRound") not in (None, "") else None
        except (TypeError, ValueError):
            round_number = None

        prologue = bool(_PROLOGUE.match(raw_name)) or round_number == 0
        if match := _STAGE.match(raw_name):
            number = int(match.group(1))
            rest = raw_name[match.end():]
        elif prologue:
            number = 0
            rest = _PROLOGUE.sub("", raw_name)
        elif round_number is not None:
            number = round_number
            rest = ""
        else:
            return None
        marathon = bool(_MARATHON.search(raw_name))
        start_town = finish_town = None
        if match := _ROUTE.search(_MARATHON.sub("", rest)):
            start_town, finish_town = _place(match.group(1)), _place(match.group(2))

        if prologue:
            name = "Prologue"
        else:
            name = f"Stage {number}" + (" Marathon" if marathon else "")
        return cls(
            id=str(raw["idEvent"]),
            name=name,
            number=number,
            prologue=prologue,
            marathon=marathon,
            season=_clean(raw.get("strSeason")),
            day=day,
            start_town=start_town,
            finish_town=finish_town,
            # strCity is sometimes the start town (2025), the route's finish is the bivouac.
            bivouac=finish_town or _place(raw.get("strCity")),
            country=_clean(raw.get("strCountry")),
            status=_clean(raw.get("strStatus")),
            result=_clean_block(raw.get("strResult")),
            description=_clean_block(raw.get("strDescriptionEN")),
            poster=_clean(raw.get("strPoster")),
            thumb=_clean(raw.get("strThumb")),
            video=_clean(raw.get("strVideo")),
        )

    @property
    def is_cancelled(self) -> bool:
        return (self.status or "").upper() in CANCELLED_STATUSES

    @property
    def has_result(self) -> bool:
        return (self.status or "").upper() in FINISHED_STATUSES or bool(self.result)

    @property
    def route(self) -> str | None:
        if self.start_town and self.finish_town:
            return f"{self.start_town} > {self.finish_town}"
        return None

    @property
    def location(self) -> str | None:
        return ", ".join(p for p in (self.bivouac, self.country) if p) or None

    def is_done(self, today: date) -> bool:
        """The stage day is over, or the result is already in."""
        return self.day < today or (self.day == today and self.has_result)

    def as_attributes(self) -> dict[str, Any]:
        return {
            "event_id": self.id,
            "name": self.name,
            "stage_number": self.number,
            "prologue": self.prologue,
            "marathon": self.marathon,
            "season": self.season,
            "date": self.day.isoformat(),
            "route": self.route,
            "start_town": self.start_town,
            "finish_town": self.finish_town,
            "bivouac": self.bivouac,
            "country": self.country,
            "status": self.status,
            "cancelled": self.is_cancelled,
            "poster": self.poster,
            "thumb": self.thumb,
            "video": self.video,
        }

    def summary(self, today: date) -> dict[str, Any]:
        """The short form used in stage lists."""
        return {
            "number": self.number,
            "name": self.name,
            "date": self.day.isoformat(),
            "route": self.route,
            "bivouac": self.bivouac,
            "marathon": self.marathon,
            "done": self.is_done(today),
            "today": self.day == today,
            "cancelled": self.is_cancelled,
            "video": self.video,
        }


def _clean_block(value: Any) -> str | None:
    """Like _clean, but keep the line breaks and tabs of multi-line text."""
    if value is None:
        return None
    value = str(value).replace("\r", "").strip()
    return value or None


def _parse_day(raw: dict[str, Any]) -> date | None:
    # dateEvent is the stage day. dateEventLocal is not usable: for the 2027 edition it
    # is a day early on half the stages.
    value = _clean(raw.get("dateEvent")) or (_clean(raw.get("strTimestamp")) or "")[:10]
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


@dataclass
class DakarRally:
    """One edition of the rally: its stages, in order."""

    season: str | None
    stages: list[DakarStage] = field(default_factory=list)

    @property
    def active_stages(self) -> list[DakarStage]:
        return [s for s in self.stages if not s.is_cancelled]

    @property
    def start(self) -> date | None:
        return self.stages[0].day if self.stages else None

    @property
    def end(self) -> date | None:
        return self.stages[-1].day if self.stages else None

    @property
    def total_stages(self) -> int:
        """Competitive stages, the Prologue does not count."""
        return sum(1 for s in self.stages if not s.prologue)

    @property
    def rest_days(self) -> list[date]:
        days = {s.day for s in self.stages}
        if not days:
            return []
        first, last = min(days), max(days)
        return [
            first + timedelta(days=i)
            for i in range((last - first).days + 1)
            if first + timedelta(days=i) not in days
        ]

    def stage_on(self, day: date) -> DakarStage | None:
        return next((s for s in self.active_stages if s.day == day), None)

    def next_stage(self, today: date) -> DakarStage | None:
        return next((s for s in self.active_stages if s.day > today), None)

    def last_stage(self, today: date) -> DakarStage | None:
        done = [s for s in self.active_stages if s.is_done(today)]
        return done[-1] if done else None

    def completed(self, today: date) -> int:
        return sum(1 for s in self.active_stages if not s.prologue and s.day < today)

    def in_progress(self, today: date) -> bool:
        return self.start is not None and self.start <= today <= self.end

    def status(self, today: date) -> str | None:
        if not self.stages:
            return None
        if today < self.start:
            return STATUS_UPCOMING
        if today > self.end:
            return STATUS_FINISHED
        return STATUS_RACING if self.stage_on(today) else STATUS_REST_DAY


@dataclass
class DakarData:
    season: str | None
    league: dict[str, Any]
    stages: list[DakarStage]
    rally: DakarRally

    @classmethod
    def from_raw(cls, season: str | None, league: dict[str, Any], raw_events: list[dict]) -> DakarData:
        stages = sorted(
            (s for s in map(DakarStage.from_api, raw_events) if s is not None),
            key=lambda s: (s.day, s.number),
        )
        return cls(
            season=season,
            league=league,
            stages=stages,
            rally=DakarRally(season, [s for s in stages if season is None or s.season == season]),
        )

    def last_stage(self, today: date) -> DakarStage | None:
        """The latest finished stage, from the previous edition if this one has not started."""
        done = [s for s in self.stages if not s.is_cancelled and s.is_done(today)]
        return done[-1] if done else None
