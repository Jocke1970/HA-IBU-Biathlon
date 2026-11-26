"""Read-only, bounded IBU Sport API archiver for Home Assistant.

No Home Assistant imports; testable without HA running.
Raw data always remains below the project-owned root directory.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import time
from urllib.parse import urljoin

SITE = "https://biathlonresults.com/"
API = urljoin(SITE, "modules/sportapi/api/")
ANALYSIS = (
    "CRST", "RNGT", "STTM", "SKIT", "PURS", "BSTW", "BSTM",
    *(f"CRS{i}" for i in range(1, 13)),
    *(f"RNG{i}" for i in range(1, 9)),
    *(f"S{i}TM" for i in range(1, 9)),
    *(f"FI{i}L" for i in range(1, 5)),
    *(f"CRST{i}" for i in range(1, 5)),
    *(f"RNGT{i}" for i in range(1, 5)),
)
LIVE_ANALYSIS = ("RNGT", "STTM", "SKIT")
ENDPOINTS = {"Seasons", "Events", "Cups", "Competitions", "Results", "AnalyticResults"}
ID_RE = re.compile(r"^[A-Za-z0-9_-]{2,90}$")
KEY_RE = re.compile(r"""ApiKey\s*=\s*['"]([0-9a-fA-F-]{36})['"]""")
SCRIPT_RE = re.compile(r"""<script[^>]*\ssrc=['"]([^'"]+\.js[^'"]*)['"]""", re.I)


def now_utc():
    return datetime.now(timezone.utc)


def safe_id(value):
    return value if isinstance(value, str) and ID_RE.fullmatch(value) else None


def parse_date(value, *, date_only=False):
    if not isinstance(value, str):
        return None
    try:
        stamp = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            if date_only and len(value.strip()) == 10:
                return stamp.replace(tzinfo=timezone.utc)
            return None
        return stamp.astimezone(timezone.utc)
    except ValueError:
        return None


def records(data, key):
    values = data if isinstance(data, list) else data.get(key) if isinstance(data, dict) else None
    return [v for v in values if isinstance(v, dict)] if isinstance(values, list) else []


def fields(obj, prefix="", depth=0):
    if depth > 4:
        return set()
    result = set()
    if isinstance(obj, dict):
        for key, val in obj.items():
            name = prefix + "." + str(key) if prefix else str(key)
            result.add(name)
            result.update(fields(val, name, depth + 1))
    elif isinstance(obj, list):
        result.add(prefix + "[]")
        for val in obj[:5]:
            result.update(fields(val, prefix + "[]", depth + 1))
    return result


class ApiUnavailable(Exception):
    pass


class Collector:
    def __init__(self, session, root, *, season="2627", api_key="", now=now_utc, delay=1.0):
        if not safe_id(season):
            raise ValueError("Invalid season")
        self.session, self.root, self.season = session, Path(root), season
        self.api_key, self.now, self.delay = api_key, now, max(1.0, float(delay))
        self.lock = asyncio.Lock()
        self.paused = None
        self.last_request = 0.0
        self.last_catalog = None
        self.last_competitions = {}
        self.last_live = {}
        self.last_broad = set()
        self.events = []
        self.competitions = {}
        self.races = {}
        self.status = {"state": "starting", "season": season, "discovered_races": 0}

    def write_json(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(path.name + ".tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp.replace(path)

    async def ensure_key(self):
        if self.api_key:
            return
        async with self.session.get(SITE, timeout=20) as response:
            if response.status != 200:
                raise ApiUnavailable("Public IBU site unavailable")
            html = await response.text()
        scripts = SCRIPT_RE.findall(html)
        scripts.sort(key=lambda name: "app" not in name.rsplit("/", 1)[-1].lower())
        for script in scripts[:12]:
            url = urljoin(SITE, script)
            if not url.startswith(SITE) or not url.split("?", 1)[0].endswith(".js"):
                continue
            await asyncio.sleep(self.delay)
            try:
                async with self.session.get(url, timeout=20) as response:
                    if response.status != 200:
                        continue
                    match = KEY_RE.search(await response.text())
                    if match:
                        self.api_key = match.group(1)
                        return
            except (asyncio.TimeoutError, OSError):
                continue
        raise ApiUnavailable("No frontend API key discovered; set api_key in project settings")

    async def query(self, endpoint, params, phase, token):
        if endpoint not in ENDPOINTS or self.paused:
            raise ApiUnavailable("Collector paused or unsupported endpoint")
        await self.ensure_key()
        wait = self.delay - (time.monotonic() - self.last_request)
        if wait > 0:
            await asyncio.sleep(wait)
        self.last_request = time.monotonic()
        stamp = self.now()
        audit = {"received_utc": stamp.isoformat(), "endpoint": endpoint,
                 "params": params, "phase": phase}
        try:
            async with self.session.get(API + endpoint, params=params,
                                        headers={"apikey": self.api_key, "Referer": SITE},
                                        timeout=25) as response:
                audit["status"] = response.status
                body = await response.read()
                audit["bytes"] = len(body)
                audit["sha256"] = hashlib.sha256(body).hexdigest()
                if response.status in (401, 403, 429):
                    self.paused = "Provider denied or rate-limited (HTTP %s)" % response.status
                    audit["error"] = self.paused
                    raise ApiUnavailable(self.paused)
                if response.status != 200 or len(body) > 8_000_000:
                    audit["error"] = "Non-200 or oversized response; not archived"
                    return None
                try:
                    data = json.loads(body)
                except ValueError:
                    audit["error"] = "Non-JSON response; not archived"
                    return None
                audit["fields"] = sorted(fields(data))
                name = stamp.strftime("%Y%m%dT%H%M%S_%fZ") + "_" + endpoint
                if "TypeId" in params:
                    name += "_" + params["TypeId"]
                target = self.root / "data" / "raw" / phase / token / (name + ".json")
                self.write_json(target, data)
                audit["file"] = str(target.relative_to(self.root))
                return data
        except ApiUnavailable:
            raise
        except (asyncio.TimeoutError, OSError) as exc:
            audit["error"] = "Transport: " + type(exc).__name__
            return None
        finally:
            target = self.root / "data" / "audit" / (stamp.strftime("%Y%m%d") + ".jsonl")
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("a", encoding="utf-8") as file:
                file.write(json.dumps(audit, ensure_ascii=False) + "\n")

    async def catalog(self, now):
        seasons = await self.query("Seasons", {}, "catalog", self.season)
        events = await self.query("Events", {"SeasonId": self.season, "Level": "0"},
                                  "catalog", self.season)
        await self.query("Cups", {"SeasonId": self.season}, "catalog", self.season)
        if events is not None:
            self.events = records(events, "Events")
        self.last_catalog = now
        self.status["events"] = len(self.events)
        self.status["season_available"] = seasons is not None

    def event_near(self, event, now):
        start = parse_date(event.get("StartDate"), date_only=True)
        end = parse_date(event.get("EndDate"), date_only=True)
        if start is None:
            return False
        return start - timedelta(days=1) <= now <= (end or start + timedelta(days=4)) + timedelta(days=1)

    async def discover(self, now):
        for event in self.events:
            event_id = safe_id(event.get("EventId"))
            if not event_id or not self.event_near(event, now):
                continue
            last = self.last_competitions.get(event_id)
            if last is not None and now - last < timedelta(hours=2):
                continue
            data = await self.query("Competitions", {"EventId": event_id},
                                    "competitions", event_id)
            self.last_competitions[event_id] = now
            if data is None:
                continue
            self.competitions[event_id] = records(data, "Competitions")
            for comp in self.competitions[event_id]:
                race = safe_id(comp.get("RaceId"))
                # Never turn an ambiguous local timestamp into a scheduled UTC start.
                stamp = next((stamp for field in ("StartTime", "StartDateTime", "StartDate")
                              if (stamp := parse_date(comp.get(field))) is not None), None)
                if race and stamp:
                    self.races[race] = stamp
        self.status["events_with_competitions"] = len(self.competitions)

    async def sample(self, race, phase):
        data = await self.query("Results", {"RaceId": race}, phase, race)
        if data is None:
            return
        for kind in (LIVE_ANALYSIS if phase == "live" else ANALYSIS):
            await self.query("AnalyticResults", {"RaceId": race, "TypeId": kind},
                             phase, race)
        self.status["last_race"] = race
        self.status["last_phase"] = phase
        self.status["last_capture_utc"] = self.now().isoformat()

    async def cycle(self):
        if self.lock.locked() or self.paused:
            return
        async with self.lock:
            now = self.now()
            self.status["last_checked_utc"] = now.isoformat()
            try:
                if self.last_catalog is None or now - self.last_catalog >= timedelta(hours=6):
                    await self.catalog(now)
                await self.discover(now)
                for race, start in sorted(self.races.items(), key=lambda row: row[1]):
                    if not (start - timedelta(hours=2) <= now <= start + timedelta(hours=5)):
                        continue
                    if start - timedelta(minutes=45) <= now < start and (race, "pre") not in self.last_broad:
                        await self.sample(race, "pre")
                        self.last_broad.add((race, "pre"))
                    if start <= now <= start + timedelta(hours=3):
                        previous = self.last_live.get(race)
                        if previous is None or now - previous >= timedelta(seconds=60):
                            await self.sample(race, "live")
                            self.last_live[race] = now
                    if now > start + timedelta(hours=3) and (race, "post") not in self.last_broad:
                        await self.sample(race, "post")
                        self.last_broad.add((race, "post"))
                self.status["state"] = "running"
                self.status.pop("last_error", None)
            except ApiUnavailable as exc:
                self.status["state"] = "paused" if self.paused else "error"
                self.status["last_error"] = str(exc)
            except Exception as exc:
                self.status["state"] = "error"
                self.status["last_error"] = type(exc).__name__ + " during collector cycle"
            finally:
                self.status["discovered_races"] = len(self.races)
                self.write_json(self.root / "status.json", self.status)
