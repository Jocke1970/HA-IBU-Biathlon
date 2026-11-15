"""Tests for the safe raw SignalR Source4 target field probe."""
import unittest
from ibu_signalr_target_probe import ShotFieldProbe, inspect_target_fields


class ProbeTests(unittest.TestCase):
    def test_allowlist_and_null_fields(self):
        obj = {
            "AthleteID": "secret-not-exported",
            "Target1": {"Hit": True, "Shootime": None, "ShootRunTime": 2040,
                        "UnknownPrivate": "do-not-export"},
            "Target2": {"Hit": False, "ShootTime": "2026-11-15T12:08:14"},
            "Target3": {"Shootime": "", "ShootRunTime": None},
            "SumShooted": 3, "InTime": "2026-11-15T12:08:02",
            "UnrelatedField": "ignore-me",
        }
        p = ShotFieldProbe()
        p.add(obj)
        report = p.report()
        self.assertEqual(report["shooting_updates"], 1)
        self.assertEqual(report["target_objects_seen"], 3)
        self.assertEqual(report["target_field_present"]["Shootime"], 2)
        self.assertEqual(report["target_field_populated"]["ShootRunTime"], 1)
        self.assertEqual(report["target_field_populated"]["ShootTime"], 1)
        self.assertNotIn("secret-not-exported", str(report))
        self.assertNotIn("UnknownPrivate", str(report))
        self.assertNotIn("2026-11-15T12:08:14", str(report))

    def test_missing_target_objects(self):
        report = inspect_target_fields({"Target1": None, "Target2": "invalid"})
        self.assertEqual(report["target_objects"], 0)
        p = ShotFieldProbe()
        p.add(None)
        self.assertEqual(p.report()["shooting_updates"], 0)


if __name__ == "__main__":
    unittest.main()
