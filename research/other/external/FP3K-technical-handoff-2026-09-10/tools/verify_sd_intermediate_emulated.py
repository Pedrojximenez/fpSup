"""Explore full-height SD-sized RAW descriptors offline, never a camera patch."""
import hashlib
import json
import struct
from pathlib import Path
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_PROT_READ, UC_PROT_EXEC, UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis/firmware'
b = (OUT / 'MAIN_c0000000.bin').read_bytes()
assert hashlib.sha256(b).hexdigest() == 'aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622'
u = Uc(UC_ARCH_ARM, UC_MODE_ARM)
n = (len(b) + 4095) & ~4095
u.mem_map(0xc0000000, n)
u.mem_write(0xc0000000, b)
u.mem_protect(0xc0000000, n, UC_PROT_READ | UC_PROT_EXEC)
BASE, STACK, STOP = 0x10000000, 0x10010000, 0xc0000000
u.mem_map(BASE, 0x4000)
u.mem_map(STACK, 0x4000)
allowed = []
def guard(uc, access, a, n, v, data):
    assert any(lo <= a and a+n <= hi for lo, hi in allowed), hex(a)
u.hook_add(UC_HOOK_MEM_WRITE, guard)
def run(addr, *args, writes=()):
    allowed[:] = [(STACK, STACK+0x4000), *writes]
    u.reg_write(UC_ARM_REG_SP, STACK+0x3ff0)
    u.reg_write(UC_ARM_REG_LR, STOP)
    for reg, value in zip((UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2), args):
        u.reg_write(reg, value)
    u.emu_start(addr, STOP, count=20000)
    assert u.reg_read(UC_ARM_REG_PC) == STOP
    return u.reg_read(UC_ARM_REG_R0)
def put(addr, words):
    u.mem_write(addr, struct.pack('<'+'I'*len(words), *words))
def get(addr, count):
    return list(struct.unpack('<'+'I'*count, u.mem_read(addr, count*4)))

profiles = json.loads((OUT/'raw-profiles.json').read_text())
PARAM, SOURCE, DESC, CTX, INPUT, RESULT = [BASE+i for i in (0x100,0x300,0x600,0x800,0x900,0xa00)]
# Sensor geometry is an input assumption, not an emulated sensor mode switch.
specs = [
    ('stock_fhd24', 431, {}, [3032,1708]),
    ('full_readout_1920x1280_from_uhd', 429,
     {0xdc:1936,0xe4:1290,0x24:1920,0x2c:1280,0x64:3200,0xd4:3200}, [6064,4042]),
    ('full_readout_1920x1280_from_fhd', 431,
     {0xe4:1290,0x2c:1280,0x64:3200,0xd4:3200,0x60:3200,0xd0:3200}, [6064,4042]),
    # Match the stock FHD pixel budget approximately while retaining a3:2 crop.
    ('full_readout_1728x1152_from_uhd', 429,
     {0xdc:1744,0xe4:1162,0x24:1728,0x2c:1152,0x64:3550,0xd4:3550}, [6064,4042]),
]
cases = []
for name, pid, changes, sensor in specs:
    row = next(r for r in profiles['rows'] if pid in r['profile_ids'])
    words = row['words']+[6064,4042]
    for offset, value in changes.items(): words[offset//4] = value
    put(PARAM, words)
    u.mem_write(SOURCE, bytes(0x60))
    put(SOURCE, [pid, PARAM])
    put(SOURCE+0x58, [0xc0bd04b0])
    put(CTX, [0,0])
    u.mem_write(DESC, bytes(0xc0))
    run(0xc0438018, DESC, SOURCE, CTX, writes=[(DESC,DESC+0xc0)])
    d = get(DESC, 48)
    raw = [d[0],d[1],max(d[18],1024),max(d[19],1024),(1,3,5)[d[20]],(1,3)[d[21]],d[8]]
    preview = [d[22],d[23],max(d[40],1024),max(d[41],1024),(1,3,5)[d[42]],(1,3)[d[43]],d[30]]
    put(INPUT, raw+preview)
    initial = bytearray(0x4c)
    for off,val in {4:1,8:1,12:1,16:1,24:1,28:2,36:1,40:1,44:1,48:1,52:1024,56:1024,60:1024,64:1024}.items():
        struct.pack_into('<I', initial, off, val)
    u.mem_write(RESULT, bytes(initial))
    run(0xc0325228, 0, INPUT, RESULT, writes=[(RESULT,RESULT+0x4c)])
    raw_bytes = run(0xc03d9630, DESC)
    extent = [(s*1024+z//2)//z for s,z in zip(sensor,raw[2:4])]
    assert all(a >= v for a,v in zip(extent,raw[:2])), (name,extent,raw)
    assert d[8] == 0
    cases.append(dict(name=name,base_profile=pid,hypothetical=bool(changes),
        parameter_changes={hex(k):v for k,v in changes.items()},
        assumed_sensor_raster=sensor,raw_input=raw,preview_input=preview,
        raw_crop_origin=d[6:8],pre_crop_extent=extent,
        path_enable_bytes=list(u.mem_read(RESULT,3)),path_words=get(RESULT,19),
        firmware_raw_bytes=raw_bytes,
        payload_MB_per_second={str(fps):raw_bytes*fps/1000000 for fps in (24,25,30)},
        descriptor_words=d))
assert cases[0]['raw_input'][:4] == [1936,1090,1600,1600]
assert cases[1]['raw_input'][:4] == [1936,1290,3200,3200]
report = dict(cases=cases,
    validation='Stock descriptor, path selector and RAW byte-count routines executed without stubs, with bounded runs and guarded writes.',
    limitations='No sensor timing or mode switch, hardware filtering, live DMA, card throughput, writer metadata, or all-pixel contribution is validated. Parameter changes are offline hypotheses, not installable patches.')
(OUT/'sd-intermediate-emulation.json').write_text(json.dumps(report,indent=2)+'\n')
for c in cases:
    print(c['name'],'RAW',c['raw_input'],'preview',c['preview_input'],
          'paths',c['path_enable_bytes'],'bytes',c['firmware_raw_bytes'],
          'MB/s',c['payload_MB_per_second'])
