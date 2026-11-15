"""Regression tests for provisional course station mapping."""
import unittest
from ibu_station_catalog import build_catalog


class StationCatalogTests(unittest.TestCase):
    def test_elapsed_time_not_ipos_defines_course_order(self):
        athletes = [
            {"race_id": "2854", "class_id": "men", "athlete_id": "a",
             "checkpoints": [
                 {"ipos": "21", "intermediate_id": "finish", "runtime_ms": 200000},
                 {"ipos": "8", "intermediate_id": "mid", "runtime_ms": 120000},
                 {"ipos": "1", "intermediate_id": "start_split", "runtime_ms": 40000}]},
            {"race_id": "2854", "class_id": "men", "athlete_id": "b",
             "checkpoints": [
                 {"ipos": "8", "intermediate_id": "mid", "runtime_ms": 140000},
                 {"ipos": "21", "intermediate_id": "finish", "runtime_ms": 240000},
                 {"ipos": "1", "intermediate_id": "start_split", "runtime_ms": 50000}]},
            {"race_id": "2854", "class_id": "women", "athlete_id": "c",
             "checkpoints": [
                 {"ipos": "18", "intermediate_id": "women_finish", "runtime_ms": 150000}]}
        ]
        result = build_catalog(athletes)["classes"]
        men = result["2854:men"]
        self.assertEqual([x["station_id"] for x in men["stations"]],
                         ["start_split", "mid", "finish"])
        self.assertEqual(men["stations"][2]["immediate_predecessor_votes"]["mid"], 2)
        self.assertFalse(men["stations"][2]["finish_verified"])
        self.assertFalse(men["order_verified"])
        self.assertEqual(result["2854:women"]["finish_candidate_unverified"],
                         "women_finish")

    def test_missing_and_invalid_timing_are_excluded(self):
        result = build_catalog([{
            "race_id": "1", "class_id": "men", "athlete_id": "a",
            "checkpoints": [{"ipos": "1", "intermediate_id": "x", "runtime_ms": 999999999},
                            {"ipos": "2", "intermediate_id": "y", "runtime_ms": 45000}]
        }])
        self.assertEqual(result["classes"]["1:men"]["station_count"], 1)
        self.assertIsNone(result["classes"]["1:men"]["stations"][0]["official_label"])


if __name__ == "__main__":
    unittest.main()
