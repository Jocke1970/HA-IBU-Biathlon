"""Offline leaderboard regression tests: receipt-time and checkpoint-local ranking."""
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from ibu_leaderboard_replay import build_snapshot


class LeaderboardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)

    def save(self, name, data):
        path = self.base / name
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return path

    def snapshots(self, records):
        path = self.base / "rest.jsonl"
        path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
        return path

    @staticmethod
    def athlete(id, cls, bib, runtime, station):
        return {
            "AthleteID": id, "ClassID": cls, "Startno": bib,
            "Athlete": {"FormatedName": id, "Nation": "SWE"},
            "Time": {"RunTimeMS": runtime, "IntermediateID": station,
                     "PassTime": "2026-11-15T12:04:00"}
        }

    def test_observed_does_not_see_future_snapshot(self):
        early = {"endpoint": "startlist", "race_id": "2854",
                 "captured_utc": "2026-11-15T11:00:00+00:00",
                 "payload": {"Data": [self.athlete("a", "men", 101, 170000, "p1")]}}
        late = {"endpoint": "results", "race_id": "2854", "class_id": "men", "ipos": "1",
                "captured_utc": "2026-11-15T11:10:00+00:00",
                "payload": {"Data": [self.athlete("a", "men", 101, 170000, "p1")]}}
        path = self.snapshots([early, late])
        before = build_snapshot("observed", datetime.fromisoformat("2026-11-15T12:05:00"), [path])
        self.assertEqual(before["classes"]["men"][0]["last_checkpoint"], None)
        self.assertEqual(before["audit"]["skipped_future_snapshots"], 1)
        after = build_snapshot("observed", datetime.fromisoformat("2026-11-15T12:11:00"), [path])
        self.assertEqual(after["classes"]["men"][0]["last_checkpoint"]["elapsed_ms"], 170000)

    def test_received_future_passing_never_affects_station_rank(self):
        early = {"endpoint": "startlist", "race_id": "2854",
                 "captured_utc": "2026-11-15T11:00:00+00:00",
                 "payload": {"Data": [
                     self.athlete("a", "men", 101, 180000, "cp"),
                     self.athlete("b", "men", 102, 170000, "cp")]}}
        row_a = self.athlete("a", "men", 101, 180000, "cp")
        row_a["Time"]["PassTime"] = "2026-11-15T12:03:00"
        row_b = self.athlete("b", "men", 102, 170000, "cp")
        row_b["Time"]["PassTime"] = "2026-11-15T12:20:00"
        results = {"endpoint": "results", "race_id": "2854",
                   "class_id": "men", "ipos": "1",
                   "captured_utc": "2026-11-15T11:04:00+00:00",
                   "payload": {"Data": [row_a, row_b]}}
        path = self.snapshots([early, results])
        state = build_snapshot("observed", datetime.fromisoformat("2026-11-15T12:05:00"),
                               [path])
        by_id = {p["athlete_id"]: p for p in state["classes"]["men"]}
        self.assertEqual(by_id["a"]["last_checkpoint"]["checkpoint_position"], 1)
        self.assertEqual(by_id["a"]["last_checkpoint"]["comparable_athletes"], 1)
        self.assertIsNone(by_id["b"]["last_checkpoint"])
        self.assertEqual(len(state["checkpoint_groups"]), 1)
        self.assertEqual(next(iter(state["checkpoint_groups"].values()))["comparable_athletes"], 1)

    def test_idre_dnf_dns_never_receive_elapsed_rank(self):
        rows = [
            self.athlete("grete", "women", 23, 120960000000, "finish"),
            self.athlete("annie", "women", 45, 129600000000, "finish"),
            self.athlete("finisher", "women", 38, 2000000, "finish"),
        ]
        rows[0]["Status"] = 101
        rows[1]["Status"] = 102
        rows[2]["Status"] = 5
        frame = {"endpoint": "results", "race_id": "2854",
                 "class_id": "women", "ipos": "18",
                 "captured_utc": "2026-11-15T11:40:00+00:00",
                 "payload": {"Data": rows}}
        path = self.snapshots([frame])
        snapshot = build_snapshot("observed",
                                  datetime.fromisoformat("2026-11-15T13:40:00"), [path])
        by_id = {x["athlete_id"]: x for x in snapshot["classes"]["women"]}
        self.assertEqual(by_id["grete"]["status"], "DNF")
        self.assertEqual(by_id["annie"]["status"], "DNS")
        self.assertIsNone(by_id["grete"]["last_checkpoint"])
        self.assertIsNone(by_id["annie"]["last_checkpoint"])
        self.assertEqual(by_id["finisher"]["last_checkpoint"]["checkpoint_position"], 1)

    def test_rank_only_among_same_class_and_station(self):
        def a(id, cls, bib, station, elapsed):
            return {"race_id": "2854", "athlete_id": id, "class_id": cls,
                    "bib": bib, "name": id, "nation": "SWE",
                    "checkpoints": [{"ipos": "1", "intermediate_id": station,
                                     "runtime_ms": elapsed,
                                     "pass_time": "2026-11-15T12:04:00"}]}
        merged = self.save("merged.json", [
            a("a", "men", 101, "cp1", 200000),
            a("b", "men", 102, "cp1", 180000),
            a("c", "men", 103, "cp2", 90000),
            a("d", "women", 1, "cp1", 100000),
        ])
        result = build_snapshot("reconstructed", datetime.fromisoformat("2026-11-15T12:05:00"),
                                merged_path=merged)
        men = {p["athlete_id"]: p for p in result["classes"]["men"]}
        self.assertEqual(men["b"]["last_checkpoint"]["checkpoint_position"], 1)
        self.assertEqual(men["a"]["last_checkpoint"]["checkpoint_position"], 2)
        self.assertEqual(men["a"]["last_checkpoint"]["checkpoint_diff_ms"], 20000)
        self.assertEqual(men["c"]["last_checkpoint"]["checkpoint_position"], 1)
        self.assertIsNone(men["c"]["overall_position"])
        self.assertEqual(result["athlete_list_sort"], "bib_ascending_not_overall_position")
        self.assertEqual(len(result["checkpoint_groups"]), 3)
        self.assertEqual(result["classes"]["women"][0]["last_checkpoint"]["checkpoint_position"], 1)

    def test_reconstructed_no_future_passings_and_ties(self):
        merged = self.save("merged.json", [
            {"race_id": "1", "athlete_id": "a", "class_id": "men", "bib": 1,
             "checkpoints": [{"ipos": "1", "intermediate_id": "cp",
                              "runtime_ms": 100000, "pass_time": "2026-11-15T12:01:40"},
                             {"ipos": "2", "intermediate_id": "finish",
                              "runtime_ms": 200000, "pass_time": "2026-11-15T12:03:20"}]},
            {"race_id": "1", "athlete_id": "b", "class_id": "men", "bib": 2,
             "checkpoints": [{"ipos": "1", "intermediate_id": "cp",
                              "runtime_ms": 100000, "pass_time": "2026-11-15T12:01:40"}]},
        ])
        early = build_snapshot("reconstructed", datetime.fromisoformat("2026-11-15T12:02:00"),
                               merged_path=merged)
        self.assertEqual(early["classes"]["men"][0]["last_checkpoint"]["checkpoint_position"], 1)
        self.assertEqual(early["classes"]["men"][1]["last_checkpoint"]["checkpoint_position"], 1)
        late = build_snapshot("reconstructed", datetime.fromisoformat("2026-11-15T12:03:30"),
                              merged_path=merged)
        by_id = {r["athlete_id"]: r for r in late["classes"]["men"]}
        self.assertEqual(by_id["a"]["last_checkpoint"]["station_id"], "finish")
        self.assertEqual(by_id["a"]["status"], "passed_checkpoint")
        finished = build_snapshot("reconstructed", datetime.fromisoformat("2026-11-15T12:03:30"),
                                  merged_path=merged, finish_stations=["finish"])
        self.assertEqual(finished["classes"]["men"][0]["status"], "finished")


if __name__ == "__main__":
    unittest.main()
