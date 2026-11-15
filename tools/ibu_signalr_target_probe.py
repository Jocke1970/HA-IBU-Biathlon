"""Privacy-minimized diagnostics for public Source=4 shooting targets.

Only explicit allowlisted target fields. No WebSocket URL, credentials,
unknown object fields, raw message blobs, or personal identifiers.
"""
from collections import Counter

TARGET_FIELDS = ("Hit", "Shootime", "ShootTime", "ShootRunTime", "ShootNr")
SHOOT_FIELDS = ("InTime", "OutTime", "SumShooted", "Missed", "ShootNr")


def inspect_target_fields(obj):
    """Return allowlisted schema/presence, not the full provider object."""
    if not isinstance(obj, dict):
        return None
    target_keys = Counter()
    populated = Counter()
    types = {}
    for index in range(1, 9):
        target = obj.get(f"Target{index}")
        if not isinstance(target, dict):
            continue
        for key in TARGET_FIELDS:
            if key not in target:
                continue
            target_keys[key] += 1
            value = target[key]
            if value is not None and value != "":
                populated[key] += 1
                types[key] = type(value).__name__
    return {
        "target_objects": sum(isinstance(obj.get(f"Target{i}"), dict) for i in range(1, 9)),
        "target_field_present": dict(target_keys),
        "target_field_populated": dict(populated),
        "target_value_types": types,
        "shoot_field_present": [key for key in SHOOT_FIELDS if key in obj],
        "shoot_field_populated": [key for key in SHOOT_FIELDS
                                  if key in obj and obj[key] not in (None, "")],
    }


class ShotFieldProbe:
    """Aggregate source presence and values with no athlete-level output."""
    def __init__(self):
        self.updates = 0
        self.target_objects = 0
        self.present = Counter()
        self.populated = Counter()
        self.types = {}
        self.shoot_present = Counter()
        self.shoot_populated = Counter()

    def add(self, source4_object):
        report = inspect_target_fields(source4_object)
        if report is None:
            return
        self.updates += 1
        self.target_objects += report["target_objects"]
        self.present.update(report["target_field_present"])
        self.populated.update(report["target_field_populated"])
        self.types.update(report["target_value_types"])
        self.shoot_present.update(report["shoot_field_present"])
        self.shoot_populated.update(report["shoot_field_populated"])

    def report(self):
        return {
            "format": "source4_target_field_presence_v1",
            "shooting_updates": self.updates,
            "target_objects_seen": self.target_objects,
            "target_field_present": dict(self.present),
            "target_field_populated": dict(self.populated),
            "target_value_types": dict(self.types),
            "shoot_field_present": dict(self.shoot_present),
            "shoot_field_populated": dict(self.shoot_populated),
            "note": "Only allowlisted key presence, value types and counts. "
                    "A received message is not a shot timestamp.",
        }
