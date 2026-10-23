"""Read only the stopped native profiler allocation, through reviewed MEM1."""
import sys,fcntl,json,time,struct,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'fpSup/fp_usb_shell'));import putfile as pf
label=sys.argv[1];assert label.replace('-','').isalnum()
out=HERE/(label+'-ring.bin');meta=out.with_suffix('.json');assert not out.exists() and not meta.exists()
f=open('/tmp/fp-af-fusion.lock','a');fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
assert pf.sh('status get is_recording',retries=0,timeout_ms=5000).strip()=='is_recording -> 0'
w=pf.mem_get(0xc3821e70,12);assert len(w)==12 and all(x is not None for x in w)
alloc,size,_,_,split,n,wrap,capacity,base,splitbase,splitcap,active=w
assert active&255==0 and capacity==32768 and 0<=n<capacity and size==923136
assert 0x44000000<=alloc<0x60000000
canonical=(alloc+63)&~63
assert base==canonical+0x80000000 and canonical+capacity*28<=alloc+size
assert splitbase==base+capacity*28
caps=pf.mem_caps();assert caps and caps['windows'][7]==(0,0,0)
clock=pf.mem_get(0xc2efabc8,4);assert clock[3]==0xc2ef72d4
vtable=pf.mem_get(clock[3],4)
count=capacity if wrap&15 else n
pf.mem_window(7,canonical,count*28,1)
try: raw=pf.mem_read(canonical,count*28,label='task monitor')
finally: pf.mem_window(7,0,0,0)
assert len(raw)==count*28 and pf.mem_get(0xc3821e70,12)==w
out.write_bytes(raw)
meta.write_text(json.dumps({'time':time.time(),'monitor':w,'clock':clock,'vtable':vtable,'count':count,'sha256':hashlib.sha256(raw).hexdigest()},indent=2))
print(meta.name, count, 'records', [hex(x) for x in clock], [hex(x) for x in vtable])
