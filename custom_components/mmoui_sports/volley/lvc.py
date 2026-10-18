"""Results and live scores from the Lega Volley live board.

TheSportsDB only gets the results hours or days later and has no live scores.
The board (the page behind https://ww2.legavolley.it/lvc/) lists the current
round of every league with the sets won and the set scores, refreshed every 30
seconds, also while the matches are being played. Only the SuperLega table is read, and its matches are paired with the
TheSportsDB ones of the same round by team: the board names the teams after
their sponsors, which change every season.
"""
from __future__ import annotations
from dataclasses import dataclass
from html import unescape
import re
import unicodedata
from typing import Any
from .models import VolleySeason

LVC_URL = "https://live-cya6b4dqare7anh8.z01.azurefd.net/"

_TABLE = re.compile(r"<table[^>]*\bid=\"GareGiornata\"[^>]*>(.*?)</table>", re.S | re.I)
_TH = re.compile(r"<th[^>]*>(.*?)</th>", re.S | re.I)
_ROW = re.compile(r"<tr[^>]*\bid=\"Acquisto\"[^>]*>(.*?)</tr>", re.S | re.I)
_TD = re.compile(r"<td[^>]*>(.*?)</td>", re.S | re.I)
_TAG = re.compile(r"<[^>]+>")
_ROUND = re.compile(r"(\d+)\D*Giornata\s*\((Andata|Ritorno)\)", re.I)
_SCORE = re.compile(r"^(\d+)\s*-\s*(\d+)")
_WORD = re.compile(r"[a-z0-9]+")

SETS_TO_WIN = 3
_SET_LABELS = ("First", "Second", "Third", "Fourth", "Fifth")

# Words that tell the clubs apart, whatever the sponsor of the season. A team is
# keyed by the cities whose words appear in its name, plus its own long words.
_CITIES = {
    "verona": ("verona",),
    "civitanova": ("civitanova", "lube"),
    "modena": ("modena",),
    "trento": ("trentino", "trento", "itas"),
    "padova": ("padova",),
    "piacenza": ("piacenza", "energy", "sales"),
    "cisterna": ("cisterna",),
    "milano": ("milano", "allianz", "powervolley"),
    "cuneo": ("cuneo",),
    "perugia": ("perugia", "sir"),
    "prata": ("prata", "pordenone", "tinet"),
    "monza": ("monza",),
    "taranto": ("taranto", "prisma"),
    "grottazzolina": ("grottazzolina", "yuasa"),
    "siena": ("siena", "emma"),
    "catania": ("catania", "farmitalia"),
}
_GENERIC = {"volley", "pallavolo", "volleyball", "club", "team", "della", "sport"}


@dataclass
class LvcMatch:
    round: int
    home: str
    away: str
    home_score: int
    away_score: int
    sets: list[tuple[int, int]]

    @property
    def finished(self) -> bool:
        return max(self.home_score, self.away_score) == SETS_TO_WIN

    @property
    def started(self) -> bool:
        return bool(self.sets) or self.home_score + self.away_score > 0


def _text(html: str) -> str:
    return " ".join(unescape(_TAG.sub(" ", html)).split())


def parse(html: str, legs: int) -> list[LvcMatch]:
    """The SuperLega regular season matches on the board; `legs` is the rounds per leg."""
    matches: list[LvcMatch] = []
    for table in _TABLE.findall(html):
        headers = [_text(h) for h in _TH.findall(table)]
        if not headers or "superlega" not in headers[0].lower() or "regular season" not in headers[0].lower():
            continue
        round_number = None
        for header in headers:
            if found := _ROUND.search(header):
                round_number = int(found.group(1)) + (legs if found.group(2).lower() == "ritorno" else 0)
        if round_number is None:
            continue
        for row in _ROW.findall(table):
            cells = [_text(c) for c in _TD.findall(row)]
            if len(cells) < 3 or not (score := _SCORE.match(cells[2])):
                continue
            sets = [
                (int(s.group(1)), int(s.group(2)))
                for cell in cells[3:8]
                if (s := _SCORE.match(cell))
            ]
            matches.append(
                LvcMatch(round_number, cells[0], cells[1], int(score.group(1)), int(score.group(2)), sets)
            )
    return matches


def _key(name: str) -> set[str]:
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    words = set(_WORD.findall(plain))
    cities = {city for city, hints in _CITIES.items() if words & set(hints)}
    return cities | {w for w in words if len(w) >= 4 and w not in _GENERIC}


def apply(matches: list[LvcMatch], season: VolleySeason, raw_events: dict[str, dict[str, Any]]) -> int:
    """Write the board results and live scores into the TheSportsDB events; returns how many changed."""
    changed = 0
    for lvc in matches:
        if not lvc.started or (rnd := season.round(lvc.round)) is None:
            continue
        # Every team plays once per round, so one side is enough to find the match.
        home, away = _key(lvc.home), _key(lvc.away)
        candidates = [m for m in rnd.matches if home & _key(m.home.name)]
        if len(candidates) != 1:
            candidates = [m for m in rnd.matches if away & _key(m.away.name)]
        if len(candidates) != 1 or (event := raw_events.get(candidates[0].id)) is None:
            continue
        if lvc.finished:
            result = "".join(f"{_SET_LABELS[i]}<br>{h} {a} <br>" for i, (h, a) in enumerate(lvc.sets[:5]))
            update = {
                "intHomeScore": str(lvc.home_score),
                "intAwayScore": str(lvc.away_score),
                "strResult": result,
                "strStatus": "FT",
            }
            stale = ("strLiveScore", "strLiveSets")
        else:
            # Sets won so far, and every set score including the one being played.
            update = {
                "strLiveScore": f"{lvc.home_score}-{lvc.away_score}",
                "strLiveSets": [f"{h}-{a}" for h, a in lvc.sets],
            }
            stale = ()
        if any(event.get(k) != v for k, v in update.items()) or any(k in event for k in stale):
            event = {k: v for k, v in event.items() if k not in stale}
            raw_events[candidates[0].id] = {**event, **update}
            changed += 1
    return changed
