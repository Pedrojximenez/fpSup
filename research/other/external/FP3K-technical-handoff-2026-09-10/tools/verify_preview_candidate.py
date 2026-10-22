"""Offline preview geometry/buffer experiment; does not build installable firmware.

Execute the stock ARM constructor, buffer-size functions and path selector with
bounded outputs. Keep the camera-tested RAW changes separate from hypotheses.
"""
import hashlib
import json
import struct
from pathlib import Path
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_PROT_READ, UC_PROT_EXEC, UC_HOOK_MEM_WRITE
from unicorn.arm_const import *
from fullheight_candidate import plan

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis/firmware/preview'
firmware = (ROOT / 'analysis/firmware/MAIN_c0000000.bin').read_bytes()
assert hashlib.sha256(firmware).hexdigest() == 'aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622'
profiles = json.loads((ROOT / 'analysis/firmware/raw-profiles.json').read_text())
u = Uc(UC_ARCH_ARM, UC_MODE_ARM)
size = (len(firmware) + 4095) & ~4095
u.mem_map(0xc0000000, size)
u.mem_write(0xc0000000, firmware)
u.mem_protect(0xc0000000, size, UC_PROT_READ | UC_PROT_EXEC)
u.mem_map(0x10000000, 0x10000)
PARAM, SOURCE, DESC, CTX, INPUT, RESULT = [0x10000000 + i for i in (0x100, 0x300, 0x600, 0x800, 0x900, 0xa00)]
SP, STOP = 0x1000fff0, 0xc0000000
allowed = []

def guard(uc, access, address, size, value, data):
    assert any(lo <= address and address + size <= hi for lo, hi in allowed), hex(address)

u.hook_add(UC_HOOK_MEM_WRITE, guard)

def put(address, words):
    u.mem_write(address, struct.pack('<' + 'I' * len(words), *words))

def get(address, count):
    return list(struct.unpack('<' + 'I' * count, u.mem_read(address, count * 4)))

def run(address, *args, writes=()):
    allowed[:] = [(0x10008000, SP), *writes]
    u.reg_write(UC_ARM_REG_SP, SP)
    u.reg_write(UC_ARM_REG_LR, STOP)
    u.reg_write(UC_ARM_REG_C1_C0_2, 0xf00000)
    u.reg_write(UC_ARM_REG_FPEXC, 0x40000000)
    for reg, value in zip((UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3), args):
        u.reg_write(reg, value)
    u.emu_start(address, STOP, count=50000)
    assert u.reg_read(UC_ARM_REG_PC) == STOP
    assert u.reg_read(UC_ARM_REG_SP) == SP
    return u.reg_read(UC_ARM_REG_R0)

row = next(r for r in profiles['rows'] if 429 in r['profile_ids'])
capture_changes = {}
for column in profiles['columns']:
    address = column['table'] + row['index'] * 4
    for entry in plan():
        if entry['address'] == address:
            capture_changes[column['offset']] = entry['replacement']
assert len(capture_changes) == 8

# Native photo profiles use a 2016x1344 raster and 2000x1334 visible area.
# Leave video format (12-bit), reduction enums and zoom untouched initially.
height_changes = {0x10: 1344, 0x28: 1334, 0xe0: 1344}
cases = []
specs = [('stock_video', 429, {}), ('camera_tested_3k', 429, capture_changes),
         ('full_height_preview_hypothesis', 429, capture_changes | height_changes),
         ('photo_profile_1', 1, {}), ('photo_profile_41', 41, {})]
for name, profile_id, changes in specs:
    base = next(r for r in profiles['rows'] if profile_id in r['profile_ids'])
    parameters = base['words'] + [6064, 4042]
    for offset, value in changes.items():
        parameters[offset // 4] = value
    put(PARAM, parameters)
    u.mem_write(SOURCE, bytes(0x60))
    put(SOURCE, [profile_id, PARAM, 6064, 4042])
    put(SOURCE + 0x58, [0xc0bd04b0])
    put(CTX, [0, 0])
    u.mem_write(DESC, bytes(0xc0))
    run(0xc0438018, DESC, SOURCE, CTX, writes=[(DESC, DESC + 0xc0)])
    descriptor = get(DESC, 48)
    raw = descriptor[:2] + [max(x, 1024) for x in descriptor[18:20]] + [(1, 3, 5)[descriptor[20]], (1, 3)[descriptor[21]], descriptor[8]]
    preview = descriptor[22:24] + [max(x, 1024) for x in descriptor[40:42]] + [(1, 3, 5)[descriptor[42]], (1, 3)[descriptor[43]], descriptor[30]]
    put(INPUT, raw + preview)
    initial = bytearray(0x4c)
    for offset, value in {4:1,8:1,12:1,16:1,24:1,28:2,36:1,40:1,44:1,48:1,52:1024,56:1024,60:1024,64:1024}.items():
        struct.pack_into('<I', initial, offset, value)
    u.mem_write(RESULT, bytes(initial))
    run(0xc0325228, 0, INPUT, RESULT, writes=[(RESULT, RESULT + 0x4c)])
    selector = get(RESULT, 19)
    # C0435428 fills per-pool counts and byte sizes. Source+8/+C are
    # supplied maximum dimensions, not observed live camera values.
    run(0xc0435428, SOURCE, writes=[(SOURCE + 0x10, SOURCE + 0x58)])
    pools = get(SOURCE + 0x10, 18)
    allocations = {hex(offset): {'count': pools[(offset-0x10)//4], 'bytes_each': pools[(offset-0x10)//4+1]}
                   for offset in range(0x10, 0x58, 8)}
    cases.append(dict(case=name, parameters_changed={hex(k):v for k,v in changes.items()},
                      descriptor=descriptor, raw_input=raw, preview_input=preview,
                      path_enable_bytes=list(u.mem_read(RESULT, 3)), selector=selector,
                      preview_crop_origin=descriptor[28:30], pools=allocations,
                      pool_sum=sum(a['count']*a['bytes_each'] for a in allocations.values())))

stock, current, candidate, photo1, photo41 = cases
assert candidate['raw_input'] == current['raw_input']
assert candidate['descriptor'][:22] == current['descriptor'][:22]
assert candidate['preview_input'] == [2016, 1344, 1024, 1024, 3, 3, 0]
assert candidate['preview_crop_origin'] == [8, 5]
assert candidate['path_enable_bytes'] == current['path_enable_bytes']
assert candidate['selector'][9:11] == current['selector'][9:11]
assert candidate['pools']['0x10']['bytes_each'] == 2016*1344*12//8 + 40
assert candidate['pools']['0x10']['bytes_each'] > current['pools']['0x10']['bytes_each']
preview_plan = []
for offset, value in height_changes.items():
    column = next(c for c in profiles['columns'] if c['offset'] == offset)
    preview_plan.append(dict(address=column['table'] + row['index']*4,
                             expected=row['words'][offset//4], replacement=value,
                             parameter_offset=offset))
report = dict(cases=cases, preview_only_plan=preview_plan,
              validated='Unmodified ARM descriptor builder, pool-size constructor and selector executed. Firmware read-only; bounded stack and object writes. No firmware calls mocked.',
              limitations=['Not installable. No camera changes.', 'Pool calculations use supplied maximum dimensions 6064x4042. Pool reservations, live object lifecycle and DMA are not tested.', 'No LCD/HDMI crop, scaling, preview queue or recording cadence emulated.', 'Photo profile IDs are reference data, not proof of active live routing.'])
OUT.mkdir(exist_ok=True)
(OUT/'candidate-emulation.json').write_text(json.dumps(report, indent=2)+'\n')
for c in cases:
    print(c['case'], 'preview', c['preview_input'], 'crop', c['preview_crop_origin'], 'pool bytes', c['pool_sum'])
print('PASS: stock ARM preview geometry, pool sizing and path selection; not a camera validation.')
