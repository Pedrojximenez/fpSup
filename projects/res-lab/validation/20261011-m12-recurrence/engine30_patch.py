"""Reversible diagnostic of two existing M12 entries; no live code changes.

Same boot owner/code/recipe/table checks as engine_patch. Exactly the two
ENGFPS words may change 60 -> 30 or be restored. The native picker must apply
the changed entry through the normal UI; no latch or native hardware writes.
"""
import fcntl
import hashlib
import json
import pathlib
import struct
import sys

import engine_patch as g

F30 = struct.unpack('<I', struct.pack('<f', 30.0))[0]
HERE = pathlib.Path(__file__).resolve().parent
VALIDATED = {
    '4358fce4127aedebbff0b93ea9db91f0a2805ae4cc013552dabc2f43e31c99dc': 'test-engine30-repick.log',
    '650c6fa0f27d216adba551cbec777741d42b39f4374e8b76db0f71dfbfe1cb85': 'test-engine30-v39.log',
}


def main():
    action, tag = sys.argv[1:3]
    assert action in ('plan', 'apply', 'restore')
    dest = HERE/(tag+'.json')
    assert not dest.exists()
    expected = hashlib.sha256((g.CARD/'fpSup/32RESCUS.BIN').read_bytes()).hexdigest()
    assert expected in VALIDATED
    assert (HERE/VALIDATED[expected]).read_text().strip().splitlines()[-1] == 'OK'
    with open('/tmp/fp-af-fusion.lock') as lease:
        fcntl.flock(lease, fcntl.LOCK_EX|fcntl.LOCK_NB)
        data = g.collect(extra_engine=F30)
        before, after = (F30, g.F60) if action == 'restore' else (g.F60, F30)
        assert all(t['words'][g.ENT['ENGFPS']//4] == before for t in data['targets'])
        proof = {'action':action, 'phase':'planned', 'before':before, 'after':after,
                 'candidate_sha256':expected, 'snapshot':data, 'written':[]}
        def save():
            dest.write_text(json.dumps(proof, indent=2)+'\n')
        save()
        if action != 'plan':
            planned = json.loads((HERE/(sys.argv[3]+'.json')).read_text())
            assert planned['action'] == 'plan'
            original = planned['snapshot']
            for key in ('consumer_base','consumer_state','producer_base','producer_state','registry'):
                assert original['runtime'][key] == data['runtime'][key]
            for a, b in zip(original['targets'], data['targets']):
                assert (a['address'],a['offset'],a['rank']) == (b['address'],b['offset'],b['rank'])
                x,y=list(a['words']),list(b['words'])
                x[g.ENT['ENGFPS']//4]=y[g.ENT['ENGFPS']//4]=0
                assert x == y
            for target in data['targets']:
                g.standby()
                state = int(data['runtime']['consumer_state'],16)
                vp = g.live.putfile.mem_get(state+g.S['VRC'],tries=1)[0]
                registry = g.live.putfile.mem_get(vp,11,tries=1)
                assert registry[2] == 0 and registry[4] == data['runtime']['registry']['generation']
                addr = int(target['address'],16)
                assert g.live.putfile.mem_get(addr,tries=1)[0] == before
                proof['phase']='writing';save()
                g.live.checked_sh(f'mem set 0x{addr:08X} 0x{after:08X}')
                assert g.live.putfile.mem_get(addr,tries=1)[0] == after
                proof['written'].append(target['address']);save()
            verified = g.collect(extra_engine=F30)
            assert all(t['words'][g.ENT['ENGFPS']//4] == after for t in verified['targets'])
            proof['verified_snapshot']=verified
            proof['phase']='verified';save()
        print(json.dumps({'action':action,'phase':proof['phase'],'written':proof['written']}))


if __name__ == '__main__':
    main()
