#!/usr/bin/env python3
"""Bounded read-only short-bracket traffic; no RAM lease, echo, or motion."""
import argparse
import fcntl
import json
from pathlib import Path
import time

import focus_bridge as b


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--count', type=int, default=100)
    args = parser.parse_args()
    if not 1 <= args.count <= 100:
        parser.error('count must be 1..100')
    args.output.mkdir(parents=True, exist_ok=False)
    result = {'status': 'incomplete', 'read_only': True, 'lens_motion_requested': False,
              'completed_brackets': 0, 'requested_brackets': args.count}
    with (args.output / 'events.jsonl').open('x') as log, open(b.LOCK, 'a+') as lock:
        def event(item):
            log.write(json.dumps(dict(monotonic=time.monotonic(), **item)) + '\n')
            log.flush()
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        io = b.Transport(event=event)
        bridge = b.FocusBridge(io, b'')
        try:
            result['version'] = io.shell('version')
            if not all(s in result['version'] for s in ('w71c1', '5.02.0.V91', '13aa6210')):
                raise b.BridgeError('unexpected firmware')
            bridge.native_identity()
            for index in range(args.count):
                bridge.ownership({b.ORIGINAL})
                if not bridge.capture_state()['capture_idle']:
                    raise b.BridgeError('capture became active')
                sample = io.read_h_bracket()
                event({'event': 'diagnostic_bracket', 'index': index, 'raw': sample,
                       'scientifically_validated': False})
                result['completed_brackets'] += 1
            result['status'] = 'readonly_brackets_completed'
        except Exception as exc:
            result['error'] = repr(exc)
        with (args.output / 'result.json').open('x') as output:
            json.dump(result, output, indent=2)
            output.write('\n')
    print(json.dumps(result, indent=2))
    return 0 if result['status'] == 'readonly_brackets_completed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
