"""Tests for the combined UI-facing livetiming snapshot."""
import json
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from ibu_combined_replay import joined_state


class CombinedTests(unittest.TestCase):
    def test_combined_hides_future_dnf_then_preserves_terminal_status(self):
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            merged = base / "merged.json"
            merged.write_text(json.dumps([
                {"race_id": "2854", "class_id": "women", "athlete_id": "grete",
                 "bib": 23, "name": "Grete Gaim", "nation": "EST",
                 "result_status": "DNF", "source_status_code": 101,
                 "result_status_observed_utc": "2026-11-15T12:36:43+00:00",
                 "checkpoints": []}
            ]), encoding="utf-8")
            events = base / "events.jsonl"
            events.write_text("", encoding="utf-8")
            earlier = joined_state(datetime.fromisoformat("2026-11-15T12:08:50"),
                                   merged=merged, event_files=[events])
            self.assertEqual(earlier["classes"]["women"][0]["display_status"],
                             "no_verified_passing")
            self.assertIsNone(earlier["classes"]["women"][0]["result_status"])
            later = joined_state(datetime.fromisoformat("2026-11-15T13:40:00"),
                                 merged=merged, event_files=[events])
            self.assertEqual(later["classes"]["women"][0]["display_status"], "DNF")
            self.assertEqual(later["classes"]["women"][0]["shooting_range_rows"], 0)

    def test_shooting_and_checkpoint_associate_by_athlete(self):
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            merged = base / "merged.json"
            merged.write_text(json.dumps([
                {"race_id": "2854", "class_id": "men", "athlete_id": "a",
                 "bib": 101, "name": "A", "nation": "SWE",
                 "checkpoints": [{"intermediate_id": "cp1", "ipos": "1",
                                  "runtime_ms": 100000,
                                  "pass_time": "2026-11-15T12:02:00"}]},
                {"race_id": "2854", "class_id": "women", "athlete_id": "b",
                 "bib": 1, "name": "B", "nation": "SWE", "checkpoints": []},
            ]), encoding="utf-8")
            events = base / "events.jsonl"
            events.write_text(json.dumps({
                "kind": "shooting", "race_id": "2854",
                "athlete_id": "a", "start_no": 101, "shoot_nr": 1,
                "sum_shooted": 2, "missed": 0, "shoot_string": "oo",
                "in_time": "2026-11-15T11:03:00", "out_time": None,
                "captured_utc": "2026-11-15T11:03:05+00:00",
                "lane": 3, "shots": []}) + "\n", encoding="utf-8")
            state = joined_state(
                datetime.fromisoformat("2026-11-15T12:03:10"),
                merged=merged, event_files=[events])
            self.assertEqual(len(state["shooting_range"]), 1)
            self.assertEqual(state["shooting_range"][0]["shots_count"], 2)
            self.assertEqual(state["classes"]["men"][0]["shooting_range_rows"], 1)
            self.assertEqual(state["classes"]["women"][0]["shooting_range_rows"], 0)
            self.assertIsNone(state["classes"]["men"][0]["overall_position"])
            self.assertEqual(len(state["checkpoint_groups"]), 1)
            self.assertFalse(state["classes"]["men"][0]["shooting_presence_confirmed"])
            self.assertEqual(state["sources"]["results"]["provider_id"], "ccresult")
            self.assertEqual(state["sources"]["shooting"]["provider_id"], "ccresult")
            self.assertEqual(state["sources"]["shooting"]["last_recorded_receipt_local"],
                             "2026-11-15T12:03:05")
            self.assertEqual(state["sources"]["ibu"]["connection_state"],
                             "not_implemented")
            self.assertFalse(state["sources"]["results"]["live_verified"])
            self.assertEqual(state["clocks"]["results"]["latest_event"]["value_local"],
                             "2026-11-15T12:02:00")
            self.assertIsNone(state["clocks"]["results"]["latest_receipt"]["value_local"])
            self.assertEqual(state["clocks"]["shooting"]["latest_event"]["value_local"],
                             "2026-11-15T12:03:00")
            self.assertEqual(state["clocks"]["shooting"]["latest_receipt"]["value_local"],
                             "2026-11-15T12:03:05")


if __name__ == "__main__":
    unittest.main()
