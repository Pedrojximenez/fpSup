#!/usr/bin/env python3
"""fp AF assist development preview. No camera access without --probe.

The offline UI runs the actual bounded controller on a synthetic scene.
Hardware motion stays disabled until completion/stop/state guards are verified.
"""
import argparse
import datetime as dt
import json
import math
from pathlib import Path
import threading
import time

import assist_controller
import assist_server
import focus_bridge


VERSION = '0.1.0-pre1'
HARDWARE_MOTION_VERIFIED = False


def repo_root():
    for parent in Path(__file__).resolve().parents:
        if (parent / 'fpSup' / 'fp_usb_shell' / 'armasm.py').is_file():
            return parent
    raise RuntimeError('maintained fp USB shell tree not found')


class SyntheticBackend:
    """Explicitly synthetic optics for the runnable controller preview."""
    def __init__(self, cancel=lambda: False):
        self.position = 10000
        self.cancel = cancel
        self.stopped = False

    def observe(self):
        return {'position': self.position,
                'min_position': 6276, 'max_position': 10800,
                'h': 100000 * math.exp(-((self.position - 10035) / 70) ** 2),
                'l': 450000, 'gain': [117, 985, 131, 0],
                'context': ['synthetic', 'single_roi', 'not_recording'], 'valid': True}

    def move_to(self, target):
        if self.stopped:
            raise RuntimeError('synthetic backend already stopped')
        if abs(target - self.position) > 100:
            raise RuntimeError('synthetic step guard')
        for _ in range(5):
            if self.cancel():
                raise RuntimeError('cancelled during synthetic motion')
            time.sleep(0.02)
        self.position = target
        return self.observe()

    def stop(self):
        self.stopped = True
        return {'verified': True, 'synthetic': True, 'position': self.position}


class PreviewService:
    """Runs real controller logic on fake optics; never imports a USB connection."""
    demo = True

    def __init__(self):
        self.lock = threading.Lock()
        self.cancel = threading.Event()
        self.worker = None
        self.state = {'demo': True, 'available': True, 'busy': False,
                      'version': VERSION, 'state': 'idle',
                      'message': '離線預覽：使用實際控制演算法，但鏡頭與讀值都是模擬。',
                      'roi': '模擬單一對焦框', 'position': 10000,
                      'hardware_motion_verified': HARDWARE_MOTION_VERIFIED,
                      'outcome': None}

    def status(self):
        with self.lock:
            return json.loads(json.dumps(self.state))

    def start(self, kind='assist'):
        if kind not in ('assist', 'native'):
            return {'ok': False, 'message': '未知工作。'}
        with self.lock:
            if self.state['busy']:
                return {'ok': False, 'message': '已有工作執行中。'}
            self.cancel.clear()
            self.state.update(busy=True, state='running', outcome=None,
                              message='離線演算法模擬中；沒有操作相機。')
            self.worker = threading.Thread(target=self._run, args=(kind,), daemon=True)
            self.worker.start()
        return {'ok': True, 'message': '已開始離線模擬。'}

    def _event(self, item):
        with self.lock:
            if item.get('kind') == 'observation':
                sample = item['sample']
                self.state.update(position=sample['position'], h=sample['h'])
            self.state['last_event'] = item

    def _run(self, kind):
        try:
            if kind == 'native':
                # The UI button is exercised but no invented original-AF data.
                outcome = {'status': 'not_run', 'synthetic': True,
                           'reason': '離線模式無法執行原廠 AF；未操作相機。'}
            else:
                backend = SyntheticBackend(self.cancel.is_set)
                outcome = assist_controller.run(backend, cancel=self.cancel.is_set, event=self._event)
                outcome['synthetic'] = True
            with self.lock:
                self.state.update(outcome=outcome, busy=False, state=outcome['status'],
                                  message='模擬結束；結果不是實機或光學對焦驗證。')
        except Exception as exc:
            with self.lock:
                self.state.update(busy=False, state='fault', message=str(exc))

    def stop(self):
        self.cancel.set()
        return {'ok': True, 'message': '已要求取消後續動作；這是離線模擬。'}

    def close(self):
        self.stop()
        if self.worker:
            self.worker.join(timeout=2)


def probe(args):
    """Explicitly authorized, non-moving getter validation with exact restore."""
    code = focus_bridge.assemble(args.usb_shell)
    args.output.mkdir(parents=True, exist_ok=False)
    with (args.output / 'events.jsonl').open('x') as log:
        def event(item):
            item = dict(time=dt.datetime.now().astimezone().isoformat(), **item)
            log.write(json.dumps(item, ensure_ascii=False, allow_nan=False) + '\n')
            log.flush()
        outcome = {'version': VERSION, 'mode': 'read_only_RAM_bridge',
                   'motion_requested': False, 'status': 'incomplete'}
        try:
            io = focus_bridge.Transport(args.socket, event)
            outcome['host_status'] = io.request('STATUS').decode('ascii')
            bridge = focus_bridge.FocusBridge(io, code, event)
            with bridge.lease():
                outcome['before'] = bridge.read_state()
                time.sleep(0.05)
                outcome['after'] = bridge.read_state()
                # Separate absolute fields. Do NOT label the old 3A54 value as
                # capture state; C0017AC8 returns root+0x18 before +0x220.
                outcome['ptp_capture_state_raw'] = io.read(0xC3033A6C)[0]
                outcome['ptp_capture_aux_word_raw'] = io.read(0xC30338C8)[0]
                outcome['old_capture_field_raw_3a54'] = io.read(0xC3033A54)[0]
            outcome['status'] = 'read_probe_restored'
        except Exception as exc:
            outcome['error'] = repr(exc)
        finally:
            with (args.output / 'result.json').open('x') as result:
                json.dump(outcome, result, ensure_ascii=False, indent=2, allow_nan=False)
                result.write('\n')
    print(json.dumps(outcome, ensure_ascii=False, indent=2))
    return 0 if outcome['status'] == 'read_probe_restored' else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--demo', action='store_true', help='offline UI and synthetic optics only')
    mode.add_argument('--probe', action='store_true', help='authorized RAM lease, native getters, no motion')
    mode.add_argument('--inspect', action='store_true', help='offline assembly check only')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--socket', default='/tmp/fpshd.sock')
    parser.add_argument('--usb-shell', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    if args.demo:
        service = PreviewService()
        try:
            assist_server.serve(service, port=args.port)
        finally:
            service.close()
        return 0
    args.usb_shell = args.usb_shell or repo_root() / 'fpSup' / 'fp_usb_shell'
    if args.inspect:
        code = focus_bridge.assemble(args.usb_shell)
        snapshot = focus_bridge.assemble(args.usb_shell, source=focus_bridge.SNAPSHOT_SOURCE,
                                          max_bytes=focus_bridge.CODE-focus_bridge.SNAPSHOT)
        print(json.dumps({'version': VERSION, 'code_bytes': len(code),
                          'code_sha256': focus_bridge.hashlib.sha256(code).hexdigest(),
                          'snapshot_bytes': len(snapshot),
                          'snapshot_sha256': focus_bridge.hashlib.sha256(snapshot).hexdigest(),
                          'snapshot_entry': 'C072F740',
                          'hardware_motion_verified': HARDWARE_MOTION_VERIFIED,
                          'host_probe_operations': 'native getters 0..6 only',
                          'lab_only_operations': 'guarded small move 7 / abort 8; explicit authorization required'}, indent=2))
        return 0
    if args.output is None or args.output.exists():
        parser.error('--probe requires --output naming a nonexistent directory')
    return probe(args)


if __name__ == '__main__':
    raise SystemExit(main())
