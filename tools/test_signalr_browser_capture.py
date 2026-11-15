"""Offline tests for browser recorder filtering and data minimization."""
import json
import unittest

import msgpack
from signalr_browser_capture import safe_messages, compact_record


def pack_signalr(obj):
    data = msgpack.packb([1, {}, None, "ReceiveMessage", [json.dumps([obj])], []],
                         use_bin_type=True)
    length = len(data)
    prefix = bytearray()
    while length >= 128:
        prefix.append((length & 127) | 128)
        length >>= 7
    prefix.append(length)
    return bytes(prefix) + data


class TestBrowserCapture(unittest.TestCase):
    def test_actual_shape_source_four(self):
        payload = {
            "Source": 4, "DbId": 3364, "RaceId": "2854",
            "Object": {
                "RaceID": "2854", "AthleteID": "278254_2854",
                "StartNo": 5, "ShootNr": 2, "SumShooted": 5,
                "Missed": 4, "Prone": False, "Lane": 15,
                "Target1": {"Hit": False, "ShootTime": "2026-11-15T09:20:14"},
                "Target2": {"Hit": True, "ShootTime": "2026-11-15T09:20:18"},
                "secret_test_field": "must not leak"
            }
        }
        found = list(safe_messages(pack_signalr(payload)))
        self.assertEqual(len(found), 1)
        record = compact_record(*found[0])
        self.assertEqual(record["sum_shooted"], 5)
        self.assertEqual(record["shots"][1]["hit"], True)
        self.assertNotIn("secret_test_field", json.dumps(record))

    def test_unknown_source_is_ignored(self):
        payload = {"Source": 9, "RaceId": "2854", "Object": {"RaceID": "2854"}}
        self.assertEqual(list(safe_messages(pack_signalr(payload))), [])


if __name__ == "__main__":
    unittest.main()
