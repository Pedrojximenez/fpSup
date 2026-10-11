"""Replay captured source objects through the stock ARM preview constructors.

No installable payload or media writes. Candidate parameters remain hypotheses.
"""
import hashlib
import json
import struct
from pathlib import Path
import verify_preview_candidate as native
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_SP, UC_ARM_REG_PC

ROOT = Path(__file__).resolve().parents[1]
trace = (ROOT / 'diagnostics/fullheight-preview-trace-return/SSD/FP3KPV/STATE.BIN').read_bytes()
assert hashlib.sha256(trace).hexdigest() == '6d1ae03185faa9f3d5a989b948ce82166ab43b6bbc51e96132aa91fbceb63710'
u, run, put, get = native.u, native.run, native.put, native.get
PARAM, SOURCE, DESC, CTX = native.PARAM, native.SOURCE, native.DESC, native.CTX
CONFIG = 0x10001000
cases = []
for name, sample, changes in [
    ('observed_standby', 0, {}),
    ('observed_recording', 6, {}),
    ('observed_photo', 50, {}),
    ('candidate_standby_crop_only', 0, {0x28: 1334}),
    ('candidate_recording_height', 6, native.height_changes),
]:
    record = trace[64 + sample * 0x900:64 + (sample + 1) * 0x900]
    assert struct.unpack_from('<I', record, 24)[0] == 1
    observed_source = record[0x1a0:0x200]
    parameters = list(struct.unpack('<67I', record[0x200:0x30c]))
    for offset, value in changes.items():
        parameters[offset // 4] = value
    u.mem_write(SOURCE, observed_source)
    put(SOURCE + 4, [PARAM])
    put(PARAM, parameters)
    put(CTX, [0, 0])
    u.mem_write(DESC, bytes(0xc0))
    run(0xc0438018, DESC, SOURCE, CTX, writes=[(DESC, DESC + 0xc0)])
    descriptor = get(DESC, 48)
    run(0xc0435428, SOURCE, writes=[(SOURCE + 0x10, SOURCE + 0x58)])
    pools = bytes(u.mem_read(SOURCE + 0x10, 0x48))
    if not changes:
        assert pools == observed_source[0x10:0x58], name
    u.mem_write(CONFIG, bytes(0x1b0))
    # Stop before the device-singleton-dependent tail, after all geometry and
    # pool fields have been copied. The tail sets config+190, not those fields.
    native.allowed[:] = [(0x10008000, native.SP), (CONFIG, CONFIG + 0x1b0)]
    u.reg_write(UC_ARM_REG_SP, native.SP)
    u.reg_write(UC_ARM_REG_R0, SOURCE)
    u.reg_write(UC_ARM_REG_R1, CONFIG)
    u.emu_start(0xc0434ef8, 0xc04353ec, count=10000)
    assert u.reg_read(UC_ARM_REG_PC) == 0xc04353ec
    config = bytes(u.mem_read(CONFIG, 0x1b0))
    if not changes:
        # C01D1630 transforms some fields; compare known direct-copy geometry
        # and per-pool sizes, not uninitialized/derived downstream fields.
        for offset in (0x28, 0x2c, 0x30, 0x34, 0x38, 0x3c, 0x68, 0x148, 0x150):
            assert config[offset:offset+4] == record[0x440+offset:0x444+offset], (name, hex(offset))
    pool_words = struct.unpack('<18I', pools)
    cases.append(dict(case=name, sample=sample, changes={hex(k):v for k,v in changes.items()},
                      maximum_dimensions=get(SOURCE+8, 2), descriptor=descriptor,
                      pools=list(pool_words), pool_sum=sum(pool_words[i]*pool_words[i+1] for i in range(0,18,2)),
                      config=list(struct.unpack('<108I', config)), passed=True))
standby, recording, photo, candidate_idle, candidate_rec = cases
assert candidate_idle['descriptor'][:22] == standby['descriptor'][:22]
assert candidate_rec['descriptor'][:22] == recording['descriptor'][:22]
assert candidate_idle['pools'] == standby['pools']
assert candidate_rec['pools'][1] == 4064296
assert candidate_idle['descriptor'][22:30] == photo['descriptor'][22:30]
assert candidate_rec['descriptor'][22:30] == photo['descriptor'][22:30]
report = dict(cases=cases, trace_sha256=hashlib.sha256(trace).hexdigest(),
              native_functions=['0xc0438018', '0xc0435428', '0xc0434ef8'],
              validated='Stock ARM constructors and config export prefix with captured live maximum dimensions and parameters. No calls mocked; exporter stops at C04353EC before device-dependent tail. Firmware read-only, destination and stack writes bounded. Observed pool sizing and direct-copy config fields reproduced exactly.',
              limitations=['Does not execute allocation/reservation or DMA.', 'Does not prove that unchanged-resolution selection rebuilds cached objects.', 'Display scaling, cadence and visual framing need hardware validation.'])
out = ROOT / 'analysis/firmware/preview/live-source-emulation.json'
out.write_text(json.dumps(report, indent=2)+'\n')
for c in cases:
    print(c['case'], 'maximum', c['maximum_dimensions'], 'preview', c['descriptor'][22:30], 'pool sum', c['pool_sum'])
print('PASS: captured pool/config reproduction and two preview geometry hypotheses.')
