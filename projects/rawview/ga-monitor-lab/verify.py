#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only local generated-payload checks; --arm also runs real constructor."""
import argparse
import json
from pathlib import Path
import struct
import build as B
import model as M


def verify(folder, arm=False):
    data = (folder/'shadowlift2/45RAWV.BIN').read_bytes()
    prior = (folder/'combined/45RAWV.BIN').read_bytes()
    baseline = (folder/'arri-reference/45RAWV.BIN').read_bytes()
    for name in B.EXPECTED:
        B.pinned((folder/name/'45RAWV.BIN').read_bytes(), B.EXPECTED[name], name)
    assert data[:B.ROW_BASE] == prior[:B.ROW_BASE]
    assert data[B.ROW_END:] == prior[B.ROW_END:]
    assert data[0x1374:0x1554] == baseline[0x1374:0x1554]
    lut, _ = M.build_lut(data)
    max_error = 0
    for iso in range(31):
        for group in (0, 2):
            assert M.build_record_lut(data, group*31+iso, lut) == M.build_record_lut(prior, group*31+iso, lut)
        for group in (1, 3):
            i = group*31+iso
            before, after = M.build_record_lut(prior,i,lut), M.build_record_lut(data,i,lut)
            assert all(a <= b for a,b in zip(after, after[1:]))
            assert after[0] == 0 and min(after[1:]) > 0
            assert max(after) == max(before) < B.LIMIT
            gain, bias, row, a, b, threshold = M.record(data,i)
            assert (gain,row,a,b,threshold) == (65536,iso,0,0,-2147483648)
            old_row = struct.unpack_from('<146H', prior, B.ROW_BASE+iso*B.STRIDE)
            for fp in range(2048):
                assert 0 <= after[fp]-before[fp] <= 350
                if before[fp] >= B.GRAY:
                    assert after[fp] == before[fp]
                pos = (lut[fp]*gain/65536+bias)/65536
                if pos < 0:
                    target = 0
                else:
                    p = min(pos*10,145)
                    j = min(int(p),144)
                    target = round(B.lift2(old_row[j]+(p-j)*(old_row[j+1]-old_row[j])))
                max_error = max(max_error,abs(target-after[fp]))
    assert max_error <= 2
    report = {'status':'PASS', 'ga_points':126976, 'sa_points_unchanged':126976,
              'max_runtime_reference_error_codes': max_error,
              'new_tone_clip_points':0, 'arm_points':None, 'hardware_tested':False}
    if arm:
        from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM
        from unicorn.arm_const import UC_ARM_REG_R4, UC_ARM_REG_PC
        base, tables = 0x50000000,0x51000000
        machine = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        machine.mem_map(base,0x10000)
        machine.mem_write(base,data)
        machine.mem_map(tables,0x90000)
        machine.reg_write(UC_ARM_REG_R4,tables)
        machine.emu_start(base+0x508,base+0x6B0,count=40_000_000)
        assert machine.reg_read(UC_ARM_REG_PC) == base+0x6B0
        for i in range(124):
            offset = (i if i < 62 else i+4)*0x1000
            actual = struct.unpack('<2048H',bytes(machine.mem_read(tables+offset,0x1000)))
            assert actual == tuple(M.build_record_lut(data,i,lut)), i
        report['arm_points'] = 253952
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('build_dir',type=Path)
    parser.add_argument('--arm',action='store_true')
    args = parser.parse_args()
    print(json.dumps(verify(args.build_dir,args.arm),indent=2))
