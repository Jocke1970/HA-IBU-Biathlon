"""Tests of receipt-time capture audit and conservative finish evidence."""
import json
import tempfile
import unittest
from pathlib import Path
from ibu_rest_coverage_audit import audit_rest


class RestAuditTests(unittest.TestCase):
    def test_status_and_finish_field_never_verify_finish(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rest.jsonl"
            rows = [
                {"AthleteID": "a", "ClassID": "men", "Status": 5, "Time": {
                    "IntermediateID": "finish_candidate", "RunTimeMS": 1200000,
                    "PassTime": "2026-11-15T12:20:00", "FFStatus": False}},
                {"AthleteID": "b", "ClassID": "men", "Status": 5, "Time": {
                    "IntermediateID": "finish_candidate", "RunTimeMS": 1300000,
                    "PassTime": "2026-11-15T12:22:00", "FFStatus": False}},
            ]
            records = [
                {"endpoint": "results", "race_id": "2854", "class_id": "men",
                 "ipos": "21", "captured_utc": "2026-11-15T11:15:00+00:00",
                 "payload": {"Data": rows}},
            ]
            path.write_text("".join(json.dumps(x) + "\n" for x in records), encoding="utf-8")
            result = audit_rest([path])
            entry = result["classes"]["2854:men"]["stations"]["finish_candidate"]
            self.assertEqual(entry["status_codes_observed"]["5"], 2)
            self.assertEqual(entry["FFStatus_false"], 2)
            self.assertEqual(entry["pass_after_capture"], 2)
            self.assertFalse(entry["verified_finish"])

    def test_separate_classes_and_skip_bad_capture_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rest.jsonl"
            lines = [
                {"endpoint": "startlist", "race_id": "1",
                 "captured_utc": "2026-11-15T11:01:00+00:00", "payload": {"Data": [
                     {"ClassID": "men"}, {"ClassID": "women"}]}},
                {"endpoint": "results", "race_id": "1", "class_id": "women",
                 "ipos": "18", "captured_utc": "2026-11-15T11:02:00+00:00",
                 "payload": {"Data": [{"AthleteID": "b", "Status": 5, "Time": {
                     "IntermediateID": "s", "RunTimeMS": 200000,
                     "PassTime": "2026-11-15T12:00:00"}}]}},
                {"endpoint": "results", "race_id": "1", "class_id": "women",
                 "ipos": "18", "captured_utc": "bad",
                 "payload": {"Data": []}},
            ]
            path.write_text("".join(json.dumps(x) + "\n" for x in lines), encoding="utf-8")
            result = audit_rest([path])
            self.assertEqual(result["invalid_or_missing_capture_records"], 1)
            self.assertEqual(result["classes"]["1:men"]["startlist_snapshots"], 1)
            self.assertEqual(result["classes"]["1:women"]["station_count"], 1)


if __name__ == "__main__":
    unittest.main()
