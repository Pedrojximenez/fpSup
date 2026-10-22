"""Bounded standby reads of the existing Res-Lab/Res-Custom owners.

No picker calls, code injection, setting writes or recording keys.
The maintained inspector verifies the loaded headers against the v38 facts.
"""
import fcntl
import json
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[3]
os.environ.setdefault('RESLAB_LIVE_CARD', str(ROOT / 'projects/res-lab/cards/20261011-count-v38/debug'))
sys.path.insert(0, str(HERE.parent / '20261009-oncamera'))
import live_camera as live
import inspect_runtime as inspect
import fps_state
from ogc_layout import S, ROW, VAR

OFFSETS = (0, 4, 12, 16, 28, 32, 36, 40, 44, 56, 88, 92, 96, 100,
           136, 144, 192, 196, 200, 208, 212, 216, 220, 224, 228, 244, 248, 252, 256)


def main():
    dest = HERE / (sys.argv[1] + '.json')
    assert not dest.exists(), dest
    live.LOG = HERE / 'commands.jsonl'
    with open('/tmp/fp-af-fusion.lock', 'r') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert 'is_recording -> 0' in live.checked_sh('status get is_recording')
        r = fps_state.snapshot()
        m = int(r['producer_state'], 16)
        vals = live.putfile.mem_get(m + inspect.FACT['state_fields']['canvas'], 29)
        assert len(vals) == 29
        r['producer_canvas'] = dict(zip(map(hex, OFFSETS), vals))
        s = int(r['consumer_state'], 16)
        end = live.putfile.mem_get(s + S['S_END'])[0]
        assert S['BODY'] <= end <= 0xc000

        def word(off):
            assert 0 <= off <= end - 4
            return live.putfile.mem_get(s + off)[0]

        def pairs(off):
            result = {}
            for _ in range(65):
                key = word(off)
                if key == 0xffffffff:
                    return result
                assert key < 0x108 and not key & 3
                result[hex(key)] = word(off + 4)
                off += 8
            raise AssertionError('unterminated canvas list')

        active = bool(r['consumer']['flag'] and r['consumer']['current'])
        r['consumer_canvas_applicable'] = active
        effective = {}
        if active:
            assert 1 <= r['consumer']['current'] <= r['consumer']['nrows']
            row = word(S['ROWS']) + (r['consumer']['current'] - 1) * ROW['SIZE']
            r['consumer_canvas_base'] = pairs(word(row + ROW['REC']))
            effective.update(r['consumer_canvas_base'])
        if 'picked_entry' in r:
            vi = r['picked_entry']['VAR']
            assert vi < word(S['NVAR'])
            variant = word(S['VARS']) + vi * VAR['SIZE']
            r['picked_variant'] = {key: word(variant + off) for key, off in VAR.items() if key != 'SIZE'}
            vlist = r['picked_variant']['LIST']
            r['consumer_canvas_variant'] = pairs(vlist) if vlist else {}
            effective.update(r['consumer_canvas_variant'])
        if active:
            r['consumer_canvas_effective'] = effective
        frozen = json.loads((HERE.parent / '20261009-recording-formula/frozen-r78.json').read_text())['canvas']
        r['producer_r78_differences'] = {key: {'r78': value, 'current': r['producer_canvas'].get(key)}
            for key, value in frozen.items() if r['producer_canvas'].get(key) != value}
        if active:
            r['consumer_r78_differences'] = {key: {'r78': value, 'current': effective.get(key)}
                for key, value in frozen.items() if effective.get(key) != value}
        r['record_log'] = live.checked_sh('rec log-out')
        r['standby_at_end'] = 'is_recording -> 0' in live.checked_sh('status get is_recording')
        dest.write_text(json.dumps(r, indent=2) + '\n')
        print(json.dumps({key: r[key] for key in ('fps_state', 'sensor_timing_fps',
            'fps_getter', 'producer_r78_differences', 'consumer_r78_differences',
            'consumer_canvas_variant', 'standby_at_end') if key in r}, indent=2))


if __name__ == '__main__':
    main()
