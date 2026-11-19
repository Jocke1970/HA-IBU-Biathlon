"""No-network regression tests for the IBU archival collector."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from ibu_archive_capture import ANALYSIS, archive, fields, fetch, main


class Response:
    status_code = 200
    content = b'{"Results":[{"IBUId":"athlete","Rank":"1"}]}'
    headers = {"content-type":"application/json"}
    def json(self):
        return {"Results":[{"IBUId":"athlete","Rank":"1"}]}


class FakeSession:
    def __init__(self):
        self.calls = []
    def get(self, url, params, timeout):
        self.calls.append((url, params, timeout))
        return Response()


class ArchiveTests(unittest.TestCase):
    def test_nested_schema_counts_without_values(self):
        paths = fields({"Results":[{"IBUId":"do-not-print","Shootings":"0011"}]})
        self.assertIn("Results[].IBUId", paths)
        self.assertNotIn("do-not-print", str(paths))

    def test_read_only_response_archiving(self):
        session = FakeSession()
        payload, meta = fetch(session, "Results", {"RaceId":"race"}, pause=0)
        self.assertEqual(meta["status"], 200)
        self.assertIn("sha256", meta)
        self.assertNotIn("apikey", str(meta).lower())
        self.assertEqual(len(session.calls), 1)
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            archive(folder, "results", payload, meta)
            self.assertTrue((folder/"results.json").exists())
            self.assertEqual(json.loads((folder/"results.json").read_text()), payload)

    def test_finite_race_list(self):
        self.assertEqual(len(ANALYSIS), 9)
        self.assertEqual(ANALYSIS[0], "S1TM")
        self.assertEqual(ANALYSIS[-1], "SKIT")

    def test_invalid_race_id_rejected_before_network(self):
        with self.assertRaises(SystemExit):
            main(["--mode","race","--race-id","../secret"])

    def test_race_capture_has_ten_requests_once(self):
        fake = FakeSession()
        with (tempfile.TemporaryDirectory() as root,
              patch("ibu_archive_capture.find_key",return_value="not-to-print"),
              patch("ibu_archive_capture.SESSION",fake),
              patch("ibu_archive_capture.time.sleep",return_value=None)):
            fake.headers = {}
            code = main(["--mode","race","--race-id","BTRACETEST",
                         "--out",root,"--pause","0.5"])
            self.assertEqual(code, 0)
            self.assertEqual(len(fake.calls), 10)
            folder=Path(root)/"race_BTRACETEST"
            manifest=json.loads((folder/"manifest.json").read_text())
            self.assertEqual(len(manifest["requests"]),10)
            self.assertNotIn("not-to-print", str(manifest))
            self.assertTrue((folder/"analysis_S1TM.json").exists())
            # Intentional no-overwrite contract.
            with self.assertRaises(SystemExit):
                main(["--mode","race","--race-id","BTRACETEST","--out",root])


if __name__=="__main__":
    unittest.main()
