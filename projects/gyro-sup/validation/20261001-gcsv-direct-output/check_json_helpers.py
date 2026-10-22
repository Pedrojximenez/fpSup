#!/usr/bin/env python3
"""Replay the offline JSON-helper check for the GCSV formatter optimisation.

Assembles current source into temporary files; reads the saved baseline blobs.
No camera, transport, media, deployment or source-writing operation is used.
The harness executes actual ARM code. Native calls are strict stubs, although
these three helpers do not call any native firmware routine.

Run from any directory with a Python environment containing Unicorn:
    python3 -B check_json_helpers.py
JSON goes to stdout. Exit 0 = pass, 1 = failure, 2 = unavailable/skipped.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import sys
import traceback

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
FPSUP = ROOT / 'fpSup'
sys.path[:0] = [str(FPSUP / 'fp_usb_shell'), str(FPSUP / 'gyro')]
from armasm import assemble, symbols  # noqa: E402
from test_gcsv_yield import (  # noqa: E402
    Formatter, HAS_UNICORN, EMULATOR_REASON, OUTPUT, CODE, STACK, STOP,
)

EDITIONS = (
    ('base', ('FPGYRO_EDITION_BASE=1',)),
    ('gcsv', ()),
    ('gcsv-yield', ('FPGYRO_FORMAT_YIELD_RECORDS=128',)),
)
HELPERS = ('ji', 'jm', 'jhalf')


def helper(machine, name, number):
    uc, reg = machine.uc, machine.reg
    machine.returned = False
    uc.mem_write(OUTPUT - 3, b'\xa5' * 80)
    saved = {i: 0x55000000 + i for i in range(4, 12)}
    for i, value in saved.items():
        uc.reg_write(getattr(reg, f'UC_ARM_REG_R{i}'), value)
    uc.reg_write(reg.UC_ARM_REG_R0, number)
    uc.reg_write(reg.UC_ARM_REG_R1, 0xDEADBEEF)
    uc.reg_write(reg.UC_ARM_REG_R2, 0xBAD00002)
    uc.reg_write(reg.UC_ARM_REG_R3, 0xBAD00003)
    uc.reg_write(reg.UC_ARM_REG_R9, OUTPUT)
    uc.reg_write(reg.UC_ARM_REG_SP, STACK + 0xFFF0)
    uc.reg_write(reg.UC_ARM_REG_LR, STOP)
    uc.reg_write(reg.UC_ARM_REG_CPSR, 0x13)
    uc.emu_start(CODE + machine.syms[name], STOP + 4, count=3000)
    assert machine.returned, (name, number, 'return')
    end = uc.reg_read(reg.UC_ARM_REG_R9)
    assert OUTPUT <= end < OUTPUT + 64, (name, number, end)
    result = bytes(uc.mem_read(OUTPUT, end - OUTPUT))
    assert bytes(uc.mem_read(OUTPUT - 3, 3)) == b'\xa5' * 3, (name, number, 'head guard')
    assert bytes(uc.mem_read(end, OUTPUT + 77 - end)) == b'\xa5' * (OUTPUT + 77 - end), (name, number, 'tail guard')
    assert uc.reg_read(reg.UC_ARM_REG_SP) == STACK + 0xFFF0, (name, number, 'SP')
    for i, value in saved.items():
        if i != 9:
            assert uc.reg_read(getattr(reg, f'UC_ARM_REG_R{i}')) == value, (name, number, f'r{i}')
    if name == 'ji':
        assert uc.reg_read(reg.UC_ARM_REG_R1) == 0xDEADBEEF, (name, number, 'r1')
    return result


def main():
    report = {
        'recorded_at_utc': datetime.now(timezone.utc).isoformat(),
        'status': 'running',
        'scope': 'offline assembled ARM JSON helpers; no physical-camera verification',
        'source_sha256': hashlib.sha256((FPSUP / 'gyro/gcsv_rows.S').read_bytes()).hexdigest(),
        'editions': [],
        'failures': [],
        'skips': [],
    }
    if not HAS_UNICORN:
        report.update(status='unavailable', skips=[EMULATOR_REASON])
        print(json.dumps(report, indent=2))
        return 2
    rng = random.Random(813)
    values = sorted(set([
        0, 1, 9, 10, 99, 100, 999, 1000, 32767, 32768, 65535,
        100000, 1000000000, 0xFFFFFFFF,
    ] + [rng.randrange(1 << 32) for _ in range(128)]))
    report.update(random_seed=813, values_per_helper=len(values), helpers=list(HELPERS))
    try:
        for edition, defines in EDITIONS:
            baseline_code = (HERE / 'before' / f'{edition}.bin').read_bytes()
            baseline_symbols = json.loads((HERE / 'before' / f'{edition}-symbols.json').read_text())
            code = assemble(FPSUP / 'gyro/gcsv_task.S', defines)
            old = Formatter(baseline_code, baseline_symbols)
            new = Formatter(code, symbols(FPSUP / 'gyro/gcsv_task.S', defines))
            count = 0
            for name in HELPERS:
                for number in values:
                    if name == 'ji':
                        want = str(number)
                    elif name == 'jm':
                        want = f'{number // 1000}.{number % 1000:03}'
                    else:
                        want = f'{number // 2}.{5 if number % 2 else 0}'
                    a, b = helper(old, name, number), helper(new, name, number)
                    assert a == b == want.encode(), (edition, name, number, a, b, want)
                    count += 1
            report['editions'].append({
                'edition': edition,
                'cases': count,
                'arm_invocations': count * 2,
                'baseline_sha256': hashlib.sha256(baseline_code).hexdigest(),
                'candidate_sha256': hashlib.sha256(code).hexdigest(),
                'candidate_bytes': len(code),
                'status': 'passed',
            })
        report.update(status='passed', total_cases=sum(e['cases'] for e in report['editions']),
                      total_arm_invocations=sum(e['arm_invocations'] for e in report['editions']))
    except Exception:
        report.update(status='failed', failures=[traceback.format_exc()])
    print(json.dumps(report, indent=2))
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
