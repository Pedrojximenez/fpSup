#!/usr/bin/env python3
"""Bounded, explicitly invoked camera trial; no action on import.

Uses the maintained shell and card-status reader. Never retries a REC key.
No USB traffic between the start pulse and the end-of-window state check.
An uncertain command stops the trial; it never blindly sends another toggle.
"""
import argparse
import fcntl
import json
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / 'fpSup/fp_usb_shell'), str(ROOT / 'fpSup/lossless')]
import putfile as pf
import card_status as cs

LAYOUT = ROOT / 'projects/lossless-sup/validation/20261012-lossless-independent/module/layout.json'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('label')
    ap.add_argument('--take-seconds', type=float)
    ap.add_argument('--lossless', type=int, choices=(0, 1))
    ap.add_argument('--fps-enum', type=int, choices=(3, 7))
    a = ap.parse_args()
    if not re.fullmatch(r'[a-z0-9_-]+', a.label):
        ap.error('simple unique label required')
    if a.take_seconds is not None and not 1 <= a.take_seconds <= 45:
        ap.error('take window must be 1..45 seconds')
    out = HERE / (a.label + '.json')
    if out.exists():
        ap.error('refusing to overwrite evidence')
    lock = open('/tmp/fp-af-fusion.lock', 'a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    report = {'label': a.label, 'commands': [], 'started_at': time.time()}

    def save():
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2))

    def sh(command):
        result = pf.sh(command, retries=0, timeout_ms=5000)
        report['commands'].append({'time': time.time(), 'command': command, 'reply': result})
        save()
        # Successful native key commands return one newline, with no text.
        if (not result.strip() and not (command.startswith('key ') and result == '\n')) or result.startswith('ERR') or 'not found cmd' in result:
            raise RuntimeError(f'uncertain/failed command {command}: {result!r}')
        return result.strip()

    def recording():
        result = sh('status get is_recording')
        if result not in ('is_recording -> 0', 'is_recording -> 1'):
            raise RuntimeError(f'unknown recording state: {result!r}')
        return result.endswith('1')

    def pulse():
        # Always release the single key press, including an uncertain down.
        try:
            sh('key MOVON')
        finally:
            time.sleep(0.12)
            sh('key MOVOFF')

    def words(addr, n=1):
        result = pf.mem_get(addr, n)
        if len(result) != n or any(w is None for w in result):
            raise RuntimeError(f'incomplete memory read at {addr:#x}')
        return result

    def snapshot():
        if recording():
            raise RuntimeError('snapshot requires standby')
        idle = {'xmp_file_pointer': words(0xC358E140)[0],
                'movie_writing': words(0xC35A952C)[0] & 255}
        if any(idle.values()):
            raise RuntimeError(f'writer not yet idle: {idle}')
        if words(0xC0377118)[0] != 0xEA000160:
            raise RuntimeError('independent STOPFX has not loaded')
        if words(0xC063F828)[0] == 0x9805D102:
            raise RuntimeError('new lossless batch hook has not loaded')
        found = cs.find_record(pf.mem_get)
        if found is None:
            raise RuntimeError('missing LOSS record')
        record, state, base = found
        fields = json.loads(LAYOUT.read_text())['fields']
        # Fixed scalar offsets from the exact deployed build. No frame chain.
        values = {k: words(state + off)[0] for k, off in fields.items()
                  if k not in cs.ARRAY_WORDS and k not in ('trace', 'elog')}
        if values['magic'] != 0x44524143 or values['menu.result'] != 1:
            raise RuntimeError('lossless state/menu not initialized')
        pool = words(0xC2F1F3D8)[0]
        if not 0xC0000000 <= pool < 0xC8000000 or pool & 3:
            raise RuntimeError('invalid descriptor pool')
        free = words(pool + 0x112C)[0]
        registry = words(0xC351FF48, 96)
        result = {'record': hex(record), 'state': hex(state), 'base': hex(base),
                  'boot': words(0xC072F6F8)[0], 'descriptors_free': free,
                  'registry_occupied': sum(w >= 0x40000000 and not w & 3 for w in registry),
                  'registry_lock': words(0xC351FF44 + 0x190)[0] & 255,
                  'idle': idle, 'values': values}
        if recording():
            raise RuntimeError('camera entered REC during standby snapshot')
        return result

    try:
        if sh('status get app_current') != 'app_current -> 2' or recording():
            raise RuntimeError('requires CINE standby')
        report['before'] = snapshot()
        if a.fps_enum is not None:
            sh(f'menu SetMovFramerate {a.fps_enum}')
        # --lossless verifies the state selected through native UI. gui seti
        # can be overwritten by the publisher before REC and is not a setter.
        if a.fps_enum is not None:
            time.sleep(4)
        report['settings'] = {cmd: sh(cmd) for cmd in (
            'menu SetMovRecFormat', 'menu SetMovRecSize',
            'menu SetMovCinemaDNGQuality', 'menu SetMovFramerate',
            'gui geti MV_fpLossless', 'sdcard size 1')}
        save()
        if a.lossless is not None and report['settings']['gui geti MV_fpLossless'] != f'OK:MV_fpLossless -> {a.lossless}':
            raise RuntimeError('requested lossless state did not persist; no REC sent')
        if a.take_seconds is not None:
            before = sh('dir ' + chr(92) + 'CINEMA')
            if recording():
                raise RuntimeError('already recording')
            report['start_pulse_time'] = time.time()
            pulse()
            print(f'{a.label}: recording window {a.take_seconds}s', flush=True)
            time.sleep(a.take_seconds)
            still = recording()
            report['active_at_end_of_window'] = still
            if still:
                report['stop_pulse_time'] = time.time()
                pulse()
            time.sleep(10)
            if recording():
                raise RuntimeError('still recording; no automatic second toggle')
            report['record_log'] = sh('rec log-out')
            after = sh('dir ' + chr(92) + 'CINEMA')
            report['folders_before'] = before
            report['folders_after'] = after
            old = {x.split()[-1] for x in before.splitlines() if '<DIR>' in x}
            report['new_clips'] = [x.split()[-1] for x in after.splitlines()
                                   if '<DIR>' in x and x.split()[-1] not in old]
            if len(report['new_clips']) != 1:
                raise RuntimeError('did not observe exactly one new clip')
        report['after'] = snapshot()
        report['completed_at'] = time.time()
        save()
        print(json.dumps({k: report[k] for k in ('label', 'new_clips', 'active_at_end_of_window') if k in report}))
        print('descriptors:', report['before']['descriptors_free'], '->', report['after']['descriptors_free'])
    except BaseException as exc:
        report['error'] = repr(exc)
        save()
        raise


if __name__ == '__main__':
    main()
