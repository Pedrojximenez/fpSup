"""Guarded preview table hypothesis for the existing 24fps 3K mode.

Changes source-construction inputs; never edits a running object's buffer size.
The standby source may stay cached until the next native mode transition.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def plan():
    profiles = json.loads((ROOT/'analysis/firmware/raw-profiles.json').read_text())
    entries = []
    for profile, changes in [(5, {0x28:1334}), (429, {0x10:1344, 0x28:1334, 0xe0:1344})]:
        row = next(r for r in profiles['rows'] if profile in r['profile_ids'])
        for offset, value in changes.items():
            column = next(c for c in profiles['columns'] if c['offset']==offset)
            entries.append(dict(address=column['table']+row['index']*4,
                                expected=row['words'][offset//4], replacement=value,
                                profile=profile, parameter_offset=offset, category='preview'))
    return entries
