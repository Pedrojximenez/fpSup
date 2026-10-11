"""Identify exact native records for the temporary parser-copy hook.

The hook adds one image key or the QS maximum while the native UI parser reads
that record. It restores the original input position afterward. No NBU record
is relocated or overwritten in firmware memory.
"""
import struct,json,hashlib
from pathlib import Path
from inspect_uic_resources import load
from experimental_ui_record_compaction import animation

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'prototype/development/native-ui'
ALIAS={'FP3K_L':0xfffffff0,'FP3K_M':0xfffffff1,'FP3K_QS':0xfffffff2,'FP3K_SET':0xfffffff3,'FP3K_LH':0xfffffff4,'FP3K_MH':0xfffffff5}

def build():
    main,strings,records=load();plans=[]
    mapping={('L_resolution_1','L_resolution_2'):('FP3K_L',2),
             ('M_resolution_1','M_resolution_2'):('FP3K_M',2),
             ('qs_resolution_1_S','qs_resolution_2_S'):('FP3K_QS',2),
             ('set_resolution_1','set_resolution_2'):('FP3K_SET',2),
             ('L_resolution_1','L_resolution_2','L_resolution_dci4K'):('FP3K_LH',3),
             ('M_resolution_1','M_resolution_2','M_resolution_dci4K'):('FP3K_MH',3)}
    for address,size,tag in records:
        data=main[address:address+size];props=animation(data)
        if props is None:continue
        pos=28
        for typ,component,name,dimension,keys in props:
            names=tuple(strings.get(struct.unpack_from('>I',k,6)[0]) for k in keys)
            if typ==2 and strings.get(name)=='image' and names in mapping:
                alias,index=mapping[names]
                assert [struct.unpack_from('>H',k,4)[0] for k in keys]==list(range(0,33*len(keys),33))
                insertion=pos+20+10*len(keys)
                new=bytearray(data[:insertion]+struct.pack('>IHI',0,index*33,ALIAS[alias])+data[insertion:])
                struct.pack_into('>I',new,4,len(new));struct.pack_into('>I',new,pos,len(keys)+1)
                assert animation(new) is not None
                plans.append(dict(address=hex(0xc0000000+address),size=size,kind='image-key',
                                  count_offset=pos,insertion=insertion,alias=alias,index=index,
                                  old=data.hex(),new=new.hex()))
                break
            pos+=20+10*len(keys)
    for address in [0xc237249f,0xc25e405a]:
        data=main[address-0xc0000000:address-0xc0000000+40]
        assert struct.unpack_from('>II',data)==(0x1000e,40)
        assert struct.unpack_from('>I',data,28)[0]==0x18
        new=bytearray(data[:32]+struct.pack('>f',2.)+data[32:])
        struct.pack_into('>I',new,4,44);struct.pack_into('>I',new,28,0x1a)
        plans.append(dict(address=hex(address),size=40,kind='QS-limit',count_offset=28,
                          insertion=32,alias=None,index=2,old=data.hex(),new=new.hex()))
    assert plans
    assert max(len(bytes.fromhex(p['new'])) for p in plans)<=512
    report=dict(status='Offline parser-copy plans; not installed',aliases=ALIAS,plans=plans,
                maximum_record_bytes=max(len(bytes.fromhex(p['new'])) for p in plans),
                firmware_sha256=hashlib.sha256(main).hexdigest())
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'ui-resource-plan.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Planned',len(plans)-2,'resolution animations and 2 QS limits; maximum record',report['maximum_record_bytes'])
    return report

if __name__=='__main__':build()
