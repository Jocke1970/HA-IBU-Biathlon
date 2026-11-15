"""Regression tests for progressive SignalR shooting replay."""
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from ibu_signalr_replay import replay_messages


class SignalrReplayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "events.jsonl"
        self.metadata = [{"race_id": "2854", "athlete_id": "a", "class_id": "men",
                          "bib": 101, "name": "Athlete A", "nation": "SWE"}]

    def record(self, capture, shots, *, out=None, missed=0, pattern="", start="2026-11-15T11:08:00", lane=3):
        return {"kind": "shooting", "race_id": "2854", "athlete_id": "a",
                "shoot_nr": 1, "start_no": 101, "lane": lane,
                "sum_shooted": shots, "shoot_string": pattern,
                "missed": missed, "captured_utc": "2026-11-15T" + capture + "+00:00",
                "in_time": start, "out_time": out, "shots": []}

    def save(self, records):
        self.path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")

    def view(self, clock):
        return replay_messages([self.path], datetime.fromisoformat("2026-11-15T" + clock),
                               self.metadata)

    def test_progress_without_future_result_leak(self):
        self.save([
            self.record("11:08:02", 0, pattern="_____"),
            self.record("11:08:08", 1, pattern="o____"),
            self.record("11:08:16", 2, pattern="ox___", missed=1),
            self.record("11:08:32", 5, pattern="oxooo", missed=1,
                        out="2026-11-15T11:08:30")])
        self.assertEqual(len(self.view("12:08:01")["shooting_range"]), 0)
        before = self.view("12:08:10")["shooting_range"][0]
        self.assertEqual(before["shots_count"], 1)
        self.assertIsNone(before["out_time"])
        self.assertEqual(before["shoot_string"], "o____")
        middle = self.view("12:08:20")["shooting_range"][0]
        self.assertEqual(middle["shots_count"], 2)
        self.assertEqual(middle["missed"], 1)
        completed = self.view("12:08:32")["shooting_range"][0]
        self.assertEqual(completed["state"], "recently_finished")
        self.assertEqual(completed["shots_count"], 5)
        self.assertEqual(completed["out_time"], "2026-11-15T12:08:30")
        self.assertEqual(len(self.view("12:08:44")["shooting_range"]), 1)
        self.assertEqual(len(self.view("12:08:45")["shooting_range"]), 0)

    def test_late_zero_reset_does_not_erase_result(self):
        self.save([
            self.record("11:08:30", 5, pattern="ooooo", out="2026-11-15T11:08:30"),
            self.record("11:08:31", 0, pattern="", out="2026-11-15T11:08:31", lane=None)])
        row = self.view("12:08:32")["shooting_range"][0]
        self.assertEqual(row["shots_count"], 5)
        self.assertEqual(row["anomalies"], ["late_zero_reset_ignored"])

    def test_no_shot_times_no_invention(self):
        self.save([self.record("11:08:08", 1, pattern="o____")])
        row = self.view("12:08:10")["shooting_range"][0]
        self.assertFalse(row["individual_shot_times_available"])
        self.assertEqual(row["shots_with_timestamps"], [])
        self.assertEqual(row["state"], "active_unconfirmed")

    def test_late_hour_shift_preserves_clocks(self):
        original = self.record("11:08:32", 5, pattern="ooooo", out="2026-11-15T11:08:30")
        shifted = self.record("11:08:33", 5, pattern="ooooo",
                              out="2026-11-15T10:08:30",
                              start="2026-11-15T10:08:00")
        self.save([original, shifted])
        row = self.view("12:08:34")["shooting_range"][0]
        self.assertEqual(row["out_time"], "2026-11-15T12:08:30")
        self.assertIn("late_hour_shift_corrected", row["anomalies"])


if __name__ == "__main__":
    unittest.main()
