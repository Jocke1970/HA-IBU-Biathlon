"""Network-free regressions for scheduled IBU capture and JSON archival."""
import asyncio
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

PATH = Path(__file__).resolve().parents[1] / "custom_components" / "ibu_biathlon" / "collector.py"
SPEC = importlib.util.spec_from_file_location("ibu_capture_pure", PATH)
collector_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(collector_module)
Collector = collector_module.Collector


class FakeResponse:
    def __init__(self, value=None, status=200):
        self.status = status
        self.body = json.dumps(value if value is not None else []).encode()
    async def __aenter__(self):
        return self
    async def __aexit__(self, *args):
        return False
    async def read(self):
        return self.body
    async def text(self):
        return self.body.decode()


class FakeSession:
    def __init__(self, value=None, status=200):
        self.value, self.status, self.calls = value, status, []
    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResponse(self.value, self.status)


class HaCollectorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.clock = datetime(2026, 11, 26, 12, tzinfo=timezone.utc)
        self.session = FakeSession([])
        self.collector = Collector(self.session, self.tmp.name, api_key="private-test-key",
                                   now=lambda: self.clock, delay=1)
        self.collector.delay = 0

    async def test_key_discovery_reports_script_count_without_secrets(self):
        session = FakeSession([])
        session.get = lambda *a, **k: FakeResponse({"irrelevant":"no-script"})
        collector = Collector(session, self.tmp.name, now=lambda: self.clock, delay=1)
        with self.assertRaises(collector_module.ApiUnavailable) as failure:
            await collector.ensure_key()
        self.assertIn("scripts: 0", str(failure.exception))
        self.assertEqual(collector.status["key_discovery_scripts_found"], 0)
        self.assertEqual(collector.status["key_discovery_scripts_checked"], 0)

    async def test_modern_bundle_asset_discovery(self):
        html = ('<script type="module" src=/assets/app-abc.js?v=1></script>'
                '<link rel="modulepreload" href="/assets/chunk.js">'
                '<script defer src="/assets/vendor.js"></script>')
        assets = collector_module.frontend_assets(html)
        self.assertEqual(len(assets), 3)
        self.assertTrue(assets[0].endswith("app-abc.js?v=1"))
        self.assertNotIn("https://evil.example/extra.js",
                         collector_module.frontend_assets(
                             '<script src="https://evil.example/extra.js"></script>'))

    async def test_clock_parsing_fails_closed(self):
        self.assertIsNone(collector_module.parse_date("2026-11-26T14:00:00"))
        self.assertIsNone(collector_module.parse_date("2026-11-26"))
        self.assertEqual(collector_module.parse_date("2026-11-26", date_only=True).hour, 0)
        self.assertEqual(collector_module.parse_date("2026-11-26T00:00:00", date_only=True).day, 26)
        self.assertEqual(collector_module.parse_date("2026-11-26T14:00:00Z").hour, 14)

    async def test_raw_capture_audit_and_no_token(self):
        race = "BT2627SWRLCP01SMIN"
        await self.collector.query("Results", {"RaceId": race}, "live", race)
        files = list((Path(self.tmp.name) / "data" / "raw").rglob("*.json"))
        audits = list((Path(self.tmp.name) / "data" / "audit").glob("*.jsonl"))
        self.assertEqual(len(files), 1)
        self.assertEqual(len(audits), 1)
        self.assertNotIn("private-test-key", files[0].read_text() + audits[0].read_text())

    async def test_denial_pauses_collection(self):
        self.session.status = 429
        with self.assertRaises(collector_module.ApiUnavailable):
            await self.collector.query("Results", {"RaceId": "x"}, "live", "x")
        with self.assertRaises(collector_module.ApiUnavailable):
            await self.collector.query("Results", {"RaceId": "x"}, "live", "x")
        self.assertEqual(len(self.session.calls), 1)

    async def test_event_and_race_discovery(self):
        self.collector.events = [{"EventId": "BT2627SWRLCP01",
                                  "StartDate": "2026-11-25", "EndDate": "2026-11-29"}]
        self.session.value = [{"RaceId": "BT2627SWRLCP01SMIN",
                               "StartTime": "2026-11-26T13:00:00Z"}]
        await self.collector.discover(self.clock)
        self.assertEqual(len(self.collector.races), 1)

    async def test_unspecified_timezone_not_scheduled(self):
        self.collector.events = [{"EventId": "BT2627SWRLCP01", "StartDate": "2026-11-25"}]
        self.session.value = [{"RaceId": "BT2627SWRLCP01SMIN",
                               "StartTime": "2026-11-26T13:00:00"}]
        await self.collector.discover(self.clock)
        self.assertEqual(self.collector.races, {})

    async def test_official_finished_race_can_be_collected_after_five_hours(self):
        race = "BT2627SWRLCP01SMIN"
        from datetime import timedelta
        self.collector.race_status[race] = {
            "schedule": "FINISHED", "result": "OFFICIAL"}
        start = self.clock - timedelta(hours=8)
        self.assertTrue(self.collector.needs_post_capture(race, start, self.clock))
        self.collector.write_json(self.collector.completed_marker(race),
                                  {"race_id": race, "captured_utc": self.clock.isoformat()})
        self.assertFalse(self.collector.needs_post_capture(race, start, self.clock))
        # Persisted marker prevents re-archiving after restart.
        restarted = Collector(self.session, self.tmp.name, api_key="private-test-key",
                              now=lambda: self.clock)
        restarted.race_status[race] = {"schedule": "FINISHED", "result": "OFFICIAL"}
        self.assertFalse(restarted.needs_post_capture(race, start, self.clock))

    async def test_no_false_post_capture_for_unofficial_or_very_old_event(self):
        from datetime import timedelta
        race = "BT2627SIBUCP01SWSP"
        self.collector.race_status[race] = {
            "schedule": "SCHEDULED", "result": "START_LIST"}
        start = self.clock - timedelta(hours=8)
        self.assertFalse(self.collector.needs_post_capture(race, start, self.clock))
        self.collector.race_status[race]["result"] = "OFFICIAL"
        self.assertFalse(self.collector.needs_post_capture(
            race, self.clock - timedelta(days=8), self.clock))

    async def test_live_and_broad_capture_counts(self):
        race = "BT2627SWRLCP01SMIN"
        await self.collector.sample(race, "live")
        self.assertEqual(len(self.session.calls), 4)
        self.session.calls.clear()
        await self.collector.sample(race, "post")
        self.assertEqual(len(self.session.calls), 1 + len(collector_module.ANALYSIS))


if __name__ == "__main__":
    unittest.main()
