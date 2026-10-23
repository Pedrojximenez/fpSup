"""Bit-exactness tests: stock LZ4 block decoder C05A7630 vs lz4fast.S, both run
in unicorn on the real firmware image (out/seg0_c0000000.bin).

    python3 -B test_lz4fast.py            # everything + instruction counts
    python3 -B test_lz4fast.py --quick    # 200 icons instead of all
    python3 -B test_lz4fast.py --mutate   # every mutation must fail a case

1. Icons: every .xci in the image is decoded through the real outer frame
   decoder C05A7E50 twice -- once stock, once with the bl at C05A7EE0 pointed
   at a veneer in the cave arena (exactly how it is deployed).  Return value
   and the output buffer with 256-byte guards must match byte for byte.
2. Synthetic: hand-built token streams through a direct call of the block
   decoder (stock vs replacement): overlapping matches at offset 0..17, long
   extended lengths, FLG bit 0x10, truncated blocks (reading guard bytes),
   in->base above in->cur, in-place output overlapping the input, offsets
   that reach before the output start.  Compared: whole input+output arena,
   both stream structs, r0, r4-r11, sp.
"""
import json, pathlib, random, struct, sys
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn import arm_const as A

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'fpSup' / 'fp_usb_shell'))
from armasm import assemble, symbols  # noqa: E402

SEG0 = ROOT / 'out' / 'seg0_c0000000.bin'
SRC = HERE / 'lz4fast.S'
B = 0xC0000000
STOCK_FN = 0xC05A7630
OUTER = 0xC05A7E50
SITE = 0xC05A7EE0
VENEER = 0xC072E100          # inside the cave arena C072E064..C072EFB4
CODE = 0x46000000
STOP = 0x45F00000
STACK = 0x47000000
ARENA = 0x48000000           # synthetic in/out arena (4 MiB)
OUT = 0x50000000             # icon output (16 MiB)
STRM = 0x4A000000            # stream structs / FLG word
GUARD = 256


def bl(at, to):
    return 0xEB000000 | (((to - at - 8) >> 2) & 0xFFFFFF)


class Rig:
    def __init__(self, defines=(), counting=False, patched=False):
        self.code = assemble(SRC, defines)
        self.sym = symbols(SRC, defines)
        self.img = SEG0.read_bytes()[:0x02F00000]
        mu = self.mu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        mu.ctl_set_cpu_model(A.UC_CPU_ARM_CORTEX_A7)
        mu.mem_map(B, 0x02F00000)
        mu.mem_write(B, self.img)
        for base, size in ((CODE, 0x100000), (STOP, 0x100000), (STACK - 0x100000, 0x100000),
                           (ARENA, 0x400000), (OUT, 0x1000000), (STRM, 0x100000)):
            mu.mem_map(base, size)
        mu.mem_write(CODE, self.code)
        mu.mem_write(STOP, struct.pack('<I', 0xEAFFFFFE))
        self.entry = CODE + self.sym['lz_block']
        mu.mem_write(VENEER, struct.pack('<II', 0xE51FF004, self.entry))
        # The call site is written once, before anything is translated: unicorn
        # does not drop already-translated blocks on mem_write, so patching it
        # later would silently keep running the stock call.
        self.patched = patched
        mu.mem_write(SITE, struct.pack('<I', bl(SITE, VENEER) if patched else bl(SITE, STOCK_FN)))
        self.count = 0
        if counting:
            def hk(uc, addr, size, user):
                self.count += 1
            mu.hook_add(UC_HOOK_CODE, hk)

    def call(self, fn, args, stack_args=(), count=False):
        mu = self.mu
        sp = STACK - 0x1000
        if stack_args:
            mu.mem_write(sp, b''.join(struct.pack('<I', a) for a in stack_args))
        for i, a in enumerate(args):
            mu.reg_write(A.UC_ARM_REG_R0 + i, a)
        seed = [0x11110000 + i for i in range(4, 12)]
        for i, v in enumerate(seed):
            mu.reg_write(A.UC_ARM_REG_R4 + i, v)
        mu.reg_write(A.UC_ARM_REG_SP, sp)
        mu.reg_write(A.UC_ARM_REG_LR, STOP)
        self.count = 0
        mu.emu_start(fn, STOP, count=2_000_000_000)
        regs = [mu.reg_read(A.UC_ARM_REG_R4 + i) for i in range(8)]
        return (mu.reg_read(A.UC_ARM_REG_R0), regs == seed,
                mu.reg_read(A.UC_ARM_REG_SP) == sp)


def xci_entries(img):
    ents = []
    o = 0x1240000
    i = img.find(b'XC\x00\x00', o)
    while 0 <= i < 0x1600000:
        csz, w, h = struct.unpack_from('<IHH', img, i + 4)
        if w and h and w <= 2048 and h <= 2048 and csz < 4_000_000 \
                and struct.unpack_from('<I', img, i + 0x20)[0] == 0x184D2204:
            ents.append((B + i, csz, w, h))
        i = img.find(b'XC\x00\x00', i + 4)
    return ents


# --------------------------------------------------------------------------- icons
def run_icon(rig, ent, count=False):
    addr, csz, w, h = ent
    mu = rig.mu
    n = w * h * 4 + 2 * GUARD + 0x10000
    pat = bytes((i * 37 + 11) & 0xFF for i in range(n))
    mu.mem_write(OUT, pat)
    r0, regs_ok, sp_ok = rig.call(OUTER, (0, addr + 0x20, csz, OUT + GUARD), (w * h * 2,), count)
    return r0, bytes(mu.mem_read(OUT, n)), regs_ok and sp_ok


def test_icons(stock, fast, ents, verbose=True):
    assert not stock.patched and fast.patched
    bad = 0
    for e in ents:
        a = run_icon(stock, e)
        try:
            b = run_icon(fast, e)
        except Exception as ex:  # noqa: BLE001  a faulting replacement is a mismatch
            b = (None, repr(ex), False)
        if a[0] != b[0] or a[1] != b[1] or not b[2]:
            bad += 1
            if verbose and bad <= 5:
                diff = next((i for i in range(len(a[1])) if a[1][i] != b[1][i]), None)
                print(f'  icon {e[0]:#x} {e[2]}x{e[3]}: r0 {a[0]:#x}/{b[0]:#x} first diff {diff} regs {b[2]}')
    return bad


# --------------------------------------------------------------------------- synthetic
def ext(n):
    """bytes that extend a nibble of 15 to n (n >= 15)"""
    out = bytearray()
    n -= 15
    while n >= 255:
        out.append(255)
        n -= 255
    out.append(n)
    return bytes(out)


def seq(lit, off=None, mlen=None):
    """one LZ4 sequence; off=None means last (literals only)"""
    L = len(lit)
    tok_l = min(L, 15)
    if off is None:
        tok = tok_l << 4
        return bytes([tok]) + (ext(L) if L >= 15 else b'') + lit
    M = mlen - 4
    tok = tok_l << 4 | min(M, 15)
    return (bytes([tok]) + (ext(L) if L >= 15 else b'') + lit + struct.pack('<H', off)
            + (ext(M) if M >= 15 else b''))


def make_cases(rng):
    cases = []
    lit = lambda n: bytes(rng.randrange(256) for _ in range(n))
    # overlapping matches, every small offset, many lengths
    for off in list(range(1, 18)) + [31, 32, 33, 64, 255, 256, 4096]:
        for m in (4, 5, 7, 8, 15, 16, 17, 18, 19, 20, 31, 33, 64, 100, 270, 271, 600):
            pre = lit(max(off, 1) + rng.randrange(0, 5))
            body = seq(pre, off, m) + seq(lit(rng.randrange(0, 20)))
            cases.append(dict(name=f'off{off}_m{m}', blk=body))
    # long literal runs with extension bytes
    for L in (0, 1, 14, 15, 16, 17, 31, 269, 270, 271, 524, 525, 1000):
        body = seq(lit(L), 1, 4) + seq(lit(L))
        cases.append(dict(name=f'lit{L}', blk=body))
    # random valid-ish streams
    for i in range(300):
        parts = []
        produced = 0
        for _ in range(rng.randrange(1, 12)):
            L = rng.choice([0, 1, 2, 3, 5, 15, 16, 40, 300])
            parts.append(lit(L))
            produced += L
            if produced == 0:
                continue
            off = rng.choice([1, 2, 3, 4, 7, 15, 16, rng.randrange(1, produced + 1)])
            off = min(off, produced)
            m = rng.choice([4, 5, 9, 15, 18, 19, 30, 70, 300, 1000])
            parts[-1] = seq(parts[-1], off, m)
            produced += m
        parts.append(seq(lit(rng.randrange(0, 30))))
        cases.append(dict(name=f'rand{i}', blk=b''.join(parts)))
    # offset 0 and offsets reaching before the output start (corrupt but bounded)
    cases.append(dict(name='off0', blk=seq(lit(3), 0, 9) + seq(lit(2))))
    cases.append(dict(name='off_before_out', blk=seq(lit(2), 40, 30) + seq(b'')))
    # FLG bit 0x10 (block checksum word follows the block)
    for base in cases[:40:7]:
        cases.append(dict(name=base['name'] + '_flg10', blk=base['blk'], flg=0x10 | 0x60))
    # truncated / lying block sizes: the decoder runs into the guard bytes
    for i in range(30):
        c = rng.choice(cases[:200])
        cut = rng.randrange(1, max(2, len(c['blk'])))
        cases.append(dict(name=f'trunc{i}', blk=c['blk'][:cut], bs=len(c['blk'])))
    for i in range(20):
        c = rng.choice(cases[:200])
        cases.append(dict(name=f'short_bs{i}', blk=c['blk'], bs=rng.randrange(0, len(c['blk']) + 1)))
    # in->base above in->cur (abs() branch of C04D1408)
    for i in range(10):
        c = rng.choice(cases[:200])
        cases.append(dict(name=f'base_hi{i}', blk=c['blk'], base_delta=rng.choice([1, 7, 1000])))
    # output overlapping the input (in place)
    for i, delta in enumerate((-64, -3, -1, 1, 3, 5, 9, 15, 16, 40)):
        c = rng.choice(cases[:200])
        cases.append(dict(name=f'inplace{delta}', blk=c['blk'], out_delta=delta))
    return cases


IN_OFF = 0x200001            # odd: unaligned token/length reads like the real frames
OUT_OFF = 0x100003
ARENA_FILL = bytes((i * 131 + 7) & 0xFF for i in range(0x400000))


def run_synth(rig, case, fn):
    mu = rig.mu
    blk = case['blk']
    bs = case.get('bs', len(blk))
    mu.mem_write(ARENA, ARENA_FILL)
    src = ARENA + IN_OFF
    # guard after the block is zero so lying sizes decode zero tokens (bounded)
    mu.mem_write(src, struct.pack('<I', bs) + blk + bytes(0x800) + struct.pack('<I', 0xDEADBEEF))
    out = ARENA + OUT_OFF
    if 'out_delta' in case:
        out = src + 4 + case['out_delta']
    base = src - 0x10 if 'base_delta' not in case else src + case['base_delta'] + 4
    instream = STRM + 0x100
    outstream = STRM + 0x200
    flg = STRM + 0x300
    mu.mem_write(instream, struct.pack('<III', base, src, 0x12345))
    mu.mem_write(outstream, struct.pack('<III', out - 0x20, out, 0x54321))
    mu.mem_write(flg, struct.pack('<I', case.get('flg', 0x60)))
    r0, regs_ok, sp_ok = rig.call(fn, (STRM, outstream, instream, flg))
    return (r0, regs_ok, sp_ok, bytes(mu.mem_read(ARENA, 0x400000)),
            bytes(mu.mem_read(STRM, 0x400)))


def test_synth(rig, cases, verbose=True):
    bad = 0
    for c in cases:
        try:
            a = run_synth(rig, c, STOCK_FN)
        except Exception as e:  # noqa: BLE001  stock itself faults: skip, not a case
            c['skip'] = repr(e)
            continue
        try:
            b = run_synth(rig, c, rig.entry)
        except Exception as e:  # noqa: BLE001
            b = ('fault', repr(e))
        ok = (isinstance(b[0], int) and a[0] == b[0] and b[1] and b[2]
              and a[3] == b[3] and a[4] == b[4])
        if not ok:
            bad += 1
            if verbose and bad <= 5:
                print(f'  synth {c["name"]}: mismatch')
    return bad


def counts(ents):
    """instructions per output byte, stock vs fast, on a sample"""
    out = {}
    for on in (False, True):
        rig = Rig(counting=True, patched=on)
        ins = nbytes = 0
        for e in ents:
            run_icon(rig, e)
            ins += rig.count
            nbytes += decoded_len(rig)
        out['fast' if on else 'stock'] = (ins, nbytes)
    return out


def decoded_len(rig):
    # output stream lives in the outer decoder's frame: [sp] {base, cur, size}
    sp = STACK - 0x1000 - 0x58
    base, cur = struct.unpack('<II', rig.mu.mem_read(sp, 8))
    return cur - base


MUTATIONS = ['MUT_PHASE', 'MUT_EXT', 'MUT_POS', 'MUT_FLAG', 'MUT_TAIL', 'MUT_M4',
             'MUT_D16', 'MUT_LITADV']


def main():
    quick = '--quick' in sys.argv
    rng = random.Random(1)
    rig = Rig()
    fast = Rig(patched=True)
    ents = xci_entries(rig.img)
    cases = make_cases(random.Random(2))
    if '--mutate' in sys.argv:
        sample = rng.sample(ents, 60)
        caught = 0
        for m in MUTATIONS:
            r = Rig((m,), patched=True)
            fails = test_synth(r, cases, verbose=False) + test_icons(rig, r, sample, verbose=False)
            print(f'{m:12s} {"caught" if fails else "NOT CAUGHT"} ({fails} failing cases)')
            caught += bool(fails)
        print(f'mutations caught {caught}/{len(MUTATIONS)}')
        return 0 if caught == len(MUTATIONS) else 1
    sel = rng.sample(ents, 200) if quick else ents
    bad_s = test_synth(rig, cases)
    skipped = sum(1 for c in cases if 'skip' in c)
    print(f'synthetic: {len(cases) - skipped} cases, {bad_s} mismatches ({skipped} skipped: stock faults)')
    calls0 = struct.unpack('<I', fast.mu.mem_read(CODE + 4, 4))[0]
    bad_i = test_icons(rig, fast, sel)
    calls1 = struct.unpack('<I', fast.mu.mem_read(CODE + 4, 4))[0]
    assert calls1 - calls0 == len(sel), f'replacement ran {calls1 - calls0} times for {len(sel)} icons'
    print(f'icons: {len(sel)} of {len(ents)} decoded through C05A7E50, {bad_i} mismatches')
    sample = sorted(rng.sample(ents, 60), key=lambda e: e[0])
    big = sorted(ents, key=lambda e: -e[2] * e[3])[:3]
    c = counts(sample + big)
    for k, (ins, n) in c.items():
        print(f'{k:5s}: {ins:>11,} instructions (whole C05A7E50), {n:>9,} bytes out, {ins / n:.2f} / byte')
    json.dump({'icons': len(sel), 'icon_mismatch': bad_i, 'synthetic': len(cases) - skipped,
               'synthetic_mismatch': bad_s,
               'counts': {k: {'instructions': v[0], 'bytes': v[1]} for k, v in c.items()}},
              open(HERE / 'test_result.json', 'w'), indent=1)
    return 0 if not (bad_s or bad_i) else 1


if __name__ == '__main__':
    sys.exit(main())
