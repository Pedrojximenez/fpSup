"""Execute the frozen, user-verified r10 recipe; compare the current producer.

Offline only. The old recipe and its template come from the exact deployed
VBIN, not today's source or a rebuilt approximation.
"""
import hashlib, json, pathlib, struct, sys
ROOT = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT/'projects/open-gate/build'))
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM
from unicorn.arm_const import UC_ARM_REG_LR, UC_ARM_REG_SP
import test_virtual_rcd as V

OLD = ROOT/'projects/res-lab/cards/20261001-240-r10-ramonly-no14bit/fast-debug/fpSup.BIN'
blob = OLD.read_bytes()
assert hashlib.sha256(blob).hexdigest() == '918c9b515ea45c0403e1b22e19497cdcfb948ecf72e019f56c5f11089af57f34'
_, count, _, size = struct.unpack_from('<4sIII', blob)
at = 16 + 8*count
records = []
for i in range(count):
    dest, n = struct.unpack_from('<2I', blob, 16+8*i)
    records.append((dest, blob[at:at+n]))
    at += n + (-n % 4)
assert at == 16 + 8*count + size

mu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
for base, n in ((0xc0b00000,0x100000),(0xc0720000,0x20000),
                (0xc2f00000,0x100000),(0xc3400000,0x100000),(0x40000000,0x40000)):
    mu.mem_map(base,n)
image = (ROOT/'out/MAIN_c0000000.bin').read_bytes()
mu.mem_write(0xc0b00000, image[0xb00000:0xc00000])
for dest, data in records:
    if 0xc0b00000 <= dest < 0xc0c00000 or 0xc0720000 <= dest < 0xc0740000:
        mu.mem_write(dest,data)
mu.mem_write(0xc2f1e654,struct.pack('<4I',0xc0b59500,70,0xc0b59dc0,70))
mu.mem_write(0xc343b588,struct.pack('<I',0xc2f1e654))
mu.reg_write(UC_ARM_REG_SP,0x40020000)
mu.reg_write(UC_ARM_REG_LR,0x40030000)
mu.emu_start(0xc0730c20,0x40030000,count=2_000_000)
recipe = list(struct.unpack('<27I',mu.mem_read(0xc07324c0,108)))
n = struct.unpack('<I',mu.mem_read(0xc0732560,4))[0]
assert 0<n<=32
oldpairs = dict(struct.iter_unpack('<2I',mu.mem_read(0xc0732564,8*n)))

out, facts = V.built()
test = V.VirtualTests('test_contract_abi_and_status');test.out,test.f=out,facts
cam = test.boot();cam.geometry(12,992,662)
newvalues=struct.unpack('<29I',cam.mu.mem_read(cam.m()+facts['state_fields']['canvas'],116))
offsets=(0,4,12,16,28,32,36,40,44,56,88,92,96,100,136,144,192,196,200,208,212,216,220,224,228,244,248,252,256)
newpairs=dict(zip(offsets,newvalues));newpairs.update({0x30:struct.unpack('<I',struct.pack('<f',240000/1001))[0],0x80:7,0x84:7,0xb0:1})
profiles=json.loads((ROOT/'research/other/external/FP3K-technical-handoff-2026-09-10/analysis/firmware/raw-profiles.json').read_text())
rows={r['index']:r['words'] for r in profiles['rows']}
oldrow=list(rows[profiles['mapping'][13]])
newrow=list(rows[profiles['mapping'][83]])
for o,v in oldpairs.items():oldrow[o//4]=v
oldrow[0x30//4]=newpairs[0x30]
for o,v in newpairs.items():newrow[o//4]=v
diff=[{'offset':hex(i*4),'r10':a,'v9':b} for i,(a,b) in enumerate(zip(oldrow,newrow)) if a!=b]
report={'r10_sha256':hashlib.sha256(blob).hexdigest(),'r10_recipe':recipe,
        'r10_canvas':{hex(o):v for o,v in oldpairs.items()},
        'v9_canvas':{hex(o):v for o,v in newpairs.items()},'row_difference':diff}
pathlib.Path(__file__).with_suffix('.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
