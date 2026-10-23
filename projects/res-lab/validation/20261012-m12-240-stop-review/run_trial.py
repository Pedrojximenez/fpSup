"""One bounded reproduction with current M12240 and the installed LOSS policy.

No setting changes, no reboot, no repeated toggle after automatic stop. All
mode/core checks precede REC; camera traffic is absent during the take window.
"""
import fcntl
import importlib.util
import json
import re
import sys
import time

import inspect_current as I

C = I.C
spec = importlib.util.spec_from_file_location('review_lcd',
    I.HERE.parent / '20261011-virtual-rate-context-live/native_lcd.py')
LCD = importlib.util.module_from_spec(spec)
spec.loader.exec_module(LCD)


def clips():
    text = C.live.checked_sh('dir ' + chr(92) + 'CINEMA')
    return {m.group(1) for m in re.finditer(r'\b(A\d{3}_\d{3})\s*$', text, re.M)}


def check(r):
    s = r['consumer']['state']
    e = r['consumer']['picked_entry']
    row = r['consumer']['rows'][s['CUR'] - 1]
    assert row['label'] == 'M12240' and s['VRATE'] == 23976
    assert r['consumer']['donor'] == 12 and r['consumer']['variant'][1] == 6
    assert (e['W0'], e['W1'], e['ENGFPS']) == (0x014A014A, 0x0006038E, 0x436FC29F)
    assert r['settings']['gui geti MV_fpLossless'] == 'OK:MV_fpLossless -> 1'
    assert r['settings']['menu SetMovCinemaDNGQuality'] == '0'
    assert r['settings']['sdcard slot'] == 'slot now slot = sd0'
    assert r['consumer']['screen'] == 'LV_CINE_MEDIUM'
    assert r['loss']['descriptors_free'] == 96 and r['loss']['registry_occupied'] == 0
    assert r['hooks']['0xc0377118'] == '0xea000160'


def capture(dest, proof, save, before_start=None, after_idle=None):
    proof['before'] = I.inspect(dest / 'native-before.json')
    check(proof['before'])
    proof['lcd_before'] = LCD.shot(dest.name + '-before', dest)
    proof['clips_before'] = sorted(clips())
    if before_start is not None:
        before_start()

    def pulse(action):
        proof[action + '_requested'] = True
        save()
        try:
            C.live.checked_sh('key MOVON')
        finally:
            time.sleep(.12)
            C.live.checked_sh('key MOVOFF')
            proof[action + '_released'] = True
            save()

    proof['camera_polling_during_take'] = False
    start = time.monotonic()
    pulse('start')
    time.sleep(max(0, 2 - (time.monotonic() - start)))
    proof['recording_at_target'] = C.recording()
    proof['stop_requested'] = False
    if proof['recording_at_target']:
        assert C.recording() == 1
        pulse('stop')
    for _ in range(10):
        if C.recording() == 0:
            break
        time.sleep(.5)
    else:
        raise RuntimeError('REC stays active; no toggle replay')
    for n in range(6):
        try:
            proof['idle_after'] = C.idle()
            break
        except AssertionError:
            if n == 5:
                raise
            time.sleep(1)
    if after_idle is not None:
        after_idle()
    proof['record_log'] = C.live.checked_sh('rec log-out')
    proof['new_clips'] = sorted(clips() - set(proof['clips_before']))
    assert len(proof['new_clips']) == 1
    save()


if __name__ == '__main__':
    assert re.fullmatch('[a-z0-9-]+', sys.argv[1])
    dest = I.HERE / sys.argv[1]
    dest.mkdir()
    proof = {'label': dest.name, 'target_seconds': 2, 'settings_changed': False}
    save = lambda: (dest / 'trial.json').write_text(json.dumps(proof, indent=2) + '\n')
    with open('/tmp/fp-af-fusion.lock') as lease:
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            capture(dest, proof, save)
            proof['after'] = I.inspect(dest / 'native-after.json')
            check(proof['after'])
            proof['lcd_after'] = LCD.shot(dest.name + '-after', dest)
            proof['phase'] = 'completed'
        except BaseException as exc:
            proof['error'] = type(exc).__name__ + ': ' + str(exc)
            raise
        finally:
            save()
    print(proof['new_clips'], proof['record_log'], flush=True)
