#!/usr/bin/env python3
"""Recover ONLY an interrupted upload that never armed echo or ran RAM code.

Reads its saved before-image; refuses any unexpected current scratch word.
This is not a generic call-timeout recovery or permission to overwrite a hook.
"""
import argparse
import json
from pathlib import Path
import re

import focus_bridge as b


def recovery_plan(events):
    prepared = [item for item in events if item.get('event') == 'lease_prepared']
    if len(prepared) != 1:
        raise b.BridgeError('one exact before-image required')
    baseline = prepared[0]
    words = baseline.get('original_words')
    if not isinstance(words, list) or len(words) != (b.END - b.P) // 4 or any(
            type(v) is not int or not 0 <= v <= 0xffffffff for v in words):
        raise b.BridgeError('invalid bounded before-image')
    allowed = {b.P + i * 4: {v} for i, v in enumerate(words)}
    snapshot_hash = baseline.get('snapshot_sha256')
    code_start = (b.SNAPSHOT if isinstance(snapshot_hash, str) and
                  re.fullmatch(r'[0-9a-f]{64}', snapshot_hash) else b.CODE)
    for item in events:
        request = item.get('request', '')
        if item.get('event') == 'bridge_call_returned' or re.search(r'\bSHL echo(?:\s|$)', request):
            raise b.BridgeError('execution occurred; this narrow recovery does not apply')
        if 'SHL mem set' in request:
            match = re.fullmatch(r'TMO \d+ SHL mem set 0x([0-9A-Fa-f]{8}) 0x([0-9A-Fa-f]{8})', request)
            if not match:
                raise b.BridgeError('unrecognized write in incident evidence')
            address, value = (int(x, 16) for x in match.groups())
            if not code_start <= address < b.END or address & 3:
                raise b.BridgeError('incident is not an unarmed code-only upload')
            allowed[address].add(value)
    return baseline, allowed


def recover(io, events, event=lambda item: None):
    baseline, allowed = recovery_plan(events)
    bridge = b.FocusBridge(io, b'', event)
    # Same cooperative exclusion as every AF tool.
    with open(b.LOCK, 'a+') as lock:
        b.fcntl.flock(lock.fileno(), b.fcntl.LOCK_EX | b.fcntl.LOCK_NB)
        bridge.ownership({b.ORIGINAL})
        if io.shell('version') != baseline['version']:
            raise b.BridgeError('firmware identity changed')
        if not bridge.capture_state()['capture_idle']:
            raise b.BridgeError('capture state is not idle')
        if bridge.settings() != baseline['settings']:
            raise b.BridgeError('settings changed; inspect before recovery')
        current = io.read(b.P, len(baseline['original_words']))
        for index, word in enumerate(current):
            if word not in allowed[b.P + index * 4]:
                raise b.BridgeError('unexpected scratch word; not overwritten')
        changed = [i for i, value in enumerate(current) if value != baseline['original_words'][i]]
        event({'event': 'recovery_preflight', 'changed_words': len(changed),
               'allowed_before_or_uploaded_words_only': True})
        for index in changed:
            bridge.ownership({b.ORIGINAL})
            io.ensure(b.P + index * 4, baseline['original_words'][index])
        bridge.publish()
        if io.read(b.P, len(current)) != baseline['original_words']:
            raise b.BridgeError('recovered scratch readback mismatch')
        bridge.ownership({b.ORIGINAL})
        if bridge.settings() != baseline['settings']:
            raise b.BridgeError('post-recovery settings mismatch')
        return {'status': 'unarmed_upload_recovered', 'restored_words': len(changed),
                'scratch_verified': True, 'echo_verified': True,
                'settings_unchanged': True, 'lens_motion_requested': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--incident-events', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    events = [json.loads(line) for line in args.incident_events.read_text().splitlines()]
    recovery_plan(events)  # Validate evidence before connecting.
    args.output.mkdir(parents=True, exist_ok=False)
    with (args.output / 'events.jsonl').open('x') as log:
        def event(item):
            log.write(json.dumps(item) + '\n')
            log.flush()
        try:
            result = recover(b.Transport(event=event), events, event)
        except BaseException as exc:
            result = {'status': 'recovery_incomplete', 'error': repr(exc)}
        with (args.output / 'result.json').open('x') as output:
            json.dump(result, output, indent=2)
            output.write('\n')
    print(json.dumps(result, indent=2))
    return 0 if result['status'] == 'unarmed_upload_recovered' else 1


if __name__ == '__main__':
    raise SystemExit(main())
