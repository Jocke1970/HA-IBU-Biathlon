#!/usr/bin/env python3
"""Read-only diagnostic for IBU Datacenter's unofficial public-facing API.

Usage:
  python -m pip install requests
  python ibu_api_probe.py --season 2627
  python ibu_api_probe.py --season 2627 --race-id BT... --analytics

No scraping of non-public resources; accesses only the same publicly served
frontend and API endpoints. Check service terms before polling regularly.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests

BASE = 'https://biathlonresults.com/'
API = urljoin(BASE, 'modules/sportapi/api/')
SESSION = requests.Session()
SESSION.headers.update({'User-Agent': 'IBU-HA-Integration-Research/0.1 (personal read-only diagnostics)', 'Referer': BASE})


def request(url, **kwargs):
    r = SESSION.get(url, timeout=20, **kwargs)
    print(f'HTTP {r.status_code}  {r.url}  ({len(r.content)} bytes; {r.headers.get("content-type", "unknown type")})')
    r.raise_for_status()
    return r


def find_key():
    manual = os.getenv('BIATHLONRESULTS_API_KEY')
    if manual:
        print('Using BIATHLONRESULTS_API_KEY environment variable (not printing key).')
        return manual
    html = request(BASE).text
    scripts = re.findall(r'<script[^>]*\ssrc=["\']?([^"\'\s>]+\.js)', html, re.I)
    scripts.sort(key=lambda x: 'app' not in x.rsplit('/', 1)[-1].lower())
    for src in scripts[:30]:
        try:
            js = request(urljoin(BASE, src)).text
            match = re.search(r'ApiKey\s*=\s*["\']([0-9a-fA-F-]{36})["\']', js)
            if match:
                print('Found frontend-provided API key (not printing key).')
                return match.group(1)
        except requests.RequestException as exc:
            print(f'  Skipping script: {type(exc).__name__}')
    raise RuntimeError('Could not find a frontend API key; stop rather than guessing.')


def get(endpoint, key, **params):
    r = request(urljoin(API, endpoint), params=params or None, headers={'apikey': key})
    try:
        return r.json()
    except ValueError as exc:
        raise RuntimeError(f'{endpoint}: response is not JSON') from exc


def rows(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for name in ('Results', 'Events', 'Competitions', 'Seasons'):
            if isinstance(payload.get(name), list):
                return payload[name]
    return []


def describe(label, payload, folder):
    dest = folder / f'{label}.json'
    dest.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')
    subset = rows(payload)
    print(f'  {label}: {len(subset)} records; saved {dest}')
    if subset and isinstance(subset[0], dict):
        print(f'  First record fields: {", ".join(subset[0].keys())}')
        print('  First record:', json.dumps(subset[0], ensure_ascii=False)[:900])
    elif isinstance(payload, dict):
        print('  Top-level fields:', ', '.join(payload.keys()))
    return subset


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--season', default='2627')
    p.add_argument('--race-id', default=None, help='Known IBU RaceId to inspect')
    p.add_argument('--analytics', action='store_true', help='Fetch S1TM/RNG1/SKIT (only with --race-id)')
    p.add_argument('--out', default='ibu_probe_output')
    a = p.parse_args()
    if a.analytics and not a.race_id:
        p.error('--analytics requires --race-id')
    folder = Path(a.out)
    folder.mkdir(parents=True, exist_ok=True)
    try:
        key = find_key()
        describe('seasons', get('Seasons', key), folder)
        events = describe('events', get('Events', key, SeasonId=a.season, Level='0'), folder)
        if events:
            print('\nEvents in season (first 15):')
            for e in events[:15]:
                print('  ', e.get('EventId'), e.get('ShortDescription'), e.get('StartDate'))
            first_id = next((e.get('EventId') for e in events if isinstance(e, dict) and e.get('EventId')), None)
            if first_id:
                describe('competitions_first_event', get('Competitions', key, EventId=first_id), folder)
        if a.race_id:
            describe('race_results', get('Results', key, RaceId=a.race_id), folder)
            if a.analytics:
                for type_id in ('S1TM', 'RNG1', 'SKIT'):
                    describe('analytics_' + type_id, get('AnalyticResults', key, RaceId=a.race_id, TypeId=type_id), folder)
        print('\nDone. Inspect output JSON for actual field structure; no live-refresh rate inferred.')
    except (requests.RequestException, RuntimeError) as exc:
        print(f'\nStopped: {type(exc).__name__}: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
