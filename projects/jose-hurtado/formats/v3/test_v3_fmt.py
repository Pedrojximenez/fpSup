"""Jose Hurtado's fpSup-Formats as a Loader v3 sup (31FMT.BIN), offline.

    cd projects/jose-hurtado/formats/v3 && python3 -B -m unittest test_v3_fmt
    FMT_VERSION=0.6.0 python3 -B -m unittest test_v3_fmt     # the older package

Two kinds of test, both in Unicorn against the reference image:

  loader   the real loader.S and LOADER.BIN load the built 31FMT.BIN (fpSup/
           fp_usb_shell/v3/test_v3.Camera: file, directory, allocator and
           power-off routines in Python): claims, journal, veneers, the
           firmware words that name a coordinate, power-off write-back,
           refusals next to other sups.
  twins    the same code in two worlds -- Jose's VBIN sections at his fixed
           addresses ("original"), and the block the loader built ("v3") --
           run the compositor and then every handler the layout has (every
           hook target and register-call root) on the same inputs.  Every
           call out to the firmware is a stub, the same in both; every memory
           write, every firmware call and every return is recorded with block
           addresses mapped back to Jose's coordinates.  The two records must
           be identical, and the v3 world must never touch a fixed coordinate.

This is the proof that the move kept the behaviour: there is no source, so it
cannot be "assemble twice and compare" as OG's is.  What it cannot tell: what
the firmware stubs would really have returned (both worlds get the same), and
paths no input here reaches.  Emulated, not on the camera.
"""
import json
import pathlib
import struct
import subprocess
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
PKG = HERE.parent
ROOT = PKG.parents[2]
V3 = ROOT / 'fpSup' / 'fp_usb_shell' / 'v3'
sys.path.insert(0, str(V3))
sys.path.insert(0, str(V3.parent))
sys.path.insert(0, str(PKG / 'tools'))

sys.path.insert(0, str(ROOT / 'fpSup' / 'uishare'))
import test_v3 as T                                        # noqa: E402
import build_v3 as BV                                      # noqa: E402
import fmt_layout as FL                                    # noqa: E402
from ui import chain                                       # noqa: E402

from unicorn import (Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE,  # noqa: E402
                     UC_HOOK_MEM_WRITE, UC_HOOK_MEM_READ)
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2,  # noqa: E402
                               UC_ARM_REG_R3, UC_ARM_REG_SP, UC_ARM_REG_LR,
                               UC_ARM_REG_PC, UC_ARM_REG_CPSR)

NAME = '31FMT.BIN'
TK_CRE, TK_STA = 0xC0016A58, 0xC0016BC0
THUMB_SITES = (0xC05E5B58, 0xC05E6400, 0xC05E84D8)
_BUILT = {}
STOCK = T.IMAGE.read_bytes() if T.IMAGE.exists() else b''


def built(formats=FL.FORMATS, src=HERE / 'build_v3_fmt.py'):
    key = (tuple(formats), str(src))
    if key not in _BUILT:
        with tempfile.TemporaryDirectory(prefix='fmtv3t-') as t:
            out = pathlib.Path(t) / 'o'
            r = subprocess.run([sys.executable, '-B', str(src), '--out', str(out),
                                '--formats', ','.join(formats)],
                               capture_output=True, text=True)
            if r.returncode:
                raise RuntimeError(r.stderr[-3000:])
            meta = json.loads((out / 'build.json').read_text())
            _BUILT[key] = ((out / NAME).read_bytes(), meta['facts'])
    return _BUILT[key]


def h(s):
    return int(s, 16)


class FmtCamera(T.Camera):
    """test_v3's camera, remembering where 31FMT.BIN's block landed and every
    access to Jose's fixed coordinates."""
    def __init__(self, files, dirs, block_size, **kw):
        super().__init__(files, dirs, **kw)
        self.block_size, self.block = block_size, None
        self.old = []
        for a, b in FL.PIECES:
            self.mu.hook_add(UC_HOOK_MEM_READ | UC_HOOK_MEM_WRITE, self._old, begin=a, end=b - 1)

    def _old(self, mu, access, addr, size, value, data):
        self.old.append((addr, self.r(UC_ARM_REG_PC)))

    def _alloc(self, n, align=8):
        p = super()._alloc(n, align)
        if n == self.block_size:
            self.block = p
        return p


# The native UI objects uishare's applier needs, as lossless's MenuCamera lays
# them out (fpSup/lossless/test_card_emulation.py), so 10LOSS's row and its
# string layer really go up next to ours.
GUI_OBJECT = 0xC37B7048
UI_AREA = 0xC3A00000
APP, SCREENS, SCREEN, READER, ENTRIES, NAMES, REGISTRY, DESCS = (
    UI_AREA + o for o in (0x0, 0x1000, 0x2000, 0x3000, 0x4000, 0x6000, 0x8000, 0x9000))
SCREEN_NAMES = ['MainB1', 'MainB2', 'MainY4']
ENTRY_OFFSETS = [0x74D796, 0x76FF04, 0x889C60]
REG_LOOKUP, REG_ADD = 0xC05DB418, 0xC05DB308
POOL, POOL_LEN = 0xC18C0474, 176152
RESOLVE, OWNS, REMAIN = (s for s, _, _ in chain.SITES.values())


class UICamera(FmtCamera):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        mu, w = self.mu, self.put
        self.vars = {}
        w(GUI_OBJECT, APP)
        w(APP + 0x80, len(SCREEN_NAMES)); w(APP + 0x8C, SCREENS); w(APP + 0x888, REGISTRY - 0x60)
        for i, (name, off) in enumerate(zip(SCREEN_NAMES, ENTRY_OFFSETS)):
            s, n = SCREEN + 0x40 * i, NAMES + 0x40 * i
            mu.mem_write(n, name.encode() + b'\0')
            w(SCREENS + 4 * i, s); w(s + 4, APP); w(s + 8, n); w(s + 0x24, READER)
            w(ENTRIES + 44 * i + 4, n); w(ENTRIES + 44 * i + 8, off)
        w(READER + 0x10, POOL_LEN); w(READER + 0x14, POOL); w(READER + 0x24, 0xC18C0460)
        w(READER + 0xA8, len(SCREEN_NAMES)); w(READER + 0xAC, ENTRIES)
        for a, nm in ((REG_LOOKUP, 'REG_LOOKUP'), (REG_ADD, 'REG_ADD')):
            mu.mem_write(a, struct.pack('<I', 0x47704770))      # Thumb bx lr
            self.by_addr[a] = nm

    def _hook(self, mu, addr, size, _):
        name = self.by_addr.get(addr)
        if name in ('REG_LOOKUP', 'REG_ADD'):
            r1, r2 = self.r(UC_ARM_REG_R1), self.r(UC_ARM_REG_R2)
            self.calls.append(name)
            if name == 'REG_LOOKUP':
                self.put(r2, self.vars.get(self.cstr(r1), 0))
                return self._ret(0)
            kind, nameptr, value = struct.unpack('<3I', mu.mem_read(r2, 12))
            d = DESCS + 32 * len(self.vars)
            mu.mem_write(d, struct.pack('<3I', kind, nameptr, value))
            self.vars[self.cstr(nameptr)] = d
            return self._ret(0)
        return super()._hook(mu, addr, size, _)

    def fw(self, fn, r1):
        return self.call(fn, r0=READER, r1=r1, sp=T.STACK - 0x1000, thumb=True)[0]


def lossless_sup():
    sys.path.insert(0, str(ROOT / 'fpSup' / 'lossless'))
    import build_v3_lossless as LS
    with tempfile.TemporaryDirectory(prefix='fmtl-') as t:
        return LS.sup_file(pathlib.Path(t))[0]


def thumb_target(site, word):
    return FL.thumb_bw(site, word)[1]


def arm_target(site, word):
    return FL.arm_branch(site, word)[1]


# ---------------------------------------------------------------------------
# The twins: one engine, two memories.

STACK, SCRATCH, DONE = 0x46000000, 0x48000000, 0x47000000
STEPS = 400_000


class World:
    """The image (as a booted camera left it, or stock plus Jose's sections),
    a stack, a scratch object; code runs until it leaves its layout."""
    def __init__(self, image, layout, to_coord):
        self.layout, self.to_coord = layout, to_coord      # [(lo, hi)], addr -> coord
        mu = self.mu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        mu.mem_map(0xC0000000, 0x04000000)
        mu.mem_write(0xC0000000, image)
        mu.mem_map(STACK - 0x40000, 0x40000)
        mu.mem_map(SCRATCH, 0x10000)
        mu.mem_map(DONE, 0x1000)
        self.extra, self.owned, self.gapreads = [], None, set()
        mu.hook_add(UC_HOOK_CODE, self._code)
        mu.hook_add(UC_HOOK_MEM_WRITE, self._write)
        mu.hook_add(UC_HOOK_MEM_READ, self._read)

    def map_block(self, base, data):
        lo = base & ~0xFFF
        self.mu.mem_map(lo, ((base + len(data) - lo) + 0xFFF) & ~0xFFF)
        self.mu.mem_write(base, data)

    def inside(self, a):
        return any(lo <= a < hi for lo, hi in self.layout)

    stale_check = False

    def n(self, v):
        """A value as a coordinate when it is an address in the layout.  In
        the v3 world a value that already IS a coordinate is a missed fixup."""
        c = self.to_coord(v & ~1)
        if c is not None:
            return c | (v & 1)
        if self.stale_check and FL.piece_of(v & ~1) is not None:
            return ('STALE-COORDINATE', v)
        return v

    def _code(self, mu, addr, size, _):
        if addr == DONE:
            self.events.append(('return', self.n(mu.reg_read(UC_ARM_REG_R0))))
            mu.emu_stop()
            return
        if self.inside(addr):
            return
        regs = [self.n(mu.reg_read(r)) for r in (UC_ARM_REG_R0, UC_ARM_REG_R1,
                                                 UC_ARM_REG_R2, UC_ARM_REG_R3)]
        lr = mu.reg_read(UC_ARM_REG_LR)
        if self.inside(lr & ~1):                # a call: the stub answers
            ret = 7 if addr == TK_CRE else self.answer
            self.events.append(('call', addr, *regs, self.n(lr)))
            mu.reg_write(UC_ARM_REG_R0, ret)
            mu.reg_write(UC_ARM_REG_PC, lr)
        else:                                   # back into the firmware for good
            self.events.append(('exit', addr, *regs, self.n(mu.reg_read(UC_ARM_REG_SP))))
            mu.emu_stop()

    def _write(self, mu, access, addr, size, value, _):
        if self.owned is not None:
            self.owned.update(range(addr, addr + size))
        v = value & ((1 << 8 * size) - 1)
        self.events.append(('w', self.n(addr), size, self.n(v) if size == 4 else v))

    def _read(self, mu, access, addr, size, value, _):
        if self.owned is not None and FL.piece_of(addr) is not None and \
                not all(x in self.owned for x in range(addr, addr + size)) and \
                any(STOCK[x - 0xC0000000] for x in range(addr, addr + size)):
            # a zero the image and the block agree on is fine (an empty slot);
            # anything else is the firmware's data, which v3 does not carry
            self.gapreads.add((addr, mu.reg_read(UC_ARM_REG_PC)))
        if self.watch_old and any(a <= addr < b for a, b in FL.PIECES):
            self.events.append(('OLD-COORDINATE-READ', addr))

    def run(self, pc, regs, thumb=False, answer=0, watch_old=False):
        mu = self.mu
        self.events, self.answer, self.watch_old = [], answer, watch_old
        for r, v in zip((UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3), regs):
            mu.reg_write(r, v & 0xFFFFFFFF)
        mu.reg_write(UC_ARM_REG_SP, STACK - 0x2000)
        mu.reg_write(UC_ARM_REG_LR, DONE)
        cpsr = mu.reg_read(UC_ARM_REG_CPSR)
        mu.reg_write(UC_ARM_REG_CPSR, cpsr & ~0x20)
        try:
            mu.emu_start(pc | (1 if thumb else 0), DONE, count=STEPS)
            if mu.reg_read(UC_ARM_REG_PC) == DONE:
                self.events.append(('return', self.n(mu.reg_read(UC_ARM_REG_R0))))
            else:
                self.events.append(('steps', self.n(mu.reg_read(UC_ARM_REG_PC))))
        except Exception as e:                  # a fault is part of the record
            self.events.append(('fault', type(e).__name__, str(e)[:40],
                                self.n(mu.reg_read(UC_ARM_REG_PC))))
        return self.events


@unittest.skipIf(T.Uc is None or not T.IMAGE.exists(), 'needs unicorn and the image')
class FormatsV3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sup, cls.f = built()
        cls.img = T.IMAGE.read_bytes()
        cls.layout = FL.Layout()

    def stock(self, a, n=4):
        return self.img[a - 0xC0000000:a - 0xC0000000 + n]

    def boot(self, *others, sup=None, f=None, stale=None, cls=None):
        sup, f = sup or self.sup, f or self.f
        files, dirs = T.card(*others, (NAME, sup))
        cam = (cls or FmtCamera)(files, dirs, f['block'], stale=stale)
        r0, sp = cam.boot()
        self.assertEqual(sp, T.STACK - 0x1004)
        self.assertEqual(cam.misaligned, [])
        return cam

    def outcome(self, cam, name=NAME):
        """From the loader's books, not its log: 31FMT's 130 claim records fill
        the 96-entry log, so a sup loaded after it has no LOADED line."""
        st = cam.state()
        for i in range(cam.w(st + T.O_NSUPS)):
            sp = st + T.O_SUPS + T.SUP_BYTES * i
            if cam.cstr(sp, 40) == name:
                return ('LOADED', 'RELEASED')[cam.w(sp + 48)]
        return None

    def at(self, cam, f, coord):
        for p in f['pieces']:
            c0 = h(p['coord'])
            if c0 <= coord < c0 + p['bytes']:
                return cam.block + p['block_off'] + coord - c0
        raise KeyError(hex(coord))

    def coord(self, cam, f, a):
        for p in f['pieces']:
            lo = cam.block + p['block_off']
            if lo <= a < lo + p['bytes']:
                return h(p['coord']) + a - lo
        return None

    # ---- the loader --------------------------------------------------------
    def check_loaded(self, cam, f=None):
        f = f or self.f
        self.assertEqual(self.outcome(cam), 'LOADED')
        self.assertEqual(cam.old, [], 'the boot touched a fixed coordinate')
        j = {a: (n, data) for a, n, data in cam.journal()}
        for c in f['claims_list']:
            a, n = h(c['address']), c['bytes']
            self.assertIn(a, j, hex(a))
            self.assertEqual(j[a], (n, self.stock(a, n)), f'{a:#x}: journal = reference image')
        lo, hi = T.cave.CAVE_ARENA, T.cave.CAVE_ARENA_END
        for hk in f['hooks_list']:
            site, to = h(hk['site']), self.at(cam, f, h(hk['to']))
            word = cam.w(site)
            if hk['kind'] == 'Thumb B.W':
                ven = thumb_target(site, word)
                self.assertEqual((cam.w(ven), cam.w(ven + 4)), (0xF000F8DF, to | 1), hex(site))
            else:
                ven = arm_target(site, word)
                op = 0xEB if hk['kind'] == 'BL' else 0xEA
                self.assertEqual(word >> 24, op, hex(site))
                self.assertEqual((cam.w(ven), cam.w(ven + 4)), (0xE51FF004, to), hex(site))
            self.assertTrue(lo <= ven < hi and ven % 8 == 0, hex(ven))
        # every value patch is Jose's bytes, except what the compositor rewrites
        secs = FL.load(f['formats'])[0]
        rewritten = {0xC06BDA48, 0xC1A709BC, 0xC0D4DE04, 0xC12C7CF8, 0xC0F8E7EC}
        for c in f['claims_list']:
            a = h(c['address'])
            if c['writes'] and a not in rewritten:
                self.assertEqual(bytes(cam.mu.mem_read(a, c['bytes'])), secs[a], hex(a))
        return j

    def test_loads_relocates_and_hooks(self):
        cam = self.boot()
        self.check_loaded(cam)
        # the firmware MOVW/MOVT now loads the enum pair table where it landed
        mw, mt = cam.w(0xC06BDA3C), cam.w(0xC06BDA40)
        imm = lambda i: ((i >> 4) & 0xF000) | (i & 0xFFF)          # noqa: E731
        self.assertEqual(imm(mt) << 16 | imm(mw), self.at(cam, self.f, 0xC0731C40))
        self.assertEqual((mw & 0xFFF0F000, mt & 0xFFF0F000), (0xE3002000, 0xE3402000),
                         'movw/movt r2, as Jose wrote them')
        self.assertEqual(cam.w(0xC07426F8), self.at(cam, self.f, 0xC07304E0))
        # the compositor ran once: a task, and the run-once flag cleared
        self.assertEqual(len(cam.tasks), 1)
        self.assertEqual(cam.tasks[0], self.at(cam, self.f, 0xC0794034))
        self.assertEqual(cam.w(self.at(cam, self.f, 0xC07943CC)), 0)
        # the Settings controller max follows the number of formats on the card
        self.assertEqual(cam.w(0xC1A709BC), self.max_word(len(FL.FORMATS)))

    def max_word(self, n):
        return self.layout.img.word(0xC07943B4 + 4 * (n - 1))

    def test_power_off_puts_every_claimed_word_back(self):
        cam = self.boot()
        cam.power_off()
        for c in self.f['claims_list']:
            a, n = h(c['address']), c['bytes']
            self.assertEqual(bytes(cam.mu.mem_read(a, n)), self.stock(a, n), hex(a))

    def test_a_hook_left_by_last_boot_is_repaired_then_armed(self):
        stale = {0xC043CCF8: 0xEA0DEAD0, 0xC05E6400: 0xBF00BF00, 0xC0BDCCFC: 0x12345678}
        cam = self.boot(stale=stale)
        self.check_loaded(cam)
        repaired = {a for c, a, _, t in cam.log() if c == 'REPAIRED'}
        self.assertEqual(repaired, set(stale))

    def test_any_claim_held_by_another_releases_with_nothing_written(self):
        for site in (0xC043CCF8, 0xC0BDCCFC, 0xC0B59564, 0xC06BDA3C, 0xC12C7CF8):
            with self.subTest(site=hex(site)):
                o = T.test_sup('OTHR', [(site, T.word(self.img, site), 1, 0)])
                cam = self.boot(('05OTHER.BIN', o))
                self.assertEqual(self.outcome(cam), 'RELEASED')
                self.assertEqual(cam.tasks, [])
                self.assertEqual(sorted(j[0] for j in cam.journal()), [site])
                for hk in self.f['hooks_list']:
                    a = h(hk['site'])
                    self.assertEqual(cam.w(a), T.word(self.img, a), hex(a))
                self.assertEqual(cam.w(T.cave.CAVE_BUMP), T.cave.CAVE_ARENA, 'cave taken')

    def test_with_open_gate_v3_only_the_first_loads(self):
        sys.path.insert(0, str(ROOT / 'projects' / 'open-gate' / 'build'))
        import test_v3_og as OG
        og, ogf, ogname = OG.built('og3k')

        class Both(OG.OGCamera, FmtCamera):     # OG's uia_apply stub, our block
            def __init__(self, files, dirs, block_size, **kw):
                T.Camera.__init__(self, files, dirs, **kw)
                self.sups, self.uia_result, self.uia_calls = {ogf['block']: ogf}, 0, []
                self.restores, self.blocks, self.pending, self.restore_saw = [], {}, [], []
                self.mu.mem_write(OG.SETTER_BACK, struct.pack('<I', 0xE12FFF1E))
                self.by_addr[OG.SETTER_BACK] = 'SETTER_BACK'
                self.block_size, self.block, self.old = block_size, None, []

            def _alloc(self, n, align=8):
                p = OG.OGCamera._alloc(self, n, align)
                if n == self.block_size:
                    self.block = p
                return p

        cam = self.boot((ogname, og), cls=Both)
        self.assertEqual(self.outcome(cam, ogname), 'LOADED')
        self.assertEqual(self.outcome(cam), 'RELEASED')

    # ---- the strings: a uishare layer named after the file -----------------
    def check_strings(self, cam, f=None):
        """His ids through the firmware's own resolver = his table, as his hook
        answered; everything else as the firmware (or the layer below)."""
        f = f or self.f
        s = f['strings']
        base, count, tab = h(s['base']), s['count'], self.at(cam, f, h(s['table']))
        for i in range(count):
            self.assertEqual(cam.fw(RESOLVE, base + i), cam.w(tab + 4 * i), hex(base + i))
        p = cam.w(tab + 4 * (0xFFFFFFF6 - base))
        self.assertEqual(cam.cstr(p), 'S16 2096x1238')
        self.assertEqual((cam.fw(OWNS, p), cam.fw(REMAIN, p)), (1, cam.block + f['block'] - p))
        return base, count

    def test_strings_are_a_layer_that_answers_his_ids(self):
        cam = self.boot(cls=UICamera)
        self.check_loaded(cam)
        self.assertEqual([chain.name(cam.w, chain.outer(cam.w))], ['31FMT'])
        self.assertEqual(chain.layers(cam.w)[0][0], 0xFFFFFFD0)
        self.check_strings(cam)
        for off, want in ((0, POOL), (5, POOL + 5), (POOL_LEN - 1, POOL + POOL_LEN - 1),
                          (POOL_LEN, 0), (0xFFFFFFFF, 0), (0xFFFFFFCF, 0), (0xFFFFFFF7, 0),
                          (0x40000000, 0)):
            self.assertEqual(cam.fw(RESOLVE, off), want, hex(off))
        self.assertEqual((cam.fw(OWNS, POOL + 9), cam.fw(OWNS, cam.block - 4)), (1, 0))
        self.assertEqual(cam.fw(REMAIN, POOL + 9), POOL_LEN - 9)
        self.assertNotIn(RESOLVE, {h(x['site']) for x in self.f['hooks_list']})
        kinds = {h(c['address']): c['kind'] for c in self.f['claims_list']}
        self.assertEqual({a: kinds[a] for a in (RESOLVE, OWNS, REMAIN)},
                         {RESOLVE: 'SHARED_UI', OWNS: 'SHARED_UI', REMAIN: 'SHARED_UI'})

    def with_lossless(self, lname):
        cam = self.boot((lname, lossless_sup()), cls=UICamera)
        self.assertEqual(self.outcome(cam, lname), 'LOADED')
        self.check_loaded(cam)
        layers = chain.layers(cam.w)
        names, layer = [], chain.outer(cam.w)
        while layer is not None:
            names.append(chain.name(cam.w, layer))
            layer = chain.inner(cam.w, layer)
        self.check_strings(cam)
        loss = [(b, t) for b, t in layers if b < 0xF0000000]
        self.assertEqual(len(loss), 1)
        lb, texts = loss[0]
        self.assertIn('Lossless RAW', texts)
        for i, text in enumerate(texts):                         # its strings, through ours
            self.assertEqual(cam.cstr(cam.fw(RESOLVE, lb + i)), text)
        self.assertEqual(cam.fw(RESOLVE, lb + len(texts)), 0)
        return names[::-1], lb

    def test_with_lossless_v3_both_load_lossless_inside(self):
        names, lb = self.with_lossless('10LOSS.BIN')
        self.assertEqual(names, ['10LOSS', '31FMT'])
        self.assertEqual(lb, 0x40000000)

    def test_with_lossless_v3_both_load_lossless_outside(self):
        names, lb = self.with_lossless('40LOSS.BIN')
        self.assertEqual(names, ['31FMT', '40LOSS'])
        self.assertEqual(lb, 0x40000000, 'issued past nothing: the fixed range is skipped')

    def test_a_foreign_hook_on_a_string_site_releases_with_nothing_written(self):
        o = T.test_sup('OTHR', [(OWNS, T.word(self.img, OWNS), 3, 0xBF00BF00)])
        cam = self.boot(('05OTHER.BIN', o), cls=UICamera)
        self.assertEqual(self.outcome(cam), 'RELEASED')
        self.assertEqual(cam.tasks, [])
        for hk in self.f['hooks_list']:
            a = h(hk['site'])
            self.assertEqual(cam.w(a), T.word(self.img, a), hex(a))
        self.assertEqual(cam.w(RESOLVE), T.word(self.img, RESOLVE))

    def test_one_format_alone_builds_and_loads(self):
        for fm in FL.FORMATS:
            with self.subTest(fm=fm):
                sup, f = built((fm,))
                cam = self.boot(sup=sup, f=f)
                j = self.check_loaded(cam, f)
                self.assertEqual(cam.w(0xC1A709BC), self.max_word(1))
                self.check_clamp(cam, f, j)

    def check_clamp(self, cam, f, journal):
        """v0.6.1: every word the video clamp writes is claimed (journalled with
        the image's value, written back at power-off), and the bits it clears
        are clear in the image -- so 'off' is stock."""
        words = [h(a) for a in f['clamp_words']]
        if FL.vbin.VERSION == '0.6.0':
            self.assertEqual(words, [])
            return
        self.assertEqual(len(words), 8)
        covered = lambda a: any(s <= a < s + n for s, (n, _) in journal.items())   # noqa: E731
        self.assertEqual([hex(a) for a in words if not covered(a)], [])
        for a in words:
            self.assertEqual(T.word(self.img, a) & (0x8 | 0xC000), 0, hex(a))
        cam.power_off()
        for a in words:
            self.assertEqual(cam.w(a), T.word(self.img, a), hex(a))

    def test_the_clamp_words_are_claimed(self):
        cam = self.boot()
        self.check_clamp(cam, self.f, self.check_loaded(cam))

    # ---- the twins ---------------------------------------------------------
    def twins(self, formats=FL.FORMATS, sup=None, f=None):
        """(original World, v3 World) after the compositor ran in each."""
        sup, f = sup or self.sup, f or self.f
        layout = FL.Layout(formats)
        cam = self.boot(sup=sup, f=f)
        self.assertEqual(self.outcome(cam), 'LOADED')
        # v3: everything as the booted camera left it, the block where it was
        v3img = bytes(cam.mu.mem_read(0xC0000000, 0x04000000))
        blk = bytes(cam.mu.mem_read(cam.block, f['block']))
        blo, bhi = cam.block, cam.block + f['block']
        v = World(v3img, [(blo, bhi)], lambda a: self.coord(cam, f, a))
        v.stale_check = True
        v.map_block(cam.block, blk)
        # original: the stock image, Jose's sections at his addresses, then his
        # entry, as stage2 called it (the stubs answer as test_v3's did)
        orig = bytearray(self.img[:0x04000000].ljust(0x04000000, b'\0'))
        for a, b in sorted(layout.secs.items()):
            orig[a - 0xC0000000:a - 0xC0000000 + len(b)] = b
        o = World(bytes(orig), FL.PIECES, lambda a: a if FL.piece_of(a) is not None else None)
        o.owned = {x for a, b in layout.secs.items() if FL.piece_of(a) is not None
                   for x in range(a, a + len(b))}
        ev = o.run(FL.ENTRY, [FL.ENTRY, 0, 0, 0])
        self.assertEqual(ev[-1][0], 'return', ev[-6:])
        return o, v, cam, layout

    def test_twins_hold_the_same_layout_after_the_compositor(self):
        o, v, cam, layout = self.twins()
        self.assertEqual(o.gapreads, set(), 'Jose reads memory he never wrote')
        diffs = []
        for lo, hi in FL.PIECES:
            ob = bytes(o.mu.mem_read(lo, hi - lo))
            vb = bytes(v.mu.mem_read(self.at(cam, self.f, lo), hi - lo))
            for i in range(0, hi - lo, 4):
                if lo + i not in o.owned:
                    continue                            # firmware's, not Jose's
                ow, = struct.unpack_from('<I', ob, i)
                vw, = struct.unpack_from('<I', vb, i)
                if v.n(vw) == ow:
                    continue
                if lo + i in self.mm_sites(layout):
                    continue                            # a MOVW/MOVT: checked below
                diffs.append((hex(lo + i), hex(ow), hex(vw)))
        self.assertEqual(diffs, [])
        imm = lambda i: ((i >> 4) & 0xF000) | (i & 0xFFF)          # noqa: E731
        for w, t, val, _ in layout.pairs:
            vw = v.mu.mem_read(self.at(cam, self.f, w), 4)
            vt = v.mu.mem_read(self.at(cam, self.f, t), 4)
            got = imm(struct.unpack('<I', vt)[0]) << 16 | imm(struct.unpack('<I', vw)[0])
            self.assertEqual(v.n(got), val, hex(w))
        # and the firmware words the compositor writes
        for a, n in ((0xC06BDA48, 4), (0xC1A709BC, 4), (0xC0D4DE04, 8),
                     (0xC12C7CF8, 512), (0xC0F8E7EC, 92)):
            self.assertEqual(bytes(o.mu.mem_read(a, n)), bytes(v.mu.mem_read(a, n)), hex(a))

    def mm_sites(self, layout):
        return {x for w, t, _, _ in layout.pairs for x in (w, t)}

    def inputs(self):
        z = SCRATCH
        return [[0, 0, 0, 0], [1, 2, 3, 4], [z, 5, 1, 0], [z, 8, 1, 1], [z, 9, 0, 2],
                [z, 0xFFFFFFD5, 0, 0], [z, 0xC18C0474, 0xC0D22400, 0], [4, 1, 1, 1]]

    def test_twins_run_every_handler_alike(self):
        o, v, cam, layout = self.twins()
        handlers = sorted(layout.roots)
        self.assertGreaterEqual(len(handlers), 30)
        ran = mismatch = steps = 0
        report = []
        for pc, th in handlers:
            for regs in self.inputs():
                for answer in (0, 1):
                    for w in (o, v):
                        w.mu.mem_write(SCRATCH, bytes(0x10000))
                        w.mu.mem_write(SCRATCH + 0x14, struct.pack('<I', 0xC18C0474))
                        w.mu.mem_write(SCRATCH + 0x24, struct.pack('<I', 0xC18C0460))
                    eo = o.run(pc, regs, th, answer)
                    ev = v.run(self.at(cam, self.f, pc), regs, th, answer, watch_old=True)
                    ran += 1
                    steps += len(eo)
                    if eo != ev:
                        mismatch += 1
                        k = next((i for i, (a, b) in enumerate(zip(eo, ev)) if a != b),
                                 min(len(eo), len(ev)))
                        report.append((hex(pc), regs, answer, k, eo[k:k + 2], ev[k:k + 2]))
        self.assertEqual(report[:5], [], f'{mismatch} of {ran} runs differ')
        self.assertEqual(o.gapreads, set(), 'Jose reads memory he never wrote')
        print(f'\n  twins: {ran} runs, {len(handlers)} handlers, {steps} events compared',
              file=sys.stderr)

    def test_twins_see_a_missing_fixup(self):
        """The twin test can fail: drop one MOVW/MOVT fixup and one word fixup
        from the built file and the records must differ."""
        sup = bytearray(self.sup)
        tab = struct.unpack_from('<21I', sup, BV.SL_HEADER_LEN)
        n_abs, abs_off, n_mm, mm_off = tab[6], tab[7], tab[8], tab[9]
        for which in ('mm', 'abs'):
            with self.subTest(which=which):
                s = bytearray(sup)
                if which == 'mm':        # drop the last pair: count - 1
                    struct.pack_into('<I', s, BV.SL_HEADER_LEN + 4 * 8, n_mm - 1)
                else:
                    struct.pack_into('<I', s, BV.SL_HEADER_LEN + 4 * 6, n_abs - 1)
                o, v, cam, layout = self.twins(sup=bytes(s), f=self.f)
                bad = 0
                for pc, th in sorted(layout.roots):
                    for regs in self.inputs()[:4]:
                        for w in (o, v):
                            w.mu.mem_write(SCRATCH, bytes(0x10000))
                        if o.run(pc, regs, th) != v.run(self.at(cam, self.f, pc), regs, th,
                                                       watch_old=True):
                            bad += 1
                same_layout = True
                for lo, hi in FL.PIECES:
                    ob = bytes(o.mu.mem_read(lo, hi - lo))
                    vb = bytes(v.mu.mem_read(self.at(cam, self.f, lo), hi - lo))
                    for i in range(0, hi - lo, 4):
                        if lo + i not in o.owned:
                            continue
                        ow, = struct.unpack_from('<I', ob, i)
                        vw, = struct.unpack_from('<I', vb, i)
                        if v.n(vw) != ow and lo + i not in self.mm_sites(layout):
                            same_layout = False
                self.assertTrue(bad or not same_layout or cam.old,
                                f'dropping a {which} fixup went unnoticed')


if __name__ == '__main__':
    unittest.main()
