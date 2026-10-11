#!/usr/bin/env python3
"""Explicit non-moving, RAM-leased validation of settled H sampling."""
import argparse
import datetime as dt
import json
from pathlib import Path

import focus_bridge as b
from fp_af_assist import repo_root
from settled_sampler import SettledSampler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    code = b.assemble(repo_root() / 'fpSup' / 'fp_usb_shell')
    snapshot = b.assemble(repo_root() / 'fpSup' / 'fp_usb_shell', source=b.SNAPSHOT_SOURCE,
                          max_bytes=b.CODE-b.SNAPSHOT)
    args.output.mkdir(parents=True, exist_ok=False)
    result = {'status': 'incomplete', 'lens_motion_requested': False}
    with (args.output / 'events.jsonl').open('x') as log:
        def event(item):
            log.write(json.dumps(dict(time=dt.datetime.now().astimezone().isoformat(), **item)) + '\n')
            log.flush()
        bridge = b.FocusBridge(b.Transport(event=event), code, event, snapshot_code=snapshot)
        try:
            with bridge.lease():
                sampler = SettledSampler(bridge.io, bridge, event=event)
                result['observation'] = sampler.observe()
            result['status'] = 'settled_observation_restored'
        except Exception as exc:
            result['error'] = repr(exc)
            if getattr(exc, 'evidence', None) is not None:
                result['evidence'] = exc.evidence
        finally:
            result['cleanup_complete'] = bridge.cleanup_complete
            result['quarantined'] = bridge.quarantined
            with (args.output / 'result.json').open('x') as output:
                json.dump(result, output, indent=2)
                output.write('\n')
    print(json.dumps(result, indent=2))
    return 0 if result['status'] == 'settled_observation_restored' else 1


if __name__ == '__main__':
    raise SystemExit(main())
