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

LAYOUT = Path(__import__('os').environ.get('FPL_LIVE_LAYOUT', str(HERE/'baseline-profile/layout.json')))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('label')
    ap.add_argument('--take-seconds', type=float)
    ap.add_argument('--lossless', type=int, choices=(0, 1))
    ap.add_argument('--fps-enum', type=int, choices=(3, 5, 7))
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
    priority_changed = False
    report = {'diagnostic_worker_priority': 10, 'label': a.label, 'commands': [], 'started_at': time.time()}

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
        meta = json.loads(LAYOUT.with_name('build.json').read_text())['blob']
        if values['slots.installed'] != 1:
            raise RuntimeError('expanded slots were not installed')
        pool = values['slots.pool_ptr']
        if not base <= pool < base + meta['block_bytes'] or pool & 3:
            raise RuntimeError('descriptor pool outside owned LOSS block')
        active = values['slots.active']
        maximum = meta['slot_capacity']
        if not 96 <= active <= maximum or active % 4:
            raise RuntimeError('invalid expanded capacity')
        free = words(pool + 0x112C)[0]
        reg = state + fields['slots.registry']
        registry = []
        for offset in range(0, maximum, 64):
            registry.extend(words(reg + 4 + offset * 4, min(64, maximum - offset)))
        reg_counts = words(reg + 4 + maximum * 4, 4)
        result = {'record': hex(record), 'state': hex(state), 'base': hex(base),
                  'boot': words(0xC072F6F8)[0], 'descriptors_free': free,
                  'registry_occupied': sum(w >= 0x40000000 and not w & 3 for w in registry),
                  'registry_lock': reg_counts[3] & 255,
                  'registry_count': reg_counts[2], 'capacity': active,
                  'idle': idle, 'values': values}
        if free != active or result['registry_occupied'] or result['registry_count'] or result['registry_lock']:
            raise RuntimeError('expanded pool/registry did not return to idle: ' + str(result))
        if any(values[f'slots.cookies[{i}].pending'] for i in range(2)):
            raise RuntimeError('completion cookies remain pending')
        if recording():
            raise RuntimeError('camera entered REC during standby snapshot')
        return result

    try:
        if sh('status get app_current') != 'app_current -> 2' or recording():
            raise RuntimeError('requires CINE standby')
        report['before'] = snapshot()
        tasks = sh('tkos tsklist')
        report['tasks_before'] = tasks
        worker_lines = [line for line in tasks.splitlines() if '_VSHL' in line]
        if len(worker_lines) != 1 or int(worker_lines[0].split('|')[2],16) != words(0xC072F058)[0] + 0x6c or worker_lines[0].split('|')[4].strip() != '28':
            raise RuntimeError('unexpected USB worker identity')
        worker_id = int(re.match(r'(\d+)\(', worker_lines[0]).group(1))
        report['worker_task_id'] = worker_id
        if report['before']['boot'] != int(__import__('os').environ['FPL_EXPECT_BOOT']):
            raise RuntimeError('unexpected boot; no priority change')
        if a.fps_enum is not None:
            sh(f'menu SetMovFramerate {a.fps_enum}')
        # --lossless verifies the state selected through native UI. gui seti
        # can be overwritten by the publisher before REC and is not a setter.
        if a.fps_enum is not None:
            time.sleep(4)
        report['settings'] = {cmd: sh(cmd) for cmd in (
            'menu SetMovRecFormat', 'menu SetMovRecSize',
            'menu SetMovCinemaDNGQuality', 'menu SetMovFramerate', 'gui geti MV_FrameRate',
            'gui geti MV_fpLossless', 'sdcard size 1')}
        save()
        if a.fps_enum is not None:
            row = {3: 3, 5: 6, 7: 8}[a.fps_enum]
            if (report['settings']['menu SetMovFramerate'] != str(a.fps_enum) or
                report['settings']['gui geti MV_FrameRate'] != f'OK:MV_FrameRate -> {row}'):
                raise RuntimeError('native FPS and UI row disagree; no REC sent')
        if a.lossless is not None and report['settings']['gui geti MV_fpLossless'] != f'OK:MV_fpLossless -> {a.lossless}':
            raise RuntimeError('requested lossless state did not persist; no REC sent')
        if a.take_seconds is not None:
            before = sh('dir ' + chr(92) + 'CINEMA')
            if recording():
                raise RuntimeError('already recording')
            # Native bounded ring, no logger/file output or RAM hook injection.
            # Monitor allocation: 32768*28 + 64*(28+52+8), about 0.88 MiB.
            active = words(0xc3821e9c)[0] & 255
            if active: raise RuntimeError('another native task monitor is active')
            priority_changed = True
            report['worker_priority_restore_pending'] = True
            save()
            reply = sh(f'tkos task chgpri {worker_id} 10')
            if reply != f'changed priority (tskid: {worker_id}, tskpri: 10)':
                raise RuntimeError('priority change uncertain; no REC')
            priority_changed = True
            report['tasks_raised'] = sh('tkos tsklist')
            sh('analyzer tskmon_start 32768 64 1000000 52')
            if not words(0xc3821e9c)[0] & 255:
                raise RuntimeError('task monitor did not start; no REC sent')
            report['monitor_started'] = time.time()
            report['start_pulse_time'] = time.time()
            pulse()
            print(f'{a.label}: recording window {a.take_seconds}s', flush=True)
            time.sleep(a.take_seconds)
            report['task_top_recording'] = sh('analyzer tskmon_top 0 10')
            report['monitor_stop'] = sh('analyzer tskmon_stop')
            save()
            still = recording()
            report['active_at_end_of_window'] = still
            if still:
                report['stop_pulse_time'] = time.time()
                pulse()
            # Let the native stop finish, but keep the observation interval short.
            time.sleep(1)
            if recording(): raise RuntimeError('stop not yet completed; no repeated REC')
            report['tasks_after_stop'] = sh('tkos tsklist')
            if words(0xc3821e9c)[0] & 255: raise RuntimeError('monitor still running')
            save()
            time.sleep(9)
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
        if priority_changed:
            sh(f'tkos task chgpri {worker_id} 28')
            priority_changed = False
            report['worker_priority_restore_pending'] = False
            report['tasks_restored'] = sh('tkos tsklist')
        report['completed_at'] = time.time()
        save()
        print(json.dumps({k: report[k] for k in ('label', 'new_clips', 'active_at_end_of_window') if k in report}))
        print('descriptors:', report['before']['descriptors_free'], '->', report['after']['descriptors_free'])
    except BaseException as exc:
        report['error'] = repr(exc)
        report['worker_priority_restore_pending'] = priority_changed
        save()
        raise


if __name__ == '__main__':
    main()
