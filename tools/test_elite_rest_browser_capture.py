"""Offline unit tests for allowed CCResult REST capture and metadata hygiene."""
import unittest
from elite_rest_browser_capture import describe_request, capture_record


class RestCaptureTests(unittest.TestCase):
    def test_result_checkpoint(self):
        url = ("https://live.api.nsftiming.no/api/livePG/"
               "GetResultlistWithAthletes/2854/36810_2854?"
               "level=67254_2854&ipos=18&count=1000&access_token=DO_NOT_SAVE")
        meta = describe_request(url, "2854")
        self.assertEqual(meta, {
            "endpoint": "results", "race_id": "2854", "class_id": "36810_2854",
            "level": "67254_2854", "ipos": "18", "count": "1000"
        })
        row = capture_record(meta, {
            "TotalCount": 1,
            "Data": [{"Athlete": {"AthleteID": "278254_2854"},
                      "Time": {"RunTimeMS": 123456, "RankClass": 2}}]
        }, "2026-11-15T11:00:00+00:00")
        self.assertIn("RunTimeMS", str(row["payload"]))
        self.assertNotIn("DO_NOT_SAVE", str(row))

    def test_startlist(self):
        self.assertEqual(describe_request(
            "https://live.api.nsftiming.no/api/livePG/GetStartlist/2854?level=1"),
            {"endpoint": "startlist", "race_id": "2854", "level": "1"})

    def test_ignore_unrelated_or_other_race(self):
        self.assertIsNone(describe_request(
            "https://live.api.nsftiming.no/api/livePG/negotiate?token=SECRET"))
        self.assertIsNone(describe_request(
            "https://evil.example/api/livePG/GetStartlist/2854"))
        self.assertIsNone(describe_request(
            "https://live.api.nsftiming.no/api/livePG/GetStartlist/2854", "1234"))


if __name__ == "__main__":
    unittest.main()
