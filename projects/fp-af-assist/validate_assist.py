#!/usr/bin/env python3
"""One explicitly authorized bounded contrast job; never original AF."""
import argparse
import json
from pathlib import Path

from camera_service import CameraService
from fp_af_assist import repo_root


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--authorized-small-step-validation', action='store_true', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cancel-after-first-observation', action='store_true',
                        help='verify cancellation before any movement')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    service = None
    def event(item):
        if item.get('kind') in ('observation', 'move_requested', 'finished'):
            print(json.dumps(item, ensure_ascii=False), flush=True)
        if args.cancel_after_first_observation and item.get('kind') == 'observation':
            service.stop()
    service = CameraService(repo_root() / 'fpSup' / 'fp_usb_shell', args.output, event=event)
    try:
        started = service.start('assist')
        if not started.get('ok'):
            raise RuntimeError(started['message'])
        while service.worker.is_alive():
            service.worker.join(timeout=0.5)
    except KeyboardInterrupt:
        service.stop()
    finally:
        service.close()
    state = service.status()
    outcome = state.get('outcome') or {}
    print(json.dumps({key: outcome.get(key) for key in
                      ('status', 'reason', 'confirmed', 'initial_position', 'selected_position',
                       'final_position', 'relative_h_change', 'cleanup_complete', 'stop', 'error')},
                     ensure_ascii=False, indent=2))
    print(state.get('capture_path'))
    return 0 if outcome.get('cleanup_complete') and outcome.get('status') in (
        'completed', 'unconfirmed', 'cancelled') else 1


if __name__ == '__main__':
    raise SystemExit(main())
