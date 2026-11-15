"""Source attribution checks: no false live indicator or fabricated IBU feed."""
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from ibu_source_provenance import latest_receipt, source_entry, sources_for_snapshot


class ProvenanceTests(unittest.TestCase):
    def test_offline_source_never_claims_live_ibu(self):
        data = sources_for_snapshot(datetime.fromisoformat("2026-11-15T12:08:50"),
                                    mode="reconstructed", rest_paths=[], event_paths=[],
                                    has_results=True, has_shooting=False)
        self.assertEqual(data["results"]["provider_id"], "ccresult")
        self.assertEqual(data["results"]["data_mode"], "reconstructed_replay")
        self.assertFalse(data["results"]["live_verified"])
        self.assertEqual(data["ibu"]["connection_state"], "not_implemented")
        self.assertEqual(data["providers_connected"], [])
        self.assertFalse(data["shooting"]["data_available"])

    def test_capture_receipt_cutoff_is_respected_separately(self):
        with tempfile.TemporaryDirectory() as tmp:
            rest = Path(tmp) / "rest.jsonl"
            shooting = Path(tmp) / "events.jsonl"
            rest.write_text(json.dumps({
                "endpoint": "results", "captured_utc": "2026-11-15T12:30:00+00:00"
            }) + "\n", encoding="utf-8")
            shooting.write_text(json.dumps({
                "kind": "shooting", "captured_utc": "2026-11-15T11:08:20+00:00"
            }) + "\n", encoding="utf-8")
            at = datetime.fromisoformat("2026-11-15T12:08:50")
            data = sources_for_snapshot(at, mode="observed", rest_paths=[rest],
                                        event_paths=[shooting],
                                        has_results=False, has_shooting=True)
            self.assertIsNone(data["results"]["last_recorded_receipt_local"])
            self.assertEqual(data["shooting"]["last_recorded_receipt_local"],
                             "2026-11-15T12:08:20")
            self.assertFalse(data["results"]["data_available"])
            self.assertTrue(data["shooting"]["data_available"])

    def test_unknown_provider_is_rejected(self):
        with self.assertRaises(ValueError):
            source_entry("unverified_provider", mode="observed_replay")


if __name__ == "__main__":
    unittest.main()
