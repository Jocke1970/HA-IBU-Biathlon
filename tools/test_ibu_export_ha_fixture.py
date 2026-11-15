"""Tests for safe export of an offline biathlon UI fixture."""
import json
import tempfile
import unittest
from pathlib import Path

from ibu_export_ha_fixture import export_fixture, validate_snapshot


def fixture():
    return {
        "backend_type": "offline_joined_replay",
        "classes": {"men": [{"bib": 101, "name": "Axel"}]},
        "shooting_range": [{"lane": 3, "shots_count": 5}],
        "clocks": {"results": {}, "shooting": {}},
        "sources": {
            "results": {"live_verified": False, "transport_status": "offline_replay"},
            "shooting": {"live_verified": False, "transport_status": "offline_replay"}
        }
    }


class ExportTests(unittest.TestCase):
    def test_valid_offline_fixture_is_exported(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "input.json"
            target = Path(temp) / "ha" / "idre.json"
            source.write_text(json.dumps(fixture()), encoding="utf-8")
            report = export_fixture(source, target)
            self.assertEqual(report["class_counts"], {"men": 1})
            self.assertEqual(json.loads(target.read_text())["shooting_range"][0]["lane"], 3)

    def test_reject_live_or_unverified_provider(self):
        data = fixture()
        data["sources"]["shooting"]["live_verified"] = True
        with self.assertRaisesRegex(ValueError, "non-live"):
            validate_snapshot(data)
        data["sources"]["shooting"]["live_verified"] = False
        data["sources"]["results"].pop("transport_status")
        with self.assertRaisesRegex(ValueError, "offline_replay"):
            validate_snapshot(data)

    def test_refuse_to_overwrite_input(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "original.json"
            source.write_text(json.dumps(fixture()), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "differ"):
                export_fixture(source, source)


if __name__ == "__main__":
    unittest.main()
