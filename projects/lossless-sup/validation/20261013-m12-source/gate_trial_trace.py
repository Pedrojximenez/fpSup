"""One bounded take on the refusal-gate candidate (fields from its layout).

Usage: python3 -B gate_trial.py LABEL [--seconds 2]
Read-only on LOSS state: checks tile_force is 0, records one take with two
complete MOVON pulses, reads the hold and gate counters, and whether the
take was still recording when the stop pulse was due (no self-stop).
Never repeats a REC pulse after an uncertain reply.
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

LAYOUT = HERE / 'trace-candidate/layout.json'
BIN_SHA = '3b1536eecd57b5f9d5523def2ac6fd5fd8a881276d78dcf2b3e50571b71261d9'
COUNTERS = ['take_frames', 'record_diag.writer_calls', 'slots.cookies[0].pending'] + [p + k for p in ('hold.', 'hold_b.') for k in (
    'held', 'compressed', 'refused', 'no_benefit', 'faults', 'dma_failed', 'stalls',
    'job_last_us', 'job_max_us', 'job_count', 'job_sum_us')] + [
    'hold.arrivals', 'hold.passed', 'hold.not_eligible', 'hold.lanes_full',
    'hold.refused_by', 'hold.job.tile_width', 'hold.job.tile_height', 'hold.job.tiles',
    'rec_hold_refused', 'hold_init_failed', 'hold_live', 'rec_events', 'rec_admitted', 'rec_raw', 'stops'] + [
    'gate.' + k for k in ('streak', 'closed', 'since_probe', 'closes', 'reopens', 'probes', 'skipped')]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('label')
    ap.add_argument('--seconds', type=float, default=2.0)
    ap.add_argument('--tile', default='0', help='tile_force WxH for this take (restored to 0 after)')
    ap.add_argument('--bulk-limit', type=int, default=0,
                    help='experiment: at REC set bulk_policy.frame_limit (files per batch)')
    ap.add_argument('--no-hold', action='store_true',
                    help='A/B control: at REC set hold_live 0, every frame goes stock (reset by the next take)')
    ap.add_argument('--no-gate', action='store_true',
                    help='A/B control: at REC, set gate.streak_limit 0 (gate passes all; reset by the next take)')
    a = ap.parse_args()
    assert a.label.replace('-', '').isalnum() and 1 <= a.seconds <= 9
    out = HERE / f'gate-{a.label}.json'
    assert not out.exists(), 'refusing to overwrite evidence'
    lock = open('/tmp/fp-af-fusion.lock', 'a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    fields = json.loads(LAYOUT.read_text())['fields']
    report = {'label': a.label, 'seconds': a.seconds, 'commands': []}

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
        assert word(tf) == 0, 'tile_force must be 0'
        if a.tile != '0':
            w, h = map(int, a.tile.lower().split('x'))
            assert 32 <= w <= 512 and w % 32 == 0 and 16 <= h <= 512 and h % 16 == 0
            report['tile_force'] = w << 16 | h
            pf.mem_set(tf, w << 16 | h)
            assert word(tf) == w << 16 | h
        assert word(f('gate.streak_limit')) == 8 or word(f('gate.streak_limit')) == 0
        report['before'] = snap(); save()
        report['start'] = time.time()
        events = word(f('rec_admitted'))
        pulse()
        if a.bulk_limit:
            for _ in range(200):
                if word(f('rec_admitted')) != events:
                    time.sleep(.05)
                    pf.mem_set(f('bulk_policy.frame_limit'), a.bulk_limit)
                    break
            report['bulk_limit_now'] = word(f('bulk_policy.frame_limit'))
            report['frames_when_set'] = word(f('take_frames'))
            save()
        if a.no_hold:
            for _ in range(200):
                if word(f('rec_admitted')) != events:
                    time.sleep(.05)
                    pf.mem_set(f('hold_live'), 0)
                    break
            report['hold_disabled_at'] = time.time() - report['start']
            report['frames_when_disabled'] = word(f('take_frames'))
            save()
        if a.no_gate:
            for _ in range(200):
                if word(f('rec_admitted')) != events:
                    time.sleep(.05)
                    pf.mem_set(f('gate.streak_limit'), 0)
                    break
            report['gate_disabled_at'] = time.time() - report['start']
            report['gate_limit_now'] = word(f('gate.streak_limit'))
            report['frames_when_disabled'] = word(f('take_frames'))
            save()
        time.sleep(a.seconds)
        report['recording_at_stop'] = recording()
        if report['recording_at_stop']:
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
        if a.tile != '0':
            try:
                idle()
                pf.mem_set(tf, 0)
                report['tile_force_restored'] = word(tf)
            except Exception as e:
                report['restore_error'] = repr(e)
        save()


if __name__ == '__main__':
    main()
