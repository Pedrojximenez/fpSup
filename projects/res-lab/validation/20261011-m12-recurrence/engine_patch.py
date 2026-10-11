"""Bounded data-only A/B in the existing v38 consumer; never replace live code.

Only the two active M12 virtual entries' ENGFPS words may change. Exact loaded
code slices, boot identity, provider generation, table bounds and before-images
are checked. A normal menu selection must invoke the native picker afterward.
No timing, geometry, latch, registry, instruction or allocation writes occur.
"""
import fcntl
import json
import os
import pathlib
import struct
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[3]
CARD = pathlib.Path(os.environ.get('RESLAB_LIVE_CARD', str(ROOT/'projects/res-lab/cards/20261011-count-v38/debug')))
BASELINE = HERE/os.environ.get('RESLAB_TRIAL_BASELINE', 'usb-restored-before-v39.json')
os.environ['RESLAB_LIVE_CARD'] = str(CARD)
sys.path.insert(0, str(HERE.parent/'20261009-oncamera'))
import live_camera as live
import fps_state
import inspect_runtime as inspect
from ogc_layout import S, ENT

live.LOG = HERE/'commands.jsonl'
F60 = struct.unpack('<I', struct.pack('<f', 60.0))[0]
OLD = {23976: struct.unpack('<I', struct.pack('<f', 240000/1001))[0],
       27972: struct.unpack('<I', struct.pack('<f', 280000/1001))[0]}


def standby():
    assert 'is_recording -> 0' in live.checked_sh('status get is_recording')


def collect(extra_engine=None):
    standby()
    r = fps_state.snapshot()
    baseline = json.loads(BASELINE.read_text())
    for key in ('consumer_base', 'consumer_state', 'producer_base', 'producer_state'):
        assert r[key] == baseline[key], 'boot owner changed'
    for key in ('provider', 'generation', 'row'):
        assert r['registry'][key] == baseline['registry'][key], 'recipe changed'
    assert r['registry']['lock'] == 0 and r['registry']['provider'] == 0x42414c52
    assert r['consumer']['flag'] == 1 and r['consumer']['current'] == r['registry']['row']+1
    assert r['producer']['applied_geometry'] == 12
    assert [r['producer'][k] for k in ('out_w', 'out_h')] == [baseline['producer'][k] for k in ('out_w', 'out_h')], 'output changed from inspected baseline'
    core, state = int(r['consumer_base'], 16), int(r['consumer_state'], 16)
    old = (CARD/'fpSup/32RESCUS.BIN').read_bytes()
    # Header alone cannot distinguish the v38 and v39 code images.
    for offset in ((inspect.FACT['rescustom']['virtual_dispatch_off'] & ~3), 0x800, 19008, 22448, 32400):
        got = live.putfile.mem_get(core+offset, 8, tries=1)
        assert got == list(struct.unpack_from('<8I', old, offset)), 'unknown running code'
    end = live.putfile.mem_get(state+S['S_END'], tries=1)[0]
    start = live.putfile.mem_get(state+S['ENTS'], tries=1)[0]
    count = live.putfile.mem_get(state+S['NENT'], tries=1)[0]
    assert S['BODY'] <= start < end <= 0xc000
    assert 0 < count <= 256 and start+count*ENT['SIZE'] <= end
    targets = []
    for i in range(count):
        offset = start+i*ENT['SIZE']
        words = live.putfile.mem_get(state+offset, ENT['SIZE']//4, tries=1)
        assert len(words) == 16 and all(w is not None for w in words)
        rank = words[ENT['VRATE']//4]
        if words[ENT['ROW']//4] != r['registry']['row'] or rank not in OLD:
            continue
        targets.append({'index': i, 'offset': offset,
                        'address': hex(state+offset+ENT['ENGFPS']),
                        'rank': rank, 'words': words, 'new': F60})
    assert len(targets) == 2 and sorted(t['rank'] for t in targets) == sorted(OLD)
    accepted_extra = ()
    if extra_engine is not None:
        assert extra_engine == struct.unpack('<I', struct.pack('<f', 30.0))[0]
        accepted_extra = (extra_engine,)
    assert all(t['words'][ENT['ENGFPS']//4] in (OLD[t['rank']], F60, *accepted_extra) for t in targets)
    standby()
    return {'runtime': r, 'state_end': end, 'table_start': start,
            'table_count': count, 'targets': targets}


def main():
    action, tag = sys.argv[1:3]
    assert action in ('plan', 'apply')
    dest = HERE/(tag+'.json')
    assert not dest.exists()
    with open('/tmp/fp-af-fusion.lock', 'r') as lease:
        fcntl.flock(lease, fcntl.LOCK_EX|fcntl.LOCK_NB)
        proof = collect()
        proof['action'] = action
        dest.write_text(json.dumps(proof, indent=2)+'\n')
        if action == 'apply':
            planned = json.loads((HERE/(sys.argv[3]+'.json')).read_text())
            assert planned['action'] == 'plan' and planned['targets'] == proof['targets']
            assert all(t['words'][ENT['ENGFPS']//4] == OLD[t['rank']] for t in proof['targets'])
            proof['written'] = []
            for target in proof['targets']:
                standby()
                state = int(proof['runtime']['consumer_state'], 16)
                vp = live.putfile.mem_get(state+S['VRC'], tries=1)[0]
                current = live.putfile.mem_get(vp, 11, tries=1)
                assert current[2] == 0 and current[4] == proof['runtime']['registry']['generation']
                address = int(target['address'], 16)
                assert live.putfile.mem_get(address, tries=1)[0] == OLD[target['rank']]
                live.checked_sh(f'mem set 0x{address:08X} 0x{F60:08X}')
                assert live.putfile.mem_get(address, tries=1)[0] == F60
                proof['written'].append(target['address'])
                dest.write_text(json.dumps(proof, indent=2)+'\n')
            proof['after'] = collect()
            assert all(t['words'][ENT['ENGFPS']//4] == F60 for t in proof['after']['targets'])
            proof['phase'] = 'verified'
            dest.write_text(json.dumps(proof, indent=2)+'\n')
        print(json.dumps({k:proof[k] for k in ('action','table_count','targets','phase','written') if k in proof}, indent=2))


if __name__ == '__main__':
    main()
