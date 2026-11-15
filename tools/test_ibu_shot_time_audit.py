"""Tests of raw/compact shooting clock-field audit. Never invent shot timing."""
import json
import tempfile
import unittest
from pathlib import Path

from ibu_shot_time_audit import audit, inspect_object


class ShotTimeAuditTests(unittest.TestCase):
    def test_mixed_target_time_spellings(self):
        counts, fields = inspect_object("source4", {
            "AthleteID": "ath", "ShootNr": 1, "SumShooted": 2,
            "Target1": {"Hit": True, "Shootime": "2026-11-15T12:08:03"},
            "Target2": {"Hit": False, "ShootTime": "2026-11-15T12:08:07",
                        "ShootRunTime": 4000},
            "Target3": {"Hit": False, "Shootime": None}
        })
        self.assertEqual(counts["shot_timestamps_present"], 2)
        self.assertEqual(counts["shot_runtime_present"], 1)
        self.assertEqual(counts["updates_with_multiple_timestamps"], 1)
        self.assertIn("Target*.Shootime", fields)
        self.assertIn("Target*.ShootRunTime", fields)

    def test_compact_and_raw_payloads_without_time_are_not_invented(self):
        with tempfile.TemporaryDirectory() as folder:
            capture = Path(folder) / "events.jsonl"
            capture.write_text("\n".join(json.dumps(x) for x in [
                {"kind": "shooting", "race_id": "2854", "athlete_id": "ath",
                 "shoot_nr": 1, "sum_shooted": 5, "shots": []},
                {"kind": "receive", "payload": {"Source": 4, "Object": {
                    "RaceID": "2854", "AthleteID": "ath", "ShootNr": 1,
                    "SumShooted": 5, "Target1": {"Hit": True, "Shootime": None}}}},
                {"kind": "race_change", "race_id": "2854"}
            ]) + "\n", encoding="utf-8")
            report = audit([capture])
            self.assertEqual(report["shooting_updates"], 2)
            self.assertEqual(report["individual_shot_timestamp_values"], 0)
            self.assertEqual(report["series_with_any_shot_timestamp"], 0)

    def test_existing_compact_shot_timestamp_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            capture = Path(folder) / "events.jsonl"
            capture.write_text(json.dumps({
                "kind": "shooting", "race_id": "2854", "athlete_id": "x",
                "shoot_nr": 2, "sum_shooted": 1,
                "shots": [{"number": 1, "time": "2026-11-15T12:02:03",
                           "shoot_runtime": 1300}]
            }) + "\n", encoding="utf-8")
            report = audit([capture])
            self.assertEqual(report["individual_shot_timestamp_values"], 1)
            self.assertEqual(report["shot_runtime_values"], 1)
            self.assertEqual(report["series_with_any_shot_timestamp"], 1)


if __name__ == "__main__":
    unittest.main()
