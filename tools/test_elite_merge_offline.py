"""Offline regression tests for REST/SignalR merger."""
import json
import tempfile
import unittest
from pathlib import Path
from elite_merge_offline import merge, milliseconds, seconds_between


class MergeTests(unittest.TestCase):
    def write(self, directory, name, values):
        path = Path(directory) / name
        path.write_text("".join(json.dumps(v) + "\n" for v in values), encoding="utf-8")
        return path

    def test_valid_runtime_and_ranges(self):
        self.assertIsNone(milliseconds(129600000000))
        self.assertIsNone(milliseconds(None))
        self.assertEqual(milliseconds(1392800), 1392800)
        self.assertEqual(seconds_between(
            "2026-11-15T11:08:15.079392",
            "2026-11-15T11:08:46.684392"), 31.605)
        self.assertIsNone(seconds_between(
            "2026-11-15T11:08:46", "2026-11-15T11:08:15"))

    def test_late_hour_shift_does_not_replace_valid_shooting_times(self):
        with tempfile.TemporaryDirectory() as temp:
            start = {"endpoint": "startlist", "race_id": "2854",
                     "payload": {"Data": [{"AthleteID": "a_2854", "ClassID": "men_2854",
                                          "Startno": 128, "StartTime": "2026-11-15T12:14:00"}]}}
            before = {"kind": "shooting", "race_id": "2854", "athlete_id": "a_2854",
                      "shoot_nr": 2, "lane": 14, "sum_shooted": 5, "missed": 1,
                      "shoot_string": "oooxo", "captured_utc": "2026-11-15T11:34:21+00:00",
                      "in_time": "2026-11-15T11:31:06.975414",
                      "out_time": "2026-11-15T11:31:44.196760"}
            later = {**before, "captured_utc": "2026-11-15T11:34:22+00:00",
                     "in_time": "2026-11-15T10:31:06.975",
                     "out_time": "2026-11-15T10:31:44.196"}
            rest = self.write(temp, "rest.jsonl", [start])
            events = self.write(temp, "events.jsonl", [before, later])
            rows, report = merge([rest], [events])
            shooting = rows[0]["shootings"][0]
            self.assertEqual(shooting["in_time"], before["in_time"])
            self.assertEqual(shooting["out_time"], before["out_time"])
            self.assertEqual(shooting["shoot_string"], "oooxo")
            self.assertEqual(report["warnings"]["shooting_late_hour_shift"], 1)
            self.assertIn("shoot_2_late_hour_shift", rows[0]["quality_flags"])

    def test_merge_class_safe_and_never_invents_shot_times(self):
        with tempfile.TemporaryDirectory() as temp:
            person = {"AthleteID": "ath_2854", "ClassID": "men_2854",
                      "Startno": 5, "StartTime": "2026-11-15T12:00:30",
                      "Athlete": {"FormatedName": "Example", "Nation": "SWE"}}
            start = {"endpoint": "startlist", "race_id": "2854",
                     "payload": {"Data": [person]}}
            result = {"endpoint": "results", "race_id": "2854",
                      "class_id": "men_2854", "ipos": "21",
                      "captured_utc": "2026-11-15T13:00:00+00:00",
                      "payload": {"Data": [{**person, "Time": {
                          "Ipos": 21, "IntermediateID": "finish_2854",
                          "RunTimeMS": 1392800, "PassTime": "2026-11-15T12:23:12",
                          "RankClass": 1}}]}}
            sentinel = {"endpoint": "results", "race_id": "2854",
                        "class_id": "men_2854", "ipos": "20",
                        "payload": {"Data": [{**person, "Time": {
                            "Ipos": 20, "RunTimeMS": 129600000000}}]}}
            updates = [
                {"kind": "shooting", "race_id": "2854", "athlete_id": "ath_2854",
                 "shoot_nr": 1, "captured_utc": "2026-11-15T11:10:01+00:00",
                 "sum_shooted": 1, "missed": 0, "shots": [],
                 "in_time": "2026-11-15T11:09:00", "out_time": None},
                {"kind": "shooting", "race_id": "2854", "athlete_id": "ath_2854",
                 "shoot_nr": 1, "captured_utc": "2026-11-15T11:11:00+00:00",
                 "sum_shooted": 5, "missed": 1, "shots": [],
                 "in_time": "2026-11-15T11:09:00",
                 "out_time": "2026-11-15T11:09:40"},
                {"kind": "shooting", "race_id": "2854", "athlete_id": None,
                 "shoot_nr": 0, "sum_shooted": 0}
            ]
            updates.append({
                "kind": "shooting", "race_id": "2854", "athlete_id": "ath_2854",
                "shoot_nr": 1, "captured_utc": "2026-11-15T11:13:00+00:00",
                "sum_shooted": 0, "missed": 1, "shots": [],
                "in_time": "2026-11-15T11:13:00",
                "out_time": "2026-11-15T11:13:00",
            })
            rest = self.write(temp, "rest.jsonl", [start, result, sentinel])
            events = self.write(temp, "events.jsonl", updates)
            rows, report = merge([rest], [events])
            self.assertEqual(len(rows), 1)
            self.assertEqual(len(rows[0]["checkpoints"]), 1)
            self.assertEqual(rows[0]["checkpoints"][0]["ipos"], "21")
            self.assertEqual(rows[0]["nation"], "SWE")
            self.assertEqual(rows[0]["shootings"][0]["range_seconds"], 40.0)
            self.assertEqual(rows[0]["shootings"][0]["first_to_last_shot_seconds"], None)
            self.assertEqual(rows[0]["shootings"][0]["observed_counts"], [1, 5])
            self.assertIn("shoot_1_individual_shot_timestamps_missing",
                          rows[0]["quality_flags"])
            self.assertIn("shoot_1_reset_after_shots", rows[0]["quality_flags"])
            self.assertEqual(report["warnings"]["shooting_reset_after_shots"], 1)
            self.assertEqual(report["warnings"]["unidentified_shooting_updates"], 1)
            self.assertEqual(report["warnings"]["invalid_or_missing_runtime"], 1)


if __name__ == "__main__":
    unittest.main()
