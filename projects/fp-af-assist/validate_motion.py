#!/usr/bin/env python3
"""Explicitly authorized LAB validation only. Not a public AF control mode.

One 20-pulse step away from the nearer native limit, completion observation,
then at most one 20-pulse return with an immediate stop request. No repeated
movement after errors, no automatic rescue, and no card/firmware writes.
"""
import argparse
import datetime as dt
import json
from pathlib import Path

import focus_bridge as b
from fp_af_assist import repo_root


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--authorized-small-step-validation', action='store_true', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--socket', default='/tmp/fpshd.sock')
    args = parser.parse_args()
    code = b.assemble(repo_root() / 'fpSup' / 'fp_usb_shell')
    args.output.mkdir(parents=True, exist_ok=False)
    result = {'status': 'incomplete', 'maximum_step': 20, 'maximum_requests': 2,
              'stop_is_not_unconditional_emergency_stop': True}
    with (args.output / 'events.jsonl').open('x') as log:
        def event(item):
            log.write(json.dumps(dict(time=dt.datetime.now().astimezone().isoformat(), **item)) + '\n')
            log.flush()
        io = b.Transport(args.socket, event)
        bridge = b.FocusBridge(io, code, event)
        bridge.motion_enabled = True
        try:
            with bridge.lease():
                initial = bridge.read_state()
                result['initial'] = initial
                p = initial['position']
                direction = -1 if p - initial['min_position'] > initial['max_position'] - p else 1
                target = p + direction * 20
                result['first_submit'] = bridge.submit_validation_move(target)
                result['first_completion'] = bridge.confirm_done(expected=target)
                result['return_submit'] = bridge.submit_validation_move(p)
                # Request stop even if this small drive may have already finished.
                # Only captured flags can prove whether it was in-flight.
                result['flags_before_stop'] = bridge.flags(5)
                result['stop_request'] = bridge.request_validation_stop()
                result['stop_completion'] = bridge.confirm_done()
                final = bridge.read_state()
                result['final'] = final
                if not final['capture_idle'] or final['af_route'] != 14:
                    raise b.BridgeError('camera context changed during validation')
                result['native_busy_observed_before_stop'] = result['flags_before_stop'] != 3
                result['optical_motion_interruption_verified'] = False
            result['status'] = 'small_step_completed_and_restored'
        except BaseException as exc:
            result['error'] = repr(exc)
            # No repeated motion or automatic rescue after uncertain execution.
            result['owned_motion_unconfirmed'] = bridge.movement_owned
            result['quarantined'] = bridge.quarantined
        finally:
            result['cleanup_complete'] = bridge.cleanup_complete
            result['quarantined'] = bridge.quarantined
            with (args.output / 'result.json').open('x') as output:
                json.dump(result, output, indent=2)
                output.write('\n')
    print(json.dumps(result, indent=2))
    return 0 if result['status'] == 'small_step_completed_and_restored' else 1


if __name__ == '__main__':
    raise SystemExit(main())
