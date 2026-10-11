"""Four existing preview pair values only; bounded reversible diagnostic.

No code/allocator/timing/raw-size writes. Known current v40 M12 owner and
generation, exact code and full before-pairs are checked under the AF lease.
"""
import fcntl
import hashlib
import json
import pathlib
import struct
import sys

import engine_patch as g
from test_matching_tap import CHANGES

HERE=pathlib.Path(__file__).resolve().parent
F30=struct.unpack('<I',struct.pack('<f',30.0))[0]
EXPECTED='4358fce4127aedebbff0b93ea9db91f0a2805ae4cc013552dabc2f43e31c99dc'


def collect():
    checked=g.collect(extra_engine=F30)
    assert all(t['words'][g.ENT['ENGFPS']//4] == F30 for t in checked['targets'])
    r=checked['runtime'];s=int(r['consumer_state'],16);end=checked['state_end']
    def word(off):
        assert g.S['BODY'] <= off <= end-4
        return g.live.putfile.mem_get(s+off,tries=1)[0]
    rows=g.live.putfile.mem_get(s+g.S['ROWS'],tries=1)[0]
    from ogc_layout import ROW
    row=rows+(r['consumer']['current']-1)*ROW['SIZE']
    start=word(row+ROW['REC']);pairs=[];targets=[]
    for index in range(65):
        off=start+8*index;key=word(off)
        if key==0xffffffff:break
        assert key<0x108 and not key&3
        value=word(off+4);pairs.append([key,value])
        if key in CHANGES:
            targets.append({'key':key,'offset':off+4,'address':hex(s+off+4),'value':value})
    else:raise AssertionError('unterminated row list')
    assert {t['key'] for t in targets}==set(CHANGES) and len(targets)==4
    g.standby()
    return {'runtime':r,'pairs':pairs,'targets':targets}


def main():
    action,tag=sys.argv[1:3];assert action in ('plan','apply','restore')
    dest=HERE/(tag+'.json');assert not dest.exists()
    assert hashlib.sha256((g.CARD/'fpSup/32RESCUS.BIN').read_bytes()).hexdigest()==EXPECTED
    assert (HERE/'test-matching-tap.log').read_text().strip().splitlines()[-1]=='OK'
    with open('/tmp/fp-af-fusion.lock') as lease:
        fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
        data=collect();old_index,new_index=(1,0) if action=='restore' else (0,1)
        assert all(t['value']==CHANGES[t['key']][old_index] for t in data['targets'])
        proof={'action':action,'phase':'planned','snapshot':data,'written':[]}
        def save():dest.write_text(json.dumps(proof,indent=2)+'\n')
        save()
        if action!='plan':
            planned=json.loads((HERE/(sys.argv[3]+'.json')).read_text());assert planned['action']=='plan'
            original=planned['snapshot']
            for k in ('consumer_base','consumer_state','producer_base','producer_state','registry'):
                assert original['runtime'][k]==data['runtime'][k]
            assert [(t['key'],t['address']) for t in original['targets']]==[(t['key'],t['address']) for t in data['targets']]
            assert [[k,v] for k,v in original['pairs'] if k not in CHANGES]==[[k,v] for k,v in data['pairs'] if k not in CHANGES]
            for t in data['targets']:
                # Refuse a recipe publication between scalar writes.
                fresh=collect();assert fresh['runtime']['registry']==data['runtime']['registry']
                addr=int(t['address'],16);old,new=CHANGES[t['key']][old_index],CHANGES[t['key']][new_index]
                assert g.live.putfile.mem_get(addr,tries=1)[0]==old
                proof['phase']='writing';save()
                g.live.checked_sh(f'mem set 0x{addr:08X} 0x{new:08X}')
                assert g.live.putfile.mem_get(addr,tries=1)[0]==new
                proof['written'].append(t['address']);save()
            result=collect();assert all(t['value']==CHANGES[t['key']][new_index] for t in result['targets'])
            assert [[k,v] for k,v in original['pairs'] if k not in CHANGES]==[[k,v] for k,v in result['pairs'] if k not in CHANGES]
            proof['verified_snapshot']=result;proof['phase']='verified';save()
        print(json.dumps({'action':action,'phase':proof['phase'],'written':proof['written']}))


if __name__=='__main__':main()
