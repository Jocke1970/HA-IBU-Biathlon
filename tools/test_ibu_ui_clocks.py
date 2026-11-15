"""Tests for distinct competition-event and recorder-receipt timestamps."""
import unittest
from datetime import datetime
from ibu_ui_clocks import clocks_for_ui


class ClockContractTests(unittest.TestCase):
    def test_two_clocks_do_not_conflate_and_future_events_are_ignored(self):
        at = datetime.fromisoformat("2026-11-15T12:08:50")
        classes = {"men": [
            {"last_checkpoint": {"passed_at": "2026-11-15T12:08:01"}},
            {"last_checkpoint": {"passed_at": "2026-11-15T12:20:00"}}
        ]}
        shots = [{"in_time": "2026-11-15T12:08:15",
                  "out_time": None},
                 {"in_time": "2026-11-15T12:12:00",
                  "out_time": "2026-11-15T12:13:00"}]
        sources = {"results": {"last_recorded_receipt_local": None},
                   "shooting": {"last_recorded_receipt_local": "2026-11-15T12:08:46"}}
        clocks = clocks_for_ui(at, classes, shots, sources)
        self.assertEqual(clocks["results"]["latest_event"]["value_local"],
                         "2026-11-15T12:08:01")
        self.assertIsNone(clocks["results"]["latest_receipt"]["value_local"])
        self.assertEqual(clocks["shooting"]["latest_event"]["value_local"],
                         "2026-11-15T12:08:15")
        self.assertEqual(clocks["shooting"]["latest_receipt"]["value_local"],
                         "2026-11-15T12:08:46")
        self.assertFalse(clocks["shooting"]["latest_event"]["source_timezone_verified"])
        self.assertTrue(clocks["shooting"]["latest_receipt"]["source_timezone_verified"])

    def test_no_known_event_or_receipt_gives_explicit_null(self):
        at = datetime.fromisoformat("2026-11-15T12:00:00")
        sources = {"results": {"last_recorded_receipt_local": None},
                   "shooting": {"last_recorded_receipt_local": None}}
        clocks = clocks_for_ui(at, {}, [], sources)
        self.assertIsNone(clocks["results"]["latest_event"]["value_local"])
        self.assertIsNone(clocks["shooting"]["latest_receipt"]["value_local"])


if __name__ == "__main__":
    unittest.main()
