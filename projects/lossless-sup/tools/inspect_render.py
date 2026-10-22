#!/usr/bin/env python3
"""Pinned offline resource/property trace; no camera or transport."""
import importlib.util
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[3]
def module(name, path):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    sys.modules[name] = m
    s.loader.exec_module(m)
    return m

b = module('candidate', ROOT / 'fpSup/lossless/menu/build_menu_candidate.py')
a = b.load_audit(ROOT / 'research/ui/tools/native_ui_audit.py')
d = (ROOT / 'out/seg0_c0000000.bin').read_bytes()
assert a.sha256(d) == a.SEG0_SHA256
schemas = b.load_property_schemas(d)
resolve = lambda x: a.pool_string(d, x)
width = {0:4,1:4,2:4,3:4,4:16,5:16,6:8,7:12,8:16,9:4,10:4,11:5,12:4,13:4,14:4}
def prop(r):
    kind = resolve(r.word(8))
    if r.tag not in b.MASK_OFFSETS or kind not in schemas: return None
    cur=b.MASK_OFFSETS[r.tag]
    out={'address':a.address(r.offset),'kind':kind,'owner':r.word(b.OWNER_OFFSETS[r.tag]),'fields':{}}
    for i,p in enumerate(schemas[kind]):
        if i%32==0: mask=r.word(cur); cur+=4
        if not (mask>>(i%32))&1: continue
        ty=p['kind']; raw=r.data[cur:cur+width[ty]]
        if ty in (11,12,13): v=None if r.word(cur)==0xffffffff else resolve(r.word(cur))
        elif ty in (1,4,5,6,7,8): v=struct.unpack('>'+str(len(raw)//4)+'f',raw)
        else: v=struct.unpack('>'+str(len(raw)//4)+'I',raw)
        out['fields'][p['name']]={'offset':cur,'type':ty,'value':v}
        cur+=width[ty]
    assert cur==len(r.data)
    return out

if __name__=='__main__':
    start,end=(int(x,0) for x in sys.argv[1:3]) if len(sys.argv)>2 else (0x216c8b8,0x2172bc6)
    out=[]
    for r in a.records(d,start,end):
        if r.tag==0x10003:
            out.append({'object':r.word(20),'parent':r.word(24),'name':resolve(r.word(28)),'address':a.address(r.offset)})
        elif r.tag in b.MASK_OFFSETS:
            p=prop(r)
            if p: out.append(p)
    print(json.dumps(out,indent=2))
