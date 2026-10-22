"""Validate FPV1 trace structure and summarize live preview configuration.
Does not infer image coverage from dimensions alone.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path
from build_preview_probe import ROOT, OUT, COUNT, STRIDE, TOTAL, INTERVAL

def analyze(data):
    assert len(data)==TOTAL, ('length',len(data),TOTAL)
    header=struct.unpack_from('<16I',data)
    assert header[0]==0x31565046 and header[1:4]==(1,STRIDE,COUNT),header[:4]
    assert header[6]==INTERVAL and header[7]==1 and header[8]==TOTAL
    assert header[4]%4==0 and 0x40000000<=header[4]<=0x4ffe0000 and header[5]>=0x20000
    rows=[]
    for i in range(COUNT):
        r=data[64+i*STRIDE:64+(i+1)*STRIDE]
        w=struct.unpack('<'+'I'*(STRIDE//4),r)
        assert w[0]==i
        p=w[0x200//4:0x30c//4]
        copied=bool(w[6]&1)
        native=w[0x440//4:0x5f0//4]
        rows.append(dict(index=i,nominal_ms=i*INTERVAL,sensor_before=w[1],sensor_after=w[2],copy_flags=w[6],
                         profile_id=w[0x1a0//4] if copied else None,
                         parameters=list(p) if copied else None,
                         source_preview_raster=[p[0xc//4],p[0x10//4]] if copied else None,
                         source_preview_override=[p[0xd8//4],p[0xe0//4]] if copied else None,
                         source_visible_crop=[p[0x20//4],p[0x28//4]] if copied else None,
                         profile_kind=p[0x1c//4] if copied else None,
                         native_preview_raster=list(native[0x38//4:0x40//4]),
                         native_visible_crop=list(native[0x30//4:0x38//4]),
                         native_kind=native[0x68//4],
                         private_active=w[0x7b0//4],private_status=w[0x7a4//4],
                         qs_records_seen=w[0x7d0//4],qs_records_extended=w[0x7d4//4],
                         primary_output_raster=list(w[0x35c//4:0x364//4]),
                         primary_output_visible=list(w[0x36c//4:0x374//4]),
                         layout_seen_bits=w[0x7d8//4],layout_last_descriptor=hex(w[0x7dc//4]),
                         display_mode=struct.unpack_from('<H',r,0x858)[0],
                         native_config_sha256=hashlib.sha256(r[0x440:0x7a0]).hexdigest(),
                         display_state_sha256=hashlib.sha256(r[0x800:0x900]).hexdigest()))
    transitions=[]
    previous=None
    fields=('sensor_before','sensor_after','copy_flags','profile_id','source_visible_crop','native_visible_crop','private_active','display_mode')
    for row in rows:
        key=[row[k] for k in fields]
        if key!=previous:
            transitions.append({k:row[k] for k in ('index','nominal_ms',*fields)})
            previous=key
    return dict(header=list(header),samples=rows,transitions=transitions,
                limitations='Sequential RAM copies; transition rows can be inconsistent. Native values may be stale. Dimensions do not prove coverage, scaling or LCD appearance.')

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('directory',type=Path)
    p.add_argument('--output',required=True,type=Path)
    args=p.parse_args()
    m=json.loads((OUT/'manifest.json').read_text())
    loaded=(args.directory/'LOADED.BIN').read_bytes()
    assert len(loaded)==m['probe_bytes'] and hashlib.sha256(loaded).hexdigest()==m['probe_sha256']
    data=(args.directory/'STATE.BIN').read_bytes()
    report=analyze(data)
    alloc=struct.unpack('<3I',(args.directory/'POOL.BIN').read_bytes())
    assert list(alloc[:2])==report['header'][4:6]
    report['capture_sha256']=hashlib.sha256(data).hexdigest()
    report['probe_sha256']=m['probe_sha256']
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report['transitions'],indent=2))
