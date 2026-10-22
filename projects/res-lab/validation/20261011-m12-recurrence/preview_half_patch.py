"""Eight existing preview pair values only, on verified v39 M12 owners.

Data-only, reversible diagnostic. No instructions, native globals, RAW fields,
sensor timings, registry, allocation or card writes. A normal UI repick applies
the changed profile. collect() assumes its caller already holds the AF lease.
"""
import fcntl
import hashlib
import json
import pathlib
import sys

import engine_patch as g
from ogc_layout import ROW
from preview_half_spec import CHANGES, EXPECTED_SHA

HERE = pathlib.Path(__file__).resolve().parent


def collect():
    assert hashlib.sha256((g.CARD/'fpSup/32RESCUS.BIN').read_bytes()).hexdigest() == EXPECTED_SHA
    assert (HERE/'test-preview-half.log').read_text().strip().splitlines()[-1] == 'OK'
    checked = g.collect()
    assert all(t['words'][g.ENT['ENGFPS']//4] == g.F60 for t in checked['targets'])
    r = checked['runtime']
    state, end = int(r['consumer_state'], 16), checked['state_end']
    def word(offset):
        assert g.S['BODY'] <= offset <= end-4
        return g.live.putfile.mem_get(state+offset, tries=1)[0]
    rows = g.live.putfile.mem_get(state+g.S['ROWS'], tries=1)[0]
    row = rows+(r['consumer']['current']-1)*ROW['SIZE']
    start = word(row+ROW['REC'])
    pairs, targets = [], []
    for i in range(65):
        key = word(start+i*8)
        if key == 0xffffffff:
            break
        assert key < 0x104 and not key & 3
        value = word(start+i*8+4)
        assert key not in {k for k, _ in pairs}
        pairs.append([key, value])
        if key in CHANGES:
            assert value in CHANGES[key]
            targets.append({'key': key, 'offset': start+i*8+4,
                            'address': hex(state+start+i*8+4), 'value': value})
    else:
        raise AssertionError('unterminated canvas')
    frozen = json.loads((HERE.parent/'20261009-recording-formula/frozen-r78.json').read_text())['canvas']
    assert {k for k, _ in pairs} == {int(k, 0) for k in frozen}
    assert all(v == frozen[hex(k)] for k, v in pairs if k not in CHANGES)
    assert len(targets) == len(CHANGES) and {t['key'] for t in targets} == set(CHANGES)
    g.standby()
    return {'runtime': r, 'pairs': pairs, 'targets': targets}


def main():
    action, tag = sys.argv[1:3]
    assert action in ('plan', 'apply', 'restore')
    destination = HERE/(tag+'.json')
    assert not destination.exists()
    before_index, after_index = (1, 0) if action == 'restore' else (0, 1)
    with open('/tmp/fp-af-fusion.lock') as lease:
        fcntl.flock(lease, fcntl.LOCK_EX|fcntl.LOCK_NB)
        data = collect()
        assert all(t['value'] == CHANGES[t['key']][before_index] for t in data['targets'])
        proof = {'action': action, 'phase': 'planned', 'snapshot': data, 'written': [],
                 'candidate_sha256': EXPECTED_SHA}
        def save():
            destination.write_text(json.dumps(proof, indent=2)+'\n')
        save()
        if action != 'plan':
            planned = json.loads((HERE/(sys.argv[3]+'.json')).read_text())
            assert planned['action'] == 'plan' and planned['candidate_sha256'] == EXPECTED_SHA
            original = planned['snapshot']
            for key in ('consumer_base', 'consumer_state', 'producer_base', 'producer_state', 'registry'):
                assert original['runtime'][key] == data['runtime'][key]
            assert [(t['key'], t['address']) for t in original['targets']] == [(t['key'], t['address']) for t in data['targets']]
            assert [[k, v] for k, v in original['pairs'] if k not in CHANGES] == [[k, v] for k, v in data['pairs'] if k not in CHANGES]
            for target in data['targets']:
                fresh = collect()
                assert fresh['runtime']['registry'] == data['runtime']['registry']
                address = int(target['address'], 16)
                before, after = CHANGES[target['key']][before_index], CHANGES[target['key']][after_index]
                assert g.live.putfile.mem_get(address, tries=1)[0] == before
                proof['phase'] = 'writing'
                save()
                g.live.checked_sh(f'mem set 0x{address:08X} 0x{after:08X}')
                assert g.live.putfile.mem_get(address, tries=1)[0] == after
                proof['written'].append(target['address'])
                save()
            result = collect()
            assert all(t['value'] == CHANGES[t['key']][after_index] for t in result['targets'])
            proof['verified_snapshot'] = result
            proof['phase'] = 'verified'
            save()
        print(json.dumps({'action': action, 'phase': proof['phase'], 'written': proof['written']}))


if __name__ == '__main__':
    main()
