#!/usr/bin/env python3
"""Read-only, timestamped IBU Sport API snapshot logger for later offline analysis.

Requires requests and ibu_api_probe.py in the same directory.
No API keys or request headers are written to disk. Do not poll more frequently
than permitted by the data provider. Stops after --minutes or Ctrl+C.
"""
import argparse
import datetime as dt
import hashlib
import json
import sys
import time
from pathlib import Path

import requests
from ibu_api_probe import API, SESSION, find_key


def utc_now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='milliseconds')


def fetch(endpoint, key, params):
    started = time.monotonic()
    try:
        response = SESSION.get(API + endpoint, params=params, headers={'apikey': key}, timeout=20)
        content = response.content
        record = {
            'timestamp_utc': utc_now(),
            'endpoint': endpoint,
            'params': params,
            'http_status': response.status_code,
            'elapsed_ms': round((time.monotonic() - started) * 1000),
            'sha256': hashlib.sha256(content).hexdigest(),
            'content_type': response.headers.get('content-type'),
        }
        try:
            record['payload'] = response.json()
        except ValueError:
            record['error'] = 'Non-JSON response (body deliberately not saved)'
        return record
    except requests.RequestException as exc:
        return {
            'timestamp_utc': utc_now(), 'endpoint': endpoint, 'params': params,
            'error': f'{type(exc).__name__}: {exc.__class__.__name__}',
            'elapsed_ms': round((time.monotonic() - started) * 1000),
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--race-id', required=True, help='IBU RaceId from Competitions response')
    parser.add_argument('--interval', type=int, default=60, help='Seconds between cycles (minimum 60; default 60)')
    parser.add_argument('--minutes', type=int, default=60, help='Run duration (default 60 min; max 180)')
    parser.add_argument('--analytics', action='store_true', help='Also log selected AnalyticResults types')
    parser.add_argument('--out', default='ibu_live_logs', help='Output directory')
    args = parser.parse_args()
    if args.interval < 60 or args.minutes < 1 or args.minutes > 180:
        parser.error('interval must be at least 60 seconds; minutes must be 1–180')
    folder = Path(args.out)
    folder.mkdir(parents=True, exist_ok=True)
    filename = folder / ('ibu_' + dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '.jsonl')
    try:
        key = find_key()
    except (requests.RequestException, RuntimeError) as exc:
        print(f'Could not initialize API access: {type(exc).__name__}: {exc}', file=sys.stderr)
        return 1
    requests_list = [('Results', {'RaceId': args.race_id})]
    if args.analytics:
        for type_id in ('S1TM', 'S2TM', 'S3TM', 'S4TM', 'RNG1', 'RNG2', 'RNG3', 'RNG4', 'SKIT'):
            requests_list.append(('AnalyticResults', {'RaceId': args.race_id, 'TypeId': type_id}))
    print(f'Writing: {filename}; {len(requests_list)} requests/cycle every {args.interval}s for up to {args.minutes} min.')
    print('Press Ctrl+C to stop. Check API terms and avoid unnecessary traffic.')
    finish = time.monotonic() + args.minutes * 60
    cycles = 0
    try:
        with filename.open('a', encoding='utf-8', buffering=1) as stream:
            while time.monotonic() < finish:
                cycle_start = time.monotonic()
                cycles += 1
                for endpoint, params in requests_list:
                    record = fetch(endpoint, key, params)
                    record['cycle'] = cycles
                    stream.write(json.dumps(record, ensure_ascii=False, separators=(',', ':')) + '\n')
                    code = record.get('http_status', 'ERR')
                    print(f"{record['timestamp_utc']} #{cycles} {endpoint} {params.get('TypeId', '')} HTTP {code} hash={record.get('sha256', '-')[:10]}")
                    if code in (401, 403, 429):
                        print('Authorization/rate-limit response: stopping rather than retrying.', file=sys.stderr)
                        return 2
                sleep_for = min(cycle_start + args.interval, finish) - time.monotonic()
                if sleep_for > 0:
                    time.sleep(sleep_for)
    except KeyboardInterrupt:
        print('\nStopped by user.')
    print(f'Finished {cycles} cycles; snapshots saved in {filename}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
