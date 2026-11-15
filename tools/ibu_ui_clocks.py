"""UI-facing clock semantics for offline biathlon snapshots.

Event time: when a race action occurred (provider-supplied).
Receipt time: when the recorder received the information.
Local naive wall clocks are explicitly labeled and NEVER silently
converted to UTC. A future event is never emitted from a replay frame.
"""
from datetime import datetime


def latest_result_event(classes, at):
    values = []
    for athletes in classes.values():
        for athlete in athletes:
            point = athlete.get("last_checkpoint")
            if not point:
                continue
            raw = point.get("passed_at")
            if raw:
                try:
                    dt = datetime.fromisoformat(raw)
                except ValueError:
                    continue
                if dt.tzinfo is None and dt <= at:
                    values.append(dt)
    return max(values) if values else None


def latest_range_event(shooting_rows, at):
    values = []
    for row in shooting_rows:
        # 'in_time' is an actual event and should never be inferred from
        # the recorder's capture timestamp. 'out_time' is visible only
        # after the shooting update carrying it has been received.
        for name in ("in_time", "out_time"):
            raw = row.get(name)
            if not raw:
                continue
            try:
                dt = datetime.fromisoformat(raw)
            except ValueError:
                continue
            if dt.tzinfo is None and dt <= at:
                values.append(dt)
    return max(values) if values else None


def timestamp_info(event, *, kind, confidence):
    return {
        "value_local": event.isoformat() if event else None,
        "kind": kind,
        "timezone": "Europe/Stockholm",
        "source_timezone_verified": confidence,
    }


def clocks_for_ui(at, classes, range_rows, sources):
    result_event = latest_result_event(classes, at)
    range_event = latest_range_event(range_rows, at)
    return {
        "snapshot_local": timestamp_info(at, kind="replay_clock",
                                          confidence=True),
        "results": {
            "latest_event": timestamp_info(
                result_event, kind="checkpoint_pass", confidence=False),
            "latest_receipt": timestamp_info(
                datetime.fromisoformat(sources["results"]["last_recorded_receipt_local"])
                if sources["results"]["last_recorded_receipt_local"] else None,
                kind="rest_response_received", confidence=True),
        },
        "shooting": {
            "latest_event": timestamp_info(
                range_event, kind="range_in_or_out", confidence=False),
            "latest_receipt": timestamp_info(
                datetime.fromisoformat(sources["shooting"]["last_recorded_receipt_local"])
                if sources["shooting"]["last_recorded_receipt_local"] else None,
                kind="signalr_message_received", confidence=True),
        },
        "warning": "Source-local InTime/OutTime conversion is provisional; receipt "
                   "times come from offset-aware captured_utc. Event and receipt "
                   "timestamps are not interchangeable."
    }
