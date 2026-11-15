#!/usr/bin/env python3
"""Validate and export a safe offline combined snapshot for HA /config/www/.

The exported document contains no HA token and never implies live connectivity.
This tool does NOT write into the user's Home Assistant config or use its API.
"""
import argparse
import json
from pathlib import Path
import sys


def validate_snapshot(value):
    if not isinstance(value, dict):
        raise ValueError("combined snapshot must be a JSON object")
    if value.get("backend_type") != "offline_joined_replay":
        raise ValueError("Only offline_joined_replay is permitted for this exporter")
    if not isinstance(value.get("classes"), dict):
        raise ValueError("Missing classes object")
    if not isinstance(value.get("shooting_range"), list):
        raise ValueError("Missing shooting_range list")
    sources = value.get("sources")
    if not isinstance(sources, dict):
        raise ValueError("Missing sources")
    for section in ("results", "shooting"):
        source = sources.get(section)
        if not isinstance(source, dict):
            raise ValueError(f"Missing sources.{section}")
        if source.get("live_verified") is not False:
            raise ValueError(f"sources.{section} must be explicitly non-live")
        if source.get("transport_status") != "offline_replay":
            raise ValueError(f"sources.{section} is not offline_replay")
    if not isinstance(value.get("clocks"), dict):
        raise ValueError("Missing clocks")
    return value


def export_fixture(source, output):
    data = validate_snapshot(json.loads(Path(source).read_text(encoding="utf-8")))
    dest = Path(output)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.resolve() == Path(source).resolve():
        raise ValueError("Destination must differ from input; source will not be overwritten")
    temp = dest.with_suffix(dest.suffix + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n",
                    encoding="utf-8")
    temp.replace(dest)
    return {"file": str(dest), "size_bytes": dest.stat().st_size,
            "class_counts": {k: len(v) for k, v in data["classes"].items()},
            "range_rows": len(data["shooting_range"]), "backend_type": data["backend_type"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Combined offline replay JSON")
    parser.add_argument("--out", required=True, help="Local export path, not a HA URL")
    args = parser.parse_args()
    try:
        print(json.dumps(export_fixture(args.input, args.out), ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, TypeError) as exc:
        print("Replay fixture export failed:", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
