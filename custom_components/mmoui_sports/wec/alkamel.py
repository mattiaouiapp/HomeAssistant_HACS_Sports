"""The official race classifications from the Al Kamel results site, published hour by hour."""
from __future__ import annotations
import asyncio
import csv
import io
import json
import re
from dataclasses import dataclass
from logging import getLogger
from time import time
from typing import Any
from urllib.parse import quote
import aiohttp
from ..api import SportsApiError

_LOGGER = getLogger(__name__)

BASE_URL = "https://files.alkamelcloud.com/"
SEASONS_MANIFEST = "wec/manifests/results.json"
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)

# wec/results/15_2026/08_MONZA/689_FIA WEC/202611081100_Race/03_Hour 3/03_Classification_Race_Hour 3.CSV
_RACE_FILE = re.compile(
    r"/\d+_(?P<event>[^/]+)/\d+_FIA WEC/(?P<start>\d{12})_Race/[^/]+/"
    r"\d+_Classification_Race_Hour (?P<hour>\d+)(?P<final>_Final)?\.CSV$",
    re.I,
)
_SEASON_NUMBER = re.compile(r"^(\d+)_")


@dataclass(frozen=True)
class RaceFile:
    url: str
    event: str
    start: str
    hour: int
    final: bool


def latest_season_manifest(index: dict[str, Any]) -> str | None:
    seasons = [s for s in index.get("seasons") or [] if _SEASON_NUMBER.match(str(s.get("id")))]
    if not seasons:
        return None
    return max(seasons, key=lambda s: int(_SEASON_NUMBER.match(s["id"]).group(1))).get("manifestUrl")


def _urls(node: dict[str, Any]) -> list[str]:
    urls = [node["url"]] if node.get("url") else []
    for child in node.get("children") or []:
        urls.extend(_urls(child))
    return urls


def latest_race_file(manifest: dict[str, Any]) -> RaceFile | None:
    """The newest classification of the most recent WEC race."""
    files = []
    for folder in manifest.get("folders") or []:
        for url in _urls(folder):
            if match := _RACE_FILE.search(url):
                files.append(
                    RaceFile(
                        url=url,
                        event=match["event"],
                        start=match["start"],
                        hour=int(match["hour"]),
                        final=bool(match["final"]),
                    )
                )
    return max(files, key=lambda f: (f.start, f.hour, f.final), default=None)


def _surname(driver: str) -> str:
    return " ".join(w for w in driver.split() if w.isupper() and len(w) > 1) or driver


def _seconds(value: str) -> float | None:
    """Parses 3:00'31.030 and 1'34.951."""
    try:
        total = 0.0
        for part in value.replace("'", ":").split(":"):
            total = total * 60 + float(part)
    except ValueError:
        return None
    return total


def _format_gap(seconds: float) -> str:
    if seconds < 60:
        return f"+{seconds:.3f}"
    return f"+{int(seconds // 60)}:{seconds % 60:06.3f}"


def _as_int(value: str) -> int:
    try:
        return int(value)
    except ValueError:
        return 0


def parse_classification(text: str) -> dict[str, list[dict[str, Any]]]:
    """Group the overall classification by class, with positions and gaps within the class."""
    classes: dict[str, list[dict[str, Any]]] = {}
    leader_times: dict[str, float | None] = {}
    for raw in csv.DictReader(io.StringIO(text), delimiter=";"):
        row = {k.strip(): (v or "").strip() for k, v in raw.items() if k}
        if not row.get("CLASS") or not row.get("NUMBER"):
            continue
        cls = row["CLASS"].upper()
        rows = classes.setdefault(cls, [])
        own_time = _seconds(row.get("TOTAL_TIME", ""))
        drivers = [row[f"DRIVER_{i}"] for i in range(1, 6) if row.get(f"DRIVER_{i}")]
        entry: dict[str, Any] = {
            "position": len(rows) + 1,
            "overall": _as_int(row.get("POSITION", "")),
            "number": row["NUMBER"],
            "team": row.get("TEAM"),
            "drivers": [_surname(d) for d in drivers],
            "vehicle": row.get("VEHICLE"),
            "laps": _as_int(row.get("LAPS", "")),
            "best": row.get("FL_TIME", "").replace("'", ":"),
            "status": row.get("STATUS"),
            "laps_down": 0,
            "gap": None,
        }
        if rows:
            entry["laps_down"] = max(rows[0]["laps"] - entry["laps"], 0)
            first_time = leader_times[cls]
            if not entry["laps_down"] and own_time is not None and first_time is not None:
                entry["gap"] = _format_gap(max(own_time - first_time, 0))
        else:
            leader_times[cls] = own_time
        rows.append(entry)
    return classes


class AlKamelClient:
    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session

    async def _get(self, path: str, **params: Any) -> bytes:
        url = BASE_URL + quote(path)
        try:
            async with self._session.get(url, params=params, timeout=REQUEST_TIMEOUT) as resp:
                resp.raise_for_status()
                return await resp.read()
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise SportsApiError(f"{path}: {err}") from err

    async def _get_manifest(self, path: str) -> dict[str, Any]:
        # The site busts its own CDN cache in the same way.
        raw = await self._get(path, _=int(time() * 1000))
        try:
            data = json.loads(raw)
        except ValueError as err:
            raise SportsApiError(f"{path}: {err}") from err
        if not isinstance(data, dict):
            raise SportsApiError(f"{path}: unexpected response")
        return data

    async def async_latest_race_file(self) -> RaceFile | None:
        manifest = latest_season_manifest(await self._get_manifest(SEASONS_MANIFEST))
        if manifest is None:
            return None
        return latest_race_file(await self._get_manifest(manifest))

    async def async_get_classification(self, race_file: RaceFile) -> dict[str, list[dict[str, Any]]]:
        return parse_classification((await self._get(race_file.url)).decode("utf-8-sig"))
