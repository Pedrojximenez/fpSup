#!/usr/bin/env python3
"""Does any other sup touch the words 70PERF.BIN claims?

Two independent looks at every sup file in the tree (v3 *.BIN with an FSB1
header; v2 fpSup.BIN containers are scanned statically only):

1. static: any 32-bit literal, or movw/movt pair (ARM and Thumb-2), equal to
   one of our addresses or inside [first, last] of a claimed table;
2. dynamic: run the sup's entry in unicorn against the real image with a
   fake service table that records every claim(addr, len, kind) and grants
   it; stop at the first fault or after a budget.  A sup that faults before
   finishing its claims is reported as "partial" -- its static result stands.

    python3 -B conflicts.py [--json out.json]
"""
import argparse, collections, json, pathlib, struct, sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
import build_perf as P              # noqa: E402

from unicorn import Uc, UcError, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE, UC_HOOK_MEM_UNMAPPED
from unicorn import arm_const as A

SEG0 = ROOT / 'out' / 'seg0_c0000000.bin'
SEG1 = ROOT / 'out' / 'seg1_c2ef6e00.bin'
BLOCK, SVC, STOP, STACK = 0xC8000000, 0xC8F00000, 0xC7FFF000, 0xC3F00000
SEARCH = [ROOT / 'fpSup' / 'tools' / 'merge-v3' / 'inputs', ROOT / 'fpSup' / 'releases', ROOT / 'projects',
          ROOT / 'fpSup']


def our_addresses():
    """Every claimed word (multi-word claims expanded, e.g. C05DD5C8..CF) plus
    every patch site itself (C05DD5CA is only 2-aligned)."""
    _, info, _ = P.build(set(), 1)
    out = set()
    for c in info['claims']:
        a = int(c['addr'], 16)
        out.update(range(a, a + c['bytes'], 4))
    out.update(int(w['addr'], 16) for w in info['writes'])
    return sorted(out)


def files():
    seen, out = set(), []
    for top in SEARCH:
        for p in sorted(top.rglob('*')):
            if 'worktrees' in p.parts or 'sys-perf' in p.parts or not p.is_file():
                continue
            if p.suffix.upper() != '.BIN' and not (p.parent.name == 'fpSup' and p.suffix == ''):
                continue
            try:
                d = p.read_bytes()
            except OSError:
                continue
            if len(d) < 64 or len(d) > 8_000_000:
                continue
            h = hash(d)
            if h in seen:
                continue
            seen.add(h)
            kind = 'v3' if d[:4] == b'FSB1' else 'vbin' if d[:4] == b'VBIN' else None
            if kind:
                out.append((p, kind, d))
    return out


def movw_movt(d):
    """Values built by movw/movt pairs (ARM and Thumb-2), same register."""
    vals = set()
    lo = {}
    for o in range(0, len(d) - 3, 4):                         # ARM
        v = struct.unpack_from('<I', d, o)[0]
        if (v & 0x0FF00000) == 0x03000000:
            lo[(v >> 12) & 15] = ((v >> 4) & 0xF000) | (v & 0xFFF)
        elif (v & 0x0FF00000) == 0x03400000:
            r = (v >> 12) & 15
            if r in lo:
                vals.add(lo[r] | ((((v >> 4) & 0xF000) | (v & 0xFFF)) << 16))
    tl = {}
    for o in range(0, len(d) - 3, 2):                         # Thumb-2
        h1, h2 = struct.unpack_from('<HH', d, o)
        if (h1 & 0xFB70) in (0xF240, 0xF2C0) and not h2 & 0x8000:
            imm = ((h1 & 0xF) << 12) | (((h1 >> 10) & 1) << 11) | (((h2 >> 12) & 7) << 8) | (h2 & 0xFF)
            r = (h2 >> 8) & 15
            if h1 & 0xFB70 == 0xF240:
                tl[r] = imm
            elif r in tl:
                vals.add(tl[r] | (imm << 16))
    return vals


def static(d, addrs, lo, hi):
    lits = {struct.unpack_from('<I', d, o)[0] for o in range(0, len(d) - 3, 4)}
    lits |= {struct.unpack_from('<I', d, o)[0] for o in range(2, len(d) - 3, 4)}
    vals = lits | movw_movt(d)
    exact = sorted(a for a in addrs if a in vals or (a | 1) in vals)
    near = sorted(v for v in vals if lo <= v <= hi and v not in addrs)
    return exact, near


def dynamic(d, budget=3_000_000):
    """Claims made by this v3 sup's entry, as far as it gets."""
    mu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    mu.ctl_set_cpu_model(A.UC_CPU_ARM_CORTEX_A7)
    mu.mem_map(0xC0000000, 0x04000000)
    mu.mem_write(0xC0000000, SEG0.read_bytes())
    mu.mem_write(0xC2EF6E00, SEG1.read_bytes())
    mu.mem_map(BLOCK, 0x01000000)
    mu.mem_map(0xC7000000, 0x01000000)
    hdr = struct.unpack_from('<8I', d, 0)
    block = d + bytes(max(0, hdr[3] - len(d)))
    if len(block) > 0x00E00000:
        return None, 'too big'
    mu.mem_write(BLOCK, block)
    stubs = {}
    names = {8: 'claim', 12: 'claim_res', 16: 'chain_next', 20: 'cave', 24: 'publish', 28: 'log',
             32: 'holder', 36: 'self', 44: 'button'}
    mu.mem_write(SVC, struct.pack('<I', 4))
    for off, n in names.items():
        mu.mem_write(SVC + off, struct.pack('<I', SVC + 0x100 + off))
        stubs[SVC + 0x100 + off] = n
    mu.mem_write(SVC + 40, struct.pack('<I', 0))
    mu.mem_write(0xC7F00000, b'\\fpSup\\XX.BIN\0')
    claims, res, status = [], [], ['ok']
    cave = [0xC072E100]

    def ret(v):
        mu.reg_write(A.UC_ARM_REG_R0, v & 0xFFFFFFFF)
        mu.reg_write(A.UC_ARM_REG_PC, mu.reg_read(A.UC_ARM_REG_LR))

    def hook(uc, addr, size, _):
        n = stubs.get(addr)
        if not n:
            return
        r = lambda x: uc.reg_read(x)
        if n == 'claim':
            kind = struct.unpack('<I', uc.mem_read(r(A.UC_ARM_REG_SP), 4))[0]
            claims.append((r(A.UC_ARM_REG_R1), r(A.UC_ARM_REG_R2), kind))
            return ret(0)
        if n == 'claim_res':
            res.append((r(A.UC_ARM_REG_R1), r(A.UC_ARM_REG_R2)))
            return ret(0)
        if n == 'cave':
            v = cave[0]
            cave[0] += (r(A.UC_ARM_REG_R1) + 7) & ~7
            return ret(v)
        if n == 'self':
            return ret(0xC7F00000)
        return ret(0)
    mu.hook_add(UC_HOOK_CODE, hook, begin=SVC + 0x100, end=SVC + 0x200)
    mu.reg_write(A.UC_ARM_REG_R0, BLOCK)
    mu.reg_write(A.UC_ARM_REG_R1, SVC)
    mu.reg_write(A.UC_ARM_REG_R2, 0xC7F00000)
    mu.reg_write(A.UC_ARM_REG_SP, STACK)
    mu.reg_write(A.UC_ARM_REG_LR, STOP)
    mu.reg_write(A.UC_ARM_REG_C1_C0_2, 0x00F00000)
    mu.reg_write(A.UC_ARM_REG_FPEXC, 0x40000000)
    try:
        mu.emu_start(BLOCK + hdr[4], STOP, count=budget)
        if mu.reg_read(A.UC_ARM_REG_PC) != STOP:
            status[0] = f'partial (budget, pc={mu.reg_read(A.UC_ARM_REG_PC):#x})'
    except UcError as e:
        status[0] = f'partial ({e}, pc={mu.reg_read(A.UC_ARM_REG_PC):#x})'
    return (claims, res), status[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', type=pathlib.Path)
    a = ap.parse_args()
    addrs = our_addresses()
    lo, hi = min(addrs) - 0x40, max(addrs) + 0x40
    span = (0xC2EB3F5C - 0x40, 0xC2EB3F94 + 0x40)
    rows = []
    hit = 0
    by_id = collections.OrderedDict()
    for p, kind, d in files():
        sup_id = d[20:24].decode('latin1') if kind == 'v3' else 'VBIN'
        exact, near = static(d, set(addrs), *span)
        dyn, st = dynamic(d) if kind == 'v3' else (None, 'static only')
        overl = []
        if dyn:
            for ca, cl, ck in dyn[0]:
                overl += [f'{x:#x}' for x in addrs if ca < x + 4 and x < ca + cl]
        row = {'file': str(p.relative_to(ROOT)), 'kind': kind, 'id': sup_id,
               'static_exact': [f'{x:#x}' for x in exact], 'static_near_spantable': [f'{x:#x}' for x in near],
               'claims': len(dyn[0]) if dyn else None, 'claim_overlap': overl, 'run': st}
        rows.append(row)
        if exact or overl:
            hit += 1
        by_id.setdefault(sup_id, []).append(row)
    for sid, rs in by_id.items():
        bad = [r for r in rs if r['static_exact'] or r['claim_overlap']]
        runs = collections.Counter(r['run'].split(' ')[0] for r in rs)
        print(f'{sid:6s} {len(rs):3d} files  conflicts {len(bad)}  runs {dict(runs)}'
              + (f'  e.g. {bad[0]["file"]} {bad[0]["static_exact"] + bad[0]["claim_overlap"]}' if bad else ''))
    print(f'{len(rows)} files, {hit} touch our words')
    if a.json:
        a.json.write_text(json.dumps(rows, indent=1))
    return 1 if hit else 0


if __name__ == '__main__':
    sys.exit(main())
