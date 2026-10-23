#!/usr/bin/env python3
"""lz4fast inside the sup: real .xci icons through the real frame decoder
C05A7E50, whose bl at C05A7EE0 the sup's entry has pointed at its veneer ->
gate pf_g_lz0 -> lz_block (pf_lz on) or stock C05A7630 (pf_lz off / master off).

The reference runs in a separate unicorn instance (lz4fast/test_lz4fast.py's
stock Rig): unicorn keeps already-translated blocks after a code write, so
stock and patched never share an instance.  Our instance is patched by the
sup's own entry before anything is translated.

    python3 -B test_perf_lz.py [N]          (N icons, default 60)
"""
import pathlib, sys
from unicorn import UC_HOOK_CODE

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / 'lz4fast'))
import build_perf as P                    # noqa: E402
import test_perf_render as R         # noqa: E402
import test_lz4fast as L             # noqa: E402


def ours(sw, ents, blob, sym, info):
    g = R.Rig(blob, sym, info, sw)
    for base, size in ((L.OUT, 0x1000000), (L.STACK - 0x100000, 0x100000)):
        g.mu.mem_map(base, size)
    lo = R.BLOCK + 32 + sym['lz_mod'] if 'lz_mod' in sym else None
    hits = [0]
    g.mu.hook_add(UC_HOOK_CODE, lambda mu, a, s, _: hits.__setitem__(0, hits[0] + 1),
                  begin=lo, end=lo + 0x400)

    class Shim:                      # the call interface run_icon expects
        mu = g.mu
        patched = True

        def call(self, fn, args, stack_args=(), count=False):
            mu = g.mu
            sp = L.STACK - 0x1000
            mu.mem_write(sp, b''.join(a.to_bytes(4, 'little') for a in stack_args))
            from unicorn import arm_const as A
            for i, a in enumerate(args):
                mu.reg_write(A.UC_ARM_REG_R0 + i, a)
            seed = [0x11110000 + i for i in range(8)]
            for i, v in enumerate(seed):
                mu.reg_write(A.UC_ARM_REG_R4 + i, v)
            mu.reg_write(A.UC_ARM_REG_SP, sp)
            mu.reg_write(A.UC_ARM_REG_LR, R.STOP)
            mu.emu_start(fn, R.STOP, count=2_000_000_000)
            ok = [mu.reg_read(A.UC_ARM_REG_R4 + i) for i in range(8)] == seed and \
                mu.reg_read(A.UC_ARM_REG_SP) == sp
            return mu.reg_read(A.UC_ARM_REG_R0), ok, True
    shim = Shim()
    return [L.run_icon(shim, e) for e in ents], hits[0]


def main(n=60, **build_kw):
    import os
    build_kw.setdefault('without', {x for x in os.environ.get('PERF_WITHOUT', '').split(',') if x})
    blob, info, sym = P.build(set(), 1, **build_kw)
    if not info['lz4fast']:
        print('lz4fast not built in; nothing to test')
        return 0
    stock = L.Rig(patched=False)
    ents = L.xci_entries(stock.img)
    step = max(1, len(ents) // n)
    ents = ents[::step][:n]
    ref = [L.run_icon(stock, e) for e in ents]
    fails = 0
    for sw, want_fast in ((dict(master=1, lz=1), True), (dict(master=1, lz=0), False),
                          (dict(master=0, lz=1), False)):
        got, hits = ours(sw, ents, blob, sym, info)
        bad = sum(1 for a, b in zip(ref, got) if a[0] != b[0] or a[1] != b[1] or not b[2])
        path_ok = bool(hits) == want_fast
        print(f'{"ok " if not bad and path_ok else "BAD"} {sw}: {len(ents)} icons, {bad} differ, '
              f'lz4fast instructions {hits}')
        fails += bad + (not path_ok)
    return fails


if __name__ == '__main__':
    sys.exit(1 if main(int(sys.argv[1]) if len(sys.argv) > 1 else 60) else 0)
