"""Regression tests for offline event-time live-state replay."""
import unittest
from datetime import datetime
from ibu_live_state import replay


class LiveStateTests(unittest.TestCase):
    def setUp(self):
        self.athletes = [
            {"race_id": "1", "athlete_id": "a", "class_id": "men",
             "name": "A", "bib": 1, "start_time": "2026-11-15T12:00:00", "nation": "SWE",
             "checkpoints": [{"ipos": "1", "intermediate_id": "cp1",
                              "runtime_ms": 180000, "rank_at_checkpoint": 2,
                              "pass_time": "2026-11-15T12:03:00"}],
             "shootings": [{"shoot_nr": 1, "lane": 7, "in_time": "2026-11-15T11:08:00",
                            "out_time": "2026-11-15T11:08:30",
                            "range_seconds": 30, "shoot_string": "ooooo",
                            "missed": 0, "shots_count": 5}]},
            {"race_id": "1", "athlete_id": "b", "class_id": "women",
             "name": "B", "bib": 2, "start_time": "2026-11-15T10:00:00",
             "nation": "SWE", "checkpoints": [], "shootings": []}
        ]

    def state(self, time):
        return replay(self.athletes, datetime.fromisoformat("2026-11-15T" + time))

    def test_range_15_second_lifecycle(self):
        self.assertEqual(self.state("12:07:59")["shooting_range"], [])
        active = self.state("12:08:20")["shooting_range"]
        self.assertEqual(active[0]["state"], "active")
        self.assertIsNone(active[0]["final_shoot_string"])
        self.assertIsNone(active[0]["out_time"])
        self.assertEqual(active[0]["elapsed_on_range_seconds"], 20)
        finished = self.state("12:08:30")["shooting_range"]
        self.assertEqual(finished[0]["state"], "recently_finished")
        self.assertEqual(finished[0]["final_shoot_string"], "ooooo")
        self.assertEqual(len(self.state("12:08:44")["shooting_range"]), 1)
        self.assertEqual(self.state("12:08:45")["shooting_range"], [])

    def test_no_cross_class_rank_or_fake_finish(self):
        result = self.state("12:04:00")
        self.assertEqual(result["classes"]["men"][0]["checkpoint_rank"], 2)
        self.assertEqual(result["classes"]["women"][0]["status"], "on_course")
        self.assertEqual(result["classes"]["men"][0]["status"], "on_course")
        self.assertEqual(result["ranking_semantics"],
                         "checkpoint_local_only_not_overall_live_position")

    def test_finish_station_requires_explicit_mapping(self):
        result = replay(self.athletes, datetime.fromisoformat("2026-11-15T12:04:00"),
                        finish_stations={"cp1"})
        self.assertEqual(result["classes"]["men"][0]["status"], "finished")

    def test_offset_is_configurable(self):
        result = replay(self.athletes, datetime.fromisoformat("2026-11-15T11:08:20"),
                        shooting_offset_hours=0)
        self.assertEqual(len(result["shooting_range"]), 1)

    def test_incomplete_series_stays_unconfirmed(self):
        self.athletes[0]["shootings"][0]["out_time"] = None
        result = self.state("12:08:30")
        self.assertEqual(result["shooting_range"][0]["state"], "active_unconfirmed")
        self.assertIsNone(result["shooting_range"][0]["final_shoot_string"])


if __name__ == "__main__":
    unittest.main()
