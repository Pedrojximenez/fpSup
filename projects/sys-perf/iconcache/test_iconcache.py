"""iconcache vs stock, on the real image in unicorn.

    python3 -B test_iconcache.py            # all 2005 icons + scenarios
    python3 -B test_iconcache.py --quick    # 300 icons
    python3 -B test_iconcache.py --mutate   # every mutation must fail

Each icon load runs the real C0601F98 LZ4 path from C0602184 (ctype 2 chosen)
to C060235E (after ldr.w fp,[sp,#0x48]) in two separate unicorn instances
(unicorn keeps translated blocks across mem_write, so stock and patched never
share one):  stock (image untouched) and patched (b.w at C060219C/C060234C to
veneers in the cave arena, iconcache.bin loaded, EN set).  Compared: fp, the
whole decoded buffer, r4-r7, sl, sp, and the stack frame (on a hit the LZ4
scratch words 0x44 and 0x70..0x9F are not written, so they are excluded there).
"""
import pathlib, struct, sys
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_HOOK_CODE
from unicorn import arm_const as A

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'fpSup' / 'fp_usb_shell'))
sys.path.insert(0, str(HERE))
from armasm import assemble, symbols  # noqa: E402
import build  # noqa: E402

B = 0xC0000000
IMG = (ROOT / 'out' / 'seg0_c0000000.bin').read_bytes()[:0x02F00000]
START, STOP = 0xC0602184, 0xC060235E
DECODE = (0xC06021A2, 0xC060234C)     # the stock decode body (counted)
VEN1, VEN2 = 0xC072E100, 0xC072E108
CODE, ARENA = 0x46000000, 0x48000000
STK, HEAP, MEMIF, STUB = 0x47000000, 0x50000000, 0x4A000000, 0x4B000000
SCRATCH = {0x44} | set(range(0x70, 0xA0, 4))
C = build.CTL


def icons():
    out = []
    i = IMG.find(b'XC\x00\x00', 0x1240000)
    while 0 <= i < 0x1600000:
        csz, w, h = struct.unpack_from('<IHH', IMG, i + 4)
        if w and h and w <= 2048 and h <= 2048 and csz < 4_000_000 and IMG[i + 0x11] == 2:
            out.append((B + i, csz, w, h, IMG[i + 0xD]))
        i = IMG.find(b'XC\x00\x00', i + 4)
    return out


class Rig:
    def __init__(self, patched, src_text=None, arena=8 << 20, maxent=0x80000, en=1):
        mu = self.mu = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
        mu.ctl_set_cpu_model(A.UC_CPU_ARM_CORTEX_A7)
        mu.mem_map(B, 0x02F00000)
        mu.mem_write(B, IMG)
        for b, s in ((STK - 0x100000, 0x100000), (HEAP, 0x2000000), (MEMIF, 0x10000),
                     (STUB, 0x10000), (CODE, 0x10000), (ARENA, 0x1000000)):
            mu.mem_map(b, s)
        mu.mem_write(STUB, struct.pack('<H', 0x4770))
        mu.mem_write(MEMIF, struct.pack('<II', STUB | 1, STUB | 1))
        mu.mem_write(MEMIF + 0x34, struct.pack('<I', 0xAD))
        self.patched = patched
        self.fail_next_alloc = False
        self.allocs = []
        if patched:
            src = HERE / 'iconcache.S'
            if src_text is not None:
                src = HERE / '_mut.S'
                src.write_text(src_text)
            code, sym = assemble(src), symbols(src)
            mu.mem_write(CODE, code)
            mu.mem_write(VEN1, build.veneer(CODE + sym['ic_h1']))
            mu.mem_write(VEN2, build.veneer(CODE + sym['ic_h2']))
            for name, site, *_ in build.SITES:
                mu.mem_write(site, struct.pack('<I', build.thumb_bw(site, VEN1 if name == 'h1' else VEN2)))
            self.w(C['enable'], en)
            self.w(C['arena'], ARENA)
            self.w(C['arena_size'], arena)
            self.w(C['max_entry'], maxent)
        self.decode_insns = 0

        def alloc(uc, addr, size, user):
            if addr == STUB:
                n = uc.reg_read(A.UC_ARM_REG_R0)
                self.allocs.append((n, uc.reg_read(A.UC_ARM_REG_R1)))
                uc.reg_write(A.UC_ARM_REG_R0, 0 if self.fail_next_alloc else HEAP)
                self.fail_next_alloc = False
        mu.hook_add(UC_HOOK_CODE, alloc, begin=STUB, end=STUB + 2)

        def cnt(uc, addr, size, user):
            self.decode_insns += 1
        mu.hook_add(UC_HOOK_CODE, cnt, begin=DECODE[0], end=DECODE[1] - 1)

    def w(self, off, v):
        self.mu.mem_write(CODE + off, struct.pack('<I', v))

    def r(self, off):
        return struct.unpack('<I', bytes(self.mu.mem_read(CODE + off, 4)))[0]

    def stats(self):
        return {k: self.r(C[k]) for k in ('hits', 'misses', 'inserts', 'evicts', 'skips', 'alloc_fail', 'rejects')}

    def load(self, ent, hdr_patch=None):
        """One image-node load of `ent`.  Returns (fp, buffer bytes, regs, frame)."""
        addr, csz, w, h, bpp = ent
        mu = self.mu
        S = STK - 0x4000
        hdr = bytearray(IMG[addr - B:addr - B + 0x20])
        if hdr_patch:
            hdr_patch(hdr)
        hw, hh = struct.unpack_from('<HH', hdr, 8)
        size = hw * hh * (2 if bpp == 4 else 4)
        frame = bytearray(0x128)
        for off, v in ((0x30, hw), (0x38, hh), (0x40, 0x9101), (0x44, csz + 0x20), (0x48, 0x1000),
                       (0x08, 0x4A001000), (0x0C, MEMIF), (0x58, 0x4A004000), (0xF0, csz + 0x20),
                       (0xF4, addr), (0x100, MEMIF)):
            struct.pack_into('<I', frame, off, v)
        frame[0xB0:0xD0] = hdr
        mu.mem_write(S, bytes(frame))
        mu.mem_write(HEAP, bytes(size + 64))
        regs = dict(R0=0, R1=addr + 0x20, R2=hw, R3=hh, R4=0, R5=0x4A001000, R6=MEMIF, R7=0x4A002000,
                    R8=0x4A004000, R9=addr + 0x20, R10=0x4A003000, R11=size, R12=2, LR=0x11)
        for k, v in regs.items():
            mu.reg_write(getattr(A, 'UC_ARM_REG_' + k), v)
        mu.reg_write(A.UC_ARM_REG_SP, S)
        self.decode_insns = 0
        self.allocs = []
        mu.emu_start(START | 1, STOP, count=500_000_000)
        fp = mu.reg_read(A.UC_ARM_REG_R11)
        buf = bytes(mu.mem_read(fp, size)) if fp else b''
        keep = tuple(mu.reg_read(getattr(A, 'UC_ARM_REG_' + k)) for k in ('R4', 'R5', 'R6', 'R7', 'R10', 'SP'))
        fr = bytes(mu.mem_read(S, 0x128))
        return fp, buf, keep + tuple(self.allocs), fr, size


def same(a, b, hit):
    fa, ba, ka, ra, _ = a
    fb, bb, kb, rb, _ = b
    if fa != fb or ba != bb or ka != kb:
        return False
    for off in range(0, 0x128, 4):
        if hit and off in SCRATCH:
            continue
        if ra[off:off + 4] != rb[off:off + 4]:
            return False
    return True


def check(cond, msg, fails):
    if not cond:
        fails.append(msg)
    return cond


# ------------------------------------------------------------------ scenarios
def t_icons(stock, pat, ents, fails):
    """pass 1: all misses (inserted when they fit); pass 2 (reverse order): hits equal stock and skip decode."""
    ref = {}
    for e in ents:
        ref[e[0]] = stock.load(e)
    s0 = pat.stats()
    for e in ents:
        got = pat.load(e)
        if not same(ref[e[0]], got, hit=False):
            fails.append(f'icons pass1 {e[0]:#x} differs'); return
    s1 = pat.stats()
    hits = 0
    for e in reversed(ents):            # most recent first: same order would be LRU's worst case
        got = pat.load(e)
        hit = pat.decode_insns == 0
        hits += hit
        if not same(ref[e[0]], got, hit=hit):
            fails.append(f'icons pass2 {e[0]:#x} differs (hit={hit})'); return
    s2 = pat.stats()
    check(s1['misses'] - s0['misses'] == len(ents), f'pass1 misses {s1} {s0}', fails)
    check(s2['hits'] - s1['hits'] == hits and hits > 0, f'pass2 hits {hits} vs {s2["hits"] - s1["hits"]}', fails)
    print(f'  icons: {len(ents)} x2, pass2 hits {hits}, inserts {s2["inserts"]}, evicts {s2["evicts"]}, '
          f'skips {s2["skips"]}')


def t_lru(ents, fails, src_text=None):
    same_sz = {}
    for e in ents:
        same_sz.setdefault(e[2] * e[3], []).append(e)
    grp = next(v for k, v in sorted(same_sz.items()) if len(v) >= 4 and k * 2 >= 4096)
    a, b, c, d = grp[:4]
    size = a[2] * a[3] * 2
    slot = (size + 7) & ~7
    stock = Rig(False)
    pat = Rig(True, src_text, arena=slot * 3)
    ref = {e[0]: stock.load(e) for e in (a, b, c, d)}
    seq = [(a, 0), (b, 0), (c, 0), (a, 1), (d, 0), (a, 1), (c, 1), (b, 0)]
    for e, want_hit in seq:
        got = pat.load(e)
        hit = pat.decode_insns == 0
        if not check(hit == bool(want_hit), f'lru {e[0]:#x} hit={hit} want {want_hit} {pat.stats()}', fails):
            return
        check(same(ref[e[0]], got, hit), f'lru {e[0]:#x} differs', fails)
    st = pat.stats()
    check(st['evicts'] == 2, f'lru evicts {st}', fails)
    # every entry hit once (pinned and released), then the oldest-hit one must be evictable
    pat = Rig(True, src_text, arena=slot * 3)
    for e, want_hit in [(a, 0), (b, 0), (c, 0), (a, 1), (b, 1), (c, 1), (d, 0), (a, 0), (c, 1)]:
        got = pat.load(e)
        hit = pat.decode_insns == 0
        if not check(hit == bool(want_hit), f'lru2 {e[0]:#x} hit={hit} want {want_hit} {pat.stats()}', fails):
            return
        check(same(ref[e[0]], got, hit), f'lru2 {e[0]:#x} differs', fails)
    print(f'  lru: ok {st}')


def t_disabled(ents, fails, src_text=None):
    stock, pat = Rig(False), Rig(True, src_text, en=0)
    for e in ents[:20] * 2:
        check(same(stock.load(e), pat.load(e), False), f'en=0 {e[0]:#x} differs', fails)
    st = pat.stats()
    check(all(v == 0 for v in st.values()), f'en=0 touched counters {st}', fails)
    print(f'  disabled: ok')


def t_alloc_fail(ents, fails, src_text=None):
    pat = Rig(True, src_text)
    e = ents[5]
    pat.load(e)
    pat.fail_next_alloc = True
    fp, buf, keep, fr, size = pat.load(e)
    check(fp == 0 and struct.unpack_from('<I', fr, 0x48)[0] == 0, 'alloc fail: fp/[0x48] not 0', fails)
    check(pat.stats()['alloc_fail'] == 1, f'alloc fail counter {pat.stats()}', fails)
    print('  alloc fail on hit: fp=0 -> stock error path')


def t_content(ents, fails, src_text=None):
    """Same address, different compressed bytes (a resource rewritten in RAM): must miss."""
    e = ents[7]
    addr, csz = e[0], e[1]
    stock, pat = Rig(False), Rig(True, src_text)
    pat.load(e)
    tail = addr + 0x20 + csz - 4                       # end mark / checksum word: not decoded
    for rig in (stock, pat):
        old = bytes(rig.mu.mem_read(tail, 4))
        rig.mu.mem_write(tail, bytes(x ^ 0x5A for x in old))
    ref = stock.load(e)
    got = pat.load(e)
    check(pat.decode_insns > 0, 'content change: was a hit', fails)
    check(same(ref, got, False), 'content change: differs', fails)
    print('  content change at the same address: miss, equal')


def t_big(ents, fails, src_text=None):
    big = max(ents, key=lambda e: e[2] * e[3])
    stock, pat = Rig(False), Rig(True, src_text, maxent=0x1000)
    for _ in range(2):
        check(same(stock.load(big), pat.load(big), False), 'big differs', fails)
        check(pat.decode_insns > 0, 'big was cached', fails)
    check(pat.stats()['skips'] == 2 and pat.stats()['inserts'] == 0, f'big {pat.stats()}', fails)
    print('  larger than max_entry: never cached')


def t_short(ents, fails, src_text=None):
    """Decoder writes fewer bytes than the buffer (header says one row more): reject, not cached."""
    e = ents[3]
    def taller(h):
        struct.pack_into('<H', h, 10, struct.unpack_from('<H', h, 10)[0] + 1)
    stock, pat = Rig(False), Rig(True, src_text)
    for _ in range(2):
        a = stock.load(e, taller)
        b = pat.load(e, taller)
        n = e[2] * e[3] * 2
        check(a[0] == b[0] and a[1][:n] == b[1][:n] and a[2] == b[2], 'short differs', fails)
        check(pat.decode_insns > 0, 'short was a hit', fails)
    check(pat.stats()['rejects'] == 2 and pat.stats()['inserts'] == 0, f'short {pat.stats()}', fails)
    print('  short decode: rejected, not cached')


def run_all(ents, src_text=None, quiet=False):
    fails = []
    stock = Rig(False)
    pat = Rig(True, src_text, arena=4 << 20)
    try:
        t_icons(stock, pat, ents, fails)
    except Exception as ex:              # a mutation may crash the emulation
        fails.append(f't_icons: {type(ex).__name__} {ex}')
    for t in (t_lru, t_disabled, t_alloc_fail, t_content, t_big, t_short):
        try:
            t(ents, fails, src_text)
        except Exception as ex:          # a mutation may crash the emulation
            fails.append(f'{t.__name__}: {type(ex).__name__} {ex}')
    return fails


MUTATIONS = [
    ('hit skips memcpy', '        ldr     ip, L_memcpy\n        blx     ip\n3:', '        nop\n        nop\n3:'),
    ('lookup ignores hash', '        cmp     r2, r7\n        bne     2f', '        cmp     r2, r2\n        bne     2f'),
    ('h2 ignores decoded length', '        ldr     r0, [r8, #F_OPOS]\n        cmp     r0, r5\n        bne     h2_rej',
     '        ldr     r0, [r8, #F_OPOS]\n        cmp     r0, r0\n        bne     h2_rej'),
    ('fits ignores overlap', '        cmp     r3, r2                  @ c < e.off+e.size ?\n        blo     11f',
     '        cmp     r3, r2                  @ c < e.off+e.size ?\n        nop'),
    ('evicts most recent', '        movlo   r3, ip\n        movlo   r2, r0', '        movhi   r3, ip\n        movhi   r2, r0'),
    ('hit does not set [sp+0x48]', '        str     r7, [r8, #F_BUF]', '        nop'),
    ('h1 miss forgets mov r0,fp', '        mov     r0, r11\n        ldr     ip, L_h1_ret', '        nop\n        ldr     ip, L_h1_ret'),
    ('h2 forgets str [sp,#0x90]', '        str     r2, [sp, #0x90]\n        ldr     r1, L_h2_ret', '        nop\n        ldr     r1, L_h2_ret'),
    ('pins never released', '        sub     r2, r2, #1\n        str     r2, [r9, #E_PINS]', '        nop\n        str     r2, [r9, #E_PINS]'),
    ('enable ignored in h1', '        ldr     r0, [r10, #EN]\n        cmp     r0, #0\n        beq     h1_stock',
     '        ldr     r0, [r10, #EN]\n        cmp     r0, r0\n        bne     h1_stock'),
]


def main():
    ents = icons()
    if '--mutate' in sys.argv:
        base = (HERE / 'iconcache.S').read_text()
        sub = ents[:120]
        bad = 0
        try:
            for name, old, new in MUTATIONS:
                assert base.count(old) == 1, name
                f = run_all(sub, base.replace(old, new))
                ok = bool(f)
                bad += not ok
                print(f'{"caught " if ok else "MISSED "} {name}: {f[0] if f else ""}')
        finally:
            (HERE / '_mut.S').unlink(missing_ok=True)
        print(f'mutations caught {len(MUTATIONS) - bad}/{len(MUTATIONS)}')
        sys.exit(1 if bad else 0)
    if '--quick' in sys.argv:
        ents = ents[:300]
    fails = run_all(ents)
    for f in fails:
        print('FAIL', f)
    print('PASS' if not fails else f'{len(fails)} failures')
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
