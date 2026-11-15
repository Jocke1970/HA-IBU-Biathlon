"""Explicit source provenance for the offline biathlon UI contract.

IBU is a *supported identifier*, not a connected data source.
All timestamps are source receipt timestamps, not event timestamps.
"""
from datetime import datetime
import json
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Stockholm")
PROVIDERS = {
    "ccresult": {"name": "CCResult / EliteTiming"},
    "ibu": {"name": "IBU"},
}


def received_local(value):
    if not isinstance(value, str):
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            return None
        return stamp.astimezone(TZ).replace(tzinfo=None)
    except ValueError:
        return None


def latest_receipt(paths, at, *, stream):
    """Latest recorded message received by snapshot time, or None."""
    latest = None
    for path in paths or []:
        with Path(path).open(encoding="utf-8") as data:
            for line in data:
                if not line.strip():
                    continue
                item = json.loads(line)
                if stream == "results":
                    if item.get("endpoint") not in ("results", "startlist"):
                        continue
                elif stream == "shooting":
                    if item.get("kind") != "shooting":
                        continue
                else:
                    raise ValueError("unknown capture stream")
                stamp = received_local(item.get("captured_utc"))
                if stamp is not None and stamp <= at and (latest is None or stamp > latest):
                    latest = stamp
    return latest


def source_entry(provider, *, mode, received_at=None, data_available=False):
    if provider not in PROVIDERS:
        raise ValueError("unsupported provider")
    if mode not in ("observed_replay", "reconstructed_replay"):
        raise ValueError("unsupported offline provenance mode")
    return {
        "provider_id": provider,
        "provider_name": PROVIDERS[provider]["name"],
        "transport_status": "offline_replay",
        "data_mode": mode,
        "data_available": bool(data_available),
        "last_recorded_receipt_local": (
            received_at.isoformat() if received_at is not None else None),
        "live_verified": False,
        "freshness": "not_applicable_offline",
    }


def sources_for_snapshot(at, *, mode, rest_paths, event_paths, has_results, has_shooting):
    results_receipt = latest_receipt(rest_paths, at, stream="results")
    shooting_receipt = latest_receipt(event_paths, at, stream="shooting")
    return {
        "selection_mode": "manual_replay_ccresult",
        "providers_supported": ["ccresult", "ibu"],
        "providers_connected": [],
        "results": source_entry(
            "ccresult",
            mode="observed_replay" if mode == "observed" else "reconstructed_replay",
            received_at=results_receipt,
            data_available=has_results,
        ),
        "shooting": source_entry(
            "ccresult", mode="observed_replay", received_at=shooting_receipt,
            data_available=has_shooting,
        ),
        "ibu": {
            "provider_id": "ibu", "provider_name": PROVIDERS["ibu"]["name"],
            "connection_state": "not_implemented",
            "live_verified": False,
        },
        "mixed_provider_join_verified": False,
    }
