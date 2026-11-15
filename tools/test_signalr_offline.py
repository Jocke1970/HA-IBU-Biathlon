"""Small offline smoke test for SignalR MessagePack length frames."""
import json
import tempfile
import unittest
from pathlib import Path

import msgpack
from signalr_offline import decode, frames, process


def wrap(payload):
    data = msgpack.packb(
        [1, {}, None, "ReceiveMessage", [json.dumps(payload)], []],
        use_bin_type=True
    )
    n = len(data)
    prefix = bytearray()
    while n >= 128:
        prefix.append((n & 127) | 128)
        n >>= 7
    prefix.append(n)
    return bytes(prefix) + data


class TestOffline(unittest.TestCase):
    def test_two_shot_snapshots(self):
        items = []
        for n in (1, 2):
            obj = {
                "AthleteID": "278254_2854", "ShootNr": 2, "StartNo": 5,
                "SumShooted": n, "Missed": 1, "Prone": False, "Lane": 15,
                "IsOpen": True,
                "Target1": {"ShootNr": 1, "Hit": False,
                            "ShootTime": "2026-11-15T09:20:14"},
                "Target2": {"ShootNr": 2, "Hit": True,
                            "ShootTime": "2026-11-15T09:20:18" if n == 2 else None}
            }
            raw = wrap({"Source": 4, "Object": obj, "RaceId": "2854"})
            decoded = [decode(x) for x in frames(raw)]
            self.assertEqual(len(decoded), 1)
            items.extend(decoded)
        summary, shots = process(items)
        self.assertEqual(summary[0]["pattern"], "xo")
        self.assertEqual([x["count"] for x in summary[0]["observed_counts"]], [1, 2])
        self.assertEqual(len(shots), 3)


if __name__ == "__main__":
    unittest.main()
