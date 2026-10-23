"""One bounded tile_force take on the v0.2.0test LOSS build (fields from its layout).

Usage: python3 -B tile_trial.py LABEL WxH|0 [--seconds 2]
Sets LOSS's own tile_force word, records one take with two complete MOVON
pulses, reads the hold counters and the last job, and always puts tile_force
back to 0 while idle. Never repeats a REC pulse after an uncertain reply.
"""
import argparse
import fcntl
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path[:0] = [str(ROOT / 'fpSup/fp_usb_shell'), str(ROOT / 'fpSup/lossless')]
import putfile as pf
import card_status as cs

LAYOUT = HERE.parent / '20261012-bulk-stop-integration/baseline-card/layout.json'
BIN_SHA = 'ad984ce65a025d7acfbf968d0a7c3e43ef94bc89085af6b3a522374e7e9f8137'
COUNTERS = [p + k for p in ('hold.', 'hold_b.') for k in (
    'held', 'compressed', 'refused', 'no_benefit', 'faults', 'dma_failed', 'stalls',
    'job_last_us', 'job_max_us', 'job_count', 'job_sum_us')] + [
    'hold.arrivals', 'hold.passed', 'hold.not_eligible', 'hold.lanes_full',
    'hold.refused_by', 'hold.job.tile_width', 'hold.job.tile_height', 'hold.job.tiles',
    'rec_hold_refused', 'hold_init_failed', 'hold_live']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('label')
    ap.add_argument('tile')
    ap.add_argument('--seconds', type=float, default=2.0)
    a = ap.parse_args()
    assert a.label.replace('-', '').isalnum() and 1 <= a.seconds <= 9
    if a.tile == '0':
        force = 0
    else:
        w, h = map(int, a.tile.lower().split('x'))
        assert 32 <= w <= 512 and w % 32 == 0 and 16 <= h <= 512 and h % 16 == 0
        force = w << 16 | h
    out = HERE / f'tile-{a.label}.json'
    assert not out.exists(), 'refusing to overwrite evidence'
    lock = open('/tmp/fp-af-fusion.lock', 'a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    fields = json.loads(LAYOUT.read_text())['fields']
    report = {'label': a.label, 'force': force, 'seconds': a.seconds, 'commands': []}

    def save():
        out.write_text(json.dumps(report, indent=2))

    def sh(c):
        r = pf.sh(c, retries=0, timeout_ms=5000)
        report['commands'].append([time.time(), c, r]); save()
        if (not r.strip() and not (c.startswith('key ') and r == '\n')) or r.startswith('ERR') or 'not found cmd' in r:
            raise RuntimeError(f'uncertain {c}: {r!r}')
        return r.strip()

    def recording():
        r = sh('status get is_recording')
        assert r in ('is_recording -> 0', 'is_recording -> 1'), r
        return r.endswith('1')

    def word(addr):
        v = pf.mem_get(addr)
        assert len(v) == 1 and v[0] is not None, hex(addr)
        return v[0]

    def idle():
        assert not recording()
        assert word(0xC358E140) == 0 and word(0xC35A952C) & 255 == 0, 'writer busy'

    def pulse():
        try:
            sh('key MOVON')
        finally:
            time.sleep(.12)
            sh('key MOVOFF')

    found = cs.find_record(pf.mem_get)
    assert found, 'no LOSS record'
    _, state, _ = found
    f = lambda k: state + fields[k]
    snap = lambda: {k: word(f(k)) for k in COUNTERS}
    tf = f('tile_force')
    try:
        assert sh('status get app_current') == 'app_current -> 2'
        idle()
        assert word(f('magic')) == 0x44524143 and word(f('menu.result')) == 1
        report['settings'] = {c: sh(c) for c in (
            'menu SetMovRecSize', 'menu SetMovCinemaDNGQuality', 'menu SetMovFramerate',
            'gui geti MV_FrameRate', 'gui geti MV_fpLossless')}
        assert report['settings']['gui geti MV_fpLossless'] == 'OK:MV_fpLossless -> 1'
        assert report['settings']['gui geti MV_FrameRate'] != 'OK:MV_FrameRate -> 9', 'no 240p'
        report['boot'] = word(0xC072F6F8)
        report['tile_force_before'] = word(tf)
        pf.mem_set(tf, force)
        assert word(tf) == force
        report['before'] = snap(); save()
        report['start'] = time.time()
        pulse()
        time.sleep(a.seconds)
        if recording():
            report['stop'] = time.time()
            pulse()
        time.sleep(1.5)
        if recording():
            raise RuntimeError('still recording after stop pulse; no further REC sent')
        for _ in range(30):
            if word(0xC358E140) == 0 and word(0xC35A952C) & 255 == 0:
                break
            time.sleep(1)
        idle()
        time.sleep(2)
        report['after'] = snap()
        d = {k: report['after'][k] - report['before'][k] for k in COUNTERS}
        report['delta'] = d
        save()
        print(json.dumps({k: v for k, v in report['after'].items()}, indent=0))
        print('delta', {k: v for k, v in d.items() if v})
    finally:
        try:
            idle()
            pf.mem_set(tf, 0)
            report['tile_force_restored'] = word(tf)
        except Exception as e:
            report['restore_error'] = repr(e)
        save()


if __name__ == '__main__':
    main()
