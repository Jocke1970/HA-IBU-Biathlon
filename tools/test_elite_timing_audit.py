"""Regression tests for the source clock audit."""
import unittest
from elite_timing_audit import audit


class AuditTests(unittest.TestCase):
    def test_separate_classes_and_utc_offset(self):
        rows = [
            {"class_id": "men", "bib": 101, "start_time": "2026-11-15T12:00:00",
             "checkpoints": [
                 {"ipos": "1", "intermediate_id": "a", "runtime_ms": 180000, "rank_at_checkpoint": 10},
                 {"ipos": "21", "intermediate_id": "finish", "runtime_ms": 1600000, "rank_at_checkpoint": 2}
             ],
             "shootings": [{"in_time": "2026-11-15T11:08:00", "out_time": None}]},
            {"class_id": "women", "bib": 1, "start_time": "2026-11-15T10:00:00",
             "checkpoints": [
                 {"ipos": "18", "intermediate_id": "finish_w", "runtime_ms": 1500000}
             ], "shootings": []}
        ]
        result = audit(rows)
        self.assertEqual(result["athletes_by_class"], {"men": 1, "women": 1})
        self.assertEqual(len(result["checkpoint_catalog"]["women"]), 1)
        self.assertEqual(len(result["checkpoint_catalog"]["men"]), 2)
        self.assertEqual(result["checkpoint_catalog"]["women"][0]["official_label"], None)
        self.assertEqual(result["candidate_signalr_to_rest_offsets_hours"]["0"]["valid_finish_window"], 0)
        self.assertEqual(result["candidate_signalr_to_rest_offsets_hours"]["1"]["valid_finish_window"], 1)
        self.assertEqual(result["provisional_best_offset_hours"], 1)

    def test_no_shooting_is_inconclusive(self):
        result = audit([{"class_id": "women", "start_time": None, "checkpoints": [], "shootings": []}])
        self.assertIsNone(result["provisional_best_offset_hours"])


if __name__ == "__main__":
    unittest.main()
