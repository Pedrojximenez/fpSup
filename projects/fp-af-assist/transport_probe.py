#!/usr/bin/env python3
"""Paced read-only USB characterization; no RAM writes or helper execution."""
import argparse
import fcntl
import json
from pathlib import Path
import time

import focus_bridge as b


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--spacing-ms', type=float, default=10.0)
    parser.add_argument('--count', type=int, default=500)
    args = parser.parse_args()
    if not 5 <= args.spacing_ms <= 20 or not 1 <= args.count <= 1000:
        parser.error('spacing must be 5..20 ms; count must be 1..1000')
    args.output.mkdir(parents=True, exist_ok=False)
    result = {'status': 'incomplete', 'read_only': True, 'completed': 0,
              'spacing_ms': args.spacing_ms, 'requested': args.count}
    with (args.output / 'events.jsonl').open('x') as log, open(b.LOCK, 'a+') as lock:
        def event(item):
            log.write(json.dumps(dict(monotonic=time.monotonic(), **item)) + '\n')
            log.flush()
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        io = b.Transport(event=event)
        try:
            result['version'] = io.shell('version')
            if not all(s in result['version'] for s in ('w71c1', '5.02.0.V91', '13aa6210')):
                raise b.BridgeError('unexpected firmware identity')
            for index in range(args.count):
                time.sleep(args.spacing_ms / 1000)
                # Single native shell exchange, deliberately no read retries.
                address = (b.ECHO, 0xC30338C8, 0xC30338D0, 0xC3033A6C,
                           0xC3476418)[index % 5]
                reply = io.shell('mem get 0x%08X,,0x4' % address)
                pairs = b.re.findall(r'A:0x([0-9a-fA-F]+),\s*D:0x([0-9a-fA-F]+)', reply)
                if len(pairs) != 1 or int(pairs[0][0], 16) != address:
                    raise b.BridgeError('incomplete/address-mismatched read')
                value = int(pairs[0][1], 16)
                if address == b.ECHO and value != b.ORIGINAL:
                    raise b.BridgeError('echo is not the original owner')
                if address in (0xC30338C8, 0xC3033A6C) and value != 0:
                    raise b.BridgeError('capture became active')
                if address == 0xC30338D0 and value & 255:
                    raise b.BridgeError('recording became active')
                result['completed'] += 1
            result['status'] = 'paced_reads_completed'
        except Exception as exc:
            result['error'] = repr(exc)
        with (args.output / 'result.json').open('x') as output:
            json.dump(result, output, indent=2)
            output.write('\n')
    print(json.dumps(result, indent=2))
    return 0 if result['status'] == 'paced_reads_completed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
