"""Serialized, explicitly enabled camera jobs for the loopback UI.

All USB work runs in one job thread under the shared AF lease. HTTP stop only
sets cancellation; it never races a second command against the USB worker.
"""
import contextlib
import datetime as dt
import json
from pathlib import Path
import threading
import time

import assist_controller
from camera_backend import CameraBackend
import focus_bridge as b


class CameraService:
    demo = False

    def __init__(self, shell_dir, captures, socket_path='/tmp/fpshd.sock', event=None):
        self.code = b.assemble(shell_dir)
        self.snapshot_code = b.assemble(shell_dir, source=b.SNAPSHOT_SOURCE, max_bytes=b.CODE-b.SNAPSHOT)
        self.captures = Path(captures)
        self.socket_path = socket_path
        self.external_event = event or (lambda item: None)
        self.lock = threading.Lock()
        self.cancel = threading.Event()
        self.worker = None
        self.fault_latched = False
        self.state = {'demo': False, 'available': True, 'busy': False,
                      'state': 'idle', 'message': '實驗版：開始前會重新檢查相機；僅支援未錄影、AF-S、單一框。',
                      'roi': '沿用相機目前對焦框，不修改設定', 'outcome': None}

    def status(self):
        with self.lock:
            return json.loads(json.dumps(self.state))

    def start(self, kind='assist'):
        if kind not in ('assist', 'native'):
            return {'ok': False, 'message': '未知工作。'}
        with self.lock:
            if self.state['busy'] or self.fault_latched:
                return {'ok': False, 'message': '正在執行，或先前失敗已鎖定；請先檢查紀錄。'}
            self.cancel.clear()
            self.state.pop('notification_error', None)
            self.state.update(busy=True, available=False, state='checking', outcome=None,
                              message='正在核對相機狀態；請勿操作模式、快門或錄影。')
            try:
                self.worker = threading.Thread(target=self._run, args=(kind,), daemon=False)
                self.worker.start()
            except Exception as exc:
                # An unstarted Thread cannot be joined. Commit a terminal fault
                # instead of leaving the UI permanently busy or retrying work.
                self.worker = None
                self.cancel.set()
                self.fault_latched = True
                self.state.update(busy=False, available=False, state='fault',
                                  capture_path=None,
                                  outcome={'status': 'fault', 'method': kind,
                                           'phase': 'job_start', 'error': repr(exc)},
                                  message='無法建立工作執行緒，已鎖定；未自動重試。')
                return {'ok': False, 'message': self.state['message']}
        return {'ok': True, 'message': '已排入一次工作；不會自動重試或改用原廠 AF。'}

    def stop(self):
        self.cancel.set()
        return {'ok': True, 'message': '已要求取消後續動作；原生呼叫返回後檢查停止，不是即時硬體緊急停止。'}

    def close(self):
        self.stop()
        if self.worker:
            self.worker.join()

    def _progress(self, item):
        with self.lock:
            if item.get('kind') == 'observation':
                sample = item['sample']
                self.state.update(position=sample['position'], h=sample['h'])
            self.state['last_event'] = item
            if item.get('kind') == 'move_requested':
                self.state.update(state='moving', message='小範圍對比探測中；正在核對完成旗標。')
        self.external_event(item)

    def _original_af(self, bridge):
        state = bridge.read_state()
        if (not state['capture_idle'] or not state['native_done'] or state['af_route'] != 14 or
                bridge.baseline.get('menu SetFocusMode') != '0' or
                bridge.baseline.get('menu SetFocusArea') != '0'):
            raise b.BridgeError('original AF requires the supported idle single-area AF-S state')
        if self.cancel.is_set():
            return {'status': 'cancelled', 'half_press_sent': False}
        # Only this explicit user-selected operation uses original AF. It can
        # search farther than the assist's +/-100 pulse window. Never S2/MOV.
        try:
            reply = bridge.io.request('TMO 1000 SHL key S1ON')
            if reply != b'OK \n':
                raise b.BridgeError('uncertain S1ON; will release but never repeat start')
            self.cancel.wait(1.5)
        finally:
            # Release dispatch must not depend on prior logging success.
            reply = bridge.io.request('TMO 1000 SHL key S1OFF')
            if reply != b'OK \n':
                raise b.BridgeError('S1OFF not acknowledged; manual inspection required')
        completion = bridge.confirm_done(timeout=2.0)
        return {'status': 'cancelled' if self.cancel.is_set() else 'completed',
                'method': 'original_AF_half_press', 'half_press_released': True,
                'completion': completion, 'optical_focus_verified': False}

    def _run(self, kind):
        stamp = dt.datetime.now().astimezone().strftime('%Y-%m-%d-%H%M%S-%f')
        outdir = self.captures / (stamp + '-' + kind)
        outcome = {'status': 'fault', 'method': kind}
        bridge = None
        try:
            outdir.mkdir(parents=True, exist_ok=False)
            with (outdir / 'events.jsonl').open('x') as log:
                def event(item):
                    item = dict(time=dt.datetime.now().astimezone().isoformat(), **item)
                    log.write(json.dumps(item, ensure_ascii=False, allow_nan=False) + '\n')
                    log.flush()
                    self._progress(item)
                io = b.Transport(self.socket_path, event)
                bridge = b.FocusBridge(io, self.code, event, snapshot_code=self.snapshot_code)
                bridge.motion_enabled = kind == 'assist'
                with bridge.lease():
                    if kind == 'native':
                        outcome = self._original_af(bridge)
                    else:
                        backend = CameraBackend(bridge, self.cancel.is_set, event)
                        outcome = assist_controller.run(backend, self.cancel.is_set, event)
                outcome['cleanup_complete'] = bridge.cleanup_complete
        except BaseException as exc:
            outcome = dict(outcome, status='fault', error=repr(exc),
                           cleanup_complete=bool(bridge and bridge.cleanup_complete),
                           quarantined=bool(bridge and bridge.quarantined))
        try:
            with (outdir / 'result.json').open('x') as result:
                json.dump(outcome, result, ensure_ascii=False, indent=2, allow_nan=False)
                result.write('\n')
        except Exception as exc:
            outcome = dict(outcome, status='fault', log_error=repr(exc))
        with self.lock:
            stop = outcome.get('stop')
            unverified_stop = isinstance(stop, dict) and stop.get('verified') is not True
            self.fault_latched = (outcome['status'] == 'fault' or
                                  not outcome.get('cleanup_complete') or unverified_stop)
            self.state.update(busy=False, available=not self.fault_latched,
                              state=outcome['status'], outcome=outcome, capture_path=str(outdir),
                              message=('已停止並鎖定，請檢查紀錄；不自動重試。' if self.fault_latched else
                                       '本輪結束並已還原工具。請看結果，不代表光學對焦已獨立驗證。'))
        try:
            # Completion is already committed and cleanup is over. Notifications
            # get detached data and cannot mutate the outcome or fail the worker.
            self.external_event(json.loads(json.dumps(
                {'event': 'job_finished', 'outcome': outcome, 'capture_path': str(outdir)},
                ensure_ascii=False, allow_nan=False)))
        except Exception as exc:
            with self.lock:
                # A callback may have started a subsequent explicit job; do not
                # attach the old notification failure to that newer job.
                if self.state.get('outcome') is outcome:
                    self.state['notification_error'] = repr(exc)
