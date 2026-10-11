"""Res-lab (Sensor Lab) as a Loader v3 sup, loaded by the real 加載器.

    cd projects/open-gate/build && python3 -B -m unittest test_v3_reslab

The real loader.S (as the AutoRun spells it), the real LOADER.BIN and the built
50RESLAB.BIN run in Unicorn against the reference image (fp_usb_shell/v3/
test_v3.Camera). Set RESLAB_V3_CARD to a saved v3 card directory to test its
exact AutoRun, LOADER.BIN and 50RESLAB.BIN instead of rebuilding the payload.
The real sl_menu_install runs against model GUI objects in the acceptance
tests; controlled result stubs cover the install-failure and NBR-refusal
paths. og3krestore is stubbed (the AutoRun card's camera-tested code; only
its call is checked). Everything else runs: claims, relocation, the static
words, the pointer pairs, both hook phases, the MARK words, exposing the page,
the real recording picker and shell composition.

Emulated, not on the camera.
"""
import json
import os
import pathlib
import struct
import subprocess
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent
V3 = ROOT / 'fpSup' / 'fp_usb_shell' / 'v3'
sys.path.insert(0, str(V3))
sys.path.insert(0, str(V3.parent))

import test_v3 as T                                       # noqa: E402
import build_v3 as BV                                     # noqa: E402

PICKER = 0xC043CCF8
GS_SITE, GS_BACK = 0xC03A6DD8, 0xC03A6DDC                  # og3kgs
FLAG, GS_LOG = 0xC0731C08, 0xC07328C0
NBU_BASE = 0xC18C0460
SCRATCH = T.STACK - 0x8000                                 # a fake B2_5 runtime entry
M_RESULT, M_NBR, M_MODES, M_LIVE, M_PACK, M_READER = 0x0C, 0x1C, 0x50, 0x54, 0x10, 0x18
_BUILT = {}
UI_HEAP = 0x48000000                         # model GUI objects, outside the sup heap
UI_APP, UI_SCREEN, UI_READER, UI_ENTRIES, UI_NAMES, UI_DESCS = (
    UI_HEAP, UI_HEAP + 0x1000, UI_HEAP + 0x2000, UI_HEAP + 0x3000,
    UI_HEAP + 0x4000, UI_HEAP + 0x5000)
UI_LOOKUP, UI_REGISTER = 0xC05DB418, 0xC05DB308


def built():
    if 'r' not in _BUILT:
        if os.environ.get('RESLAB_V3_CARD'):
            out = pathlib.Path(os.environ['RESLAB_V3_CARD']).resolve()
            meta = json.loads((out / 'build.json').read_text())
            _BUILT['card'] = out
            _BUILT['r'] = ((out / 'fpSup' / meta['file']).read_bytes(), meta['facts'], meta['file'])
            return _BUILT['r']
        with tempfile.TemporaryDirectory(prefix='rlv3t-') as t:
            out = pathlib.Path(t) / 'o'
            r = subprocess.run([sys.executable, '-B', str(HERE / 'build_v3_reslab.py'),
                                '--out', str(out)], capture_output=True, text=True)
            if r.returncode:
                raise RuntimeError(f'builder exited {r.returncode}:\n' +
                                   (r.stdout + r.stderr)[-4000:])
            meta = json.loads((out / 'build.json').read_text())
            _BUILT['r'] = ((out / meta['file']).read_bytes(), meta['facts'], meta['file'])
    return _BUILT['r']


def h(s):
    return int(s, 16) if isinstance(s, str) else s


def mov_imm(word):
    return (((word >> 16) & 15) << 12) | (word & 0xFFF)


def branch_target(site, word):
    d = word & 0xFFFFFF
    d -= 0x1000000 if d & 0x800000 else 0
    return site + 8 + 4 * d


def thumb_target(site, word):
    h1, h2 = word & 0xFFFF, word >> 16
    s, j1, j2 = (h1 >> 10) & 1, (h2 >> 13) & 1, (h2 >> 11) & 1
    i1, i2 = int(not (j1 ^ s)), int(not (j2 ^ s))
    imm = (s << 24) | (i1 << 23) | (i2 << 22) | ((h1 & 0x3FF) << 12) | ((h2 & 0x7FF) << 1)
    if imm & (1 << 24):
        imm -= 1 << 25
    assert h1 & 0xF800 == 0xF000 and h2 & 0xD000 == 0x9000, hex(word)
    return site + 4 + imm


class RLCamera(T.Camera):
    def __init__(self, files, dirs, f, install=2, nbr=0, **kw):
        super().__init__(files, dirs, **kw)
        self.f, self.install_result, self.nbr = f, install, nbr
        self.installs, self.restores, self.block, self.pending = [], [], None, []
        self.restore_saw = []
        self.registry = {}
        if install is None:
            self.seed_gui()
        for at in (GS_BACK,):
            self.mu.mem_write(at, struct.pack('<I', 0xE12FFF1E))
            self.by_addr[at] = 'GS_BACK'
        self.image_before = bytes(self.mu.mem_read(0xC0000000, 0x3000000))

    def seed_gui(self):
        """Native object layout from test_sl_menu_arm; only registry calls are
        substituted. The emitted installer and uishare pool run unchanged."""
        self.mu.mem_map(UI_HEAP, 0x20000)
        self.put(0xC37B7048, UI_APP)
        self.put(UI_APP + 0x80, 1)
        self.put(UI_APP + 0x8C, UI_APP + 0x100)
        self.put(UI_APP + 0x100, UI_SCREEN)
        self.put(UI_APP + 0x888, UI_APP + 0x800)
        self.mu.mem_write(UI_NAMES, b'MainB2\0')
        self.mu.mem_write(UI_NAMES + 0x40, b'B2_5\0')
        for off, value in ((4, UI_APP), (8, UI_NAMES), (0x24, UI_READER)):
            self.put(UI_SCREEN + off, value)
        for off, value in ((0x10, 176152), (0x14, NBU_BASE + 0x14), (0x24, NBU_BASE),
                           (0xA8, 1), (0xAC, UI_ENTRIES)):
            self.put(UI_READER + off, value)
        self.put(UI_ENTRIES + 4, UI_NAMES + 0x40)
        self.put(UI_ENTRIES + 8, 0x19C130)
        for at, name in ((UI_LOOKUP, 'UI_LOOKUP'), (UI_REGISTER, 'UI_REGISTER')):
            self.mu.mem_write(at, struct.pack('<H', 0x4770))
            self.by_addr[at] = name

    def at(self, coord):
        return self.block + self.f['img_off'] + h(coord) - h(self.f['layout0'])

    def _alloc(self, n, align=8):
        p = super()._alloc(n, align)
        if n == self.f['block']:
            self.block = p
            ins = p + (self.f['install_off'] & ~1)
            rst = self.at(self.f['restore'])
            self.by_addr[rst] = ('RESTORE',)
            self.pending = [(rst, struct.pack('<I', 0xE12FFF1E))]
            if self.install_result is not None:
                self.by_addr[ins] = ('INSTALL',)
                self.pending.append((ins, struct.pack('<H', 0x4770)))
        return p

    def _hook(self, mu, addr, size, data):
        name = self.by_addr.get(addr)
        if name in ('UI_LOOKUP', 'UI_REGISTER'):
            from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_SP
            if self.r(UC_ARM_REG_SP) & 7:
                self.misaligned.append(name)
            self.calls.append(name)
            a0, a1, a2 = (self.r(r) for r in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2))
            if name == 'UI_LOOKUP':
                self.put(a2, self.registry.get(self.cstr(a1), 0))
            else:
                assert a0 == UI_APP and a1 == 1
                kind, text, value = struct.unpack('<3I', mu.mem_read(a2, 12))
                desc = UI_DESCS + 32 * len(self.registry)
                if kind == 2:                       # the native registry copies text
                    copied = UI_NAMES + 0x100 + 32 * len(self.registry)
                    mu.mem_write(copied, self.cstr(value).encode() + b'\0')
                    value = copied
                for off, v in ((0, kind), (4, text), (8, value)):
                    self.put(desc + off, v)
                self.registry[self.cstr(text)] = desc
            return self._ret(0)
        if name == 'DCACHE' and self.pending:
            for at, code in self.pending:
                mu.mem_write(at, code)
            self.pending = []
        if name == ('RESTORE',):
            self.restores.append(1)
            self.restore_saw.append(self.w(PICKER) != T.word(self.img, PICKER))
            return self._ret(0)
        if name == ('INSTALL',):
            from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2
            m, area, n = (self.r(r) for r in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2))
            self.installs.append((m, area, n))
            sf = self.f['state_fields']
            if self.install_result == 1:              # what sl_menu_install leaves behind
                self.put(SCRATCH + 8, 0x19C130)
                self.put(m + sf['entry'], SCRATCH)
                self.put(m + sf['page'], NBU_BASE + 0x123450)
                self.put(m + sf['reader'], 0x4A000000)
                self.put(m + sf['nbr'], area + 0x2000)
                self.put(m + sf['nbr_len'], 0x40)
                self.put(m + sf['result'], 1)
                if self.nbr:
                    self.put(self.at(self.f['mark']) + M_NBR, self.nbr)
            return self._ret(self.install_result)
        return super()._hook(mu, addr, size, data)


@unittest.skipIf(T.Uc is None or not T.IMAGE.exists(), 'needs unicorn and the image')
class ResLabV3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sup, cls.f, cls.name = built()
        cls.img = T.IMAGE.read_bytes()

    def stock(self, a, n=4):
        return self.img[a - 0xC0000000:a - 0xC0000000 + n]

    def boot(self, *sups, install=2, nbr=0, stale=None):
        files, dirs = T.card(*sups, (self.name, self.sup))
        if 'card' in _BUILT:
            files['\\fpSup\\LOADER.BIN'] = (_BUILT['card'] / 'fpSup/LOADER.BIN').read_bytes()
            dirs['\\fpSup'][0] = ('LOADER.BIN', 0x20, len(files['\\fpSup\\LOADER.BIN']))
        cam = RLCamera(files, dirs, self.f, install=install, nbr=nbr, stale=stale)
        if 'card' in _BUILT:
            ar = (_BUILT['card'] / 'AutoRun.txt').read_bytes()
            for a, v in BV.loader_words(ar).items():
                cam.put(a, v)
        r0, sp = cam.boot()
        self.assertEqual(sp, T.STACK - 0x1004)
        self.assertEqual(cam.misaligned, [])
        return cam

    def outcome(self, cam, name=None):
        return {t: c for c, _, _, t in cam.log() if c in ('LOADED', 'RELEASED')}.get(name or self.name)

    def check_hooks(self, cam, rows, armed=True):
        lo, hi = T.cave.CAVE_ARENA, T.cave.CAVE_ARENA_END
        for site, to, kind in ((h(a), h(b), k) for a, b, k in rows):
            word = cam.w(site)
            if not armed:
                self.assertEqual(struct.pack('<I', word), self.stock(site), hex(site))
                continue
            if kind == 2:
                ven = thumb_target(site, word)
                self.assertEqual((cam.w(ven), cam.w(ven + 4)), (0xF000F8DF, cam.at(to) | 1), hex(site))
            else:
                self.assertEqual(word & 0xFF000000, 0xEB000000 if kind == 1 else 0xEA000000, hex(site))
                ven = branch_target(site, word)
                self.assertEqual((cam.w(ven), cam.w(ven + 4)), (0xE51FF004, cam.at(to)), hex(site))
            self.assertTrue(lo <= ven < hi and ven % 8 == 0, hex(site))

    # ---- loaded: the core, menu refused (as in emulation, no GUI) -----------
    def test_loads_claims_relocates_and_arms_the_core(self):
        cam = self.boot()
        self.assertEqual(self.outcome(cam), 'LOADED')
        j = {a: d for a, n, d in cam.journal()}
        self.assertEqual(len(j), self.f['claims'])
        for a, d in j.items():
            self.assertEqual(d, self.stock(a, len(d)), f'{a:#x}: journal holds the image')
        self.check_hooks(cam, self.f['core_hooks'])
        self.check_hooks(cam, self.f['late_hooks'], armed=False)   # the menu did not install
        self.assertEqual(cam.restores, [1])
        self.assertEqual(cam.restore_saw, [True], 'restore after the hooks')
        base = cam.at(self.f['layout0'])
        for fx in self.f['fixups']:                                  # data the firmware reads
            self.assertTrue(base <= cam.w(cam.at(fx)) < base + 0x8000, fx)

    def test_every_word_the_core_changes_later_is_journalled(self):
        """Independent of the builder's list: the 70 sensor-mode timing records
        (the picker writes any donor's) and the preview heights (og3ksel)."""
        sys.path.insert(0, str(HERE))
        from imx410_full import TIMING
        import imx410_plan as PL
        cam = self.boot()
        covered = set()
        for a, n, _ in cam.journal():
            covered.update(range(a, a + n, 4))
        want = {TIMING + i * 0x20 + k for i in range(70) for k in (4, 8)} | set(PL.PREV_PROFILES)
        self.assertEqual(want - covered, set())

    def test_pointer_pairs_name_the_tables_where_they_landed(self):
        cam = self.boot()
        for lo, hi, to in self.f['pointer_pairs']:
            lo, hi, to = h(lo), h(hi), h(to)
            got = mov_imm(cam.w(hi)) << 16 | mov_imm(cam.w(lo))
            self.assertEqual(got, cam.at(to), hex(lo))
            self.assertEqual(cam.w(lo) & 0xFFF0F000, struct.unpack('<I', self.stock(lo))[0] & 0xFFF0F000)

    def test_static_words_are_written(self):
        cam = self.boot()
        st = cam.state()
        n = cam.w(st + T.O_NCLAIMS)
        changed = sum(1 for a, k, d in cam.journal() if bytes(cam.mu.mem_read(a, k)) != d)
        writes = self.f['claims'] - self.f['runtime_runs'] - len(self.f['late_hooks'])
        self.assertEqual(changed, writes, 'every written range differs, nothing else')
        self.assertEqual(n, self.f['claims'])

    def test_the_menu_finds_the_core_through_the_picker(self):
        """sl_modes.c sl_core_base, in Python."""
        cam = self.boot()
        ven = branch_target(PICKER, cam.w(PICKER))
        target = cam.w(ven + 4)
        base = target - self.f['core_offsets']['fmt_code']
        self.assertEqual(base, cam.at(self.f['layout0']))
        self.assertEqual(base & 7, 0)
        self.assertEqual(cam.w(base + self.f['core_offsets']['core_magic']), 0x534C434F)
        mark = base + self.f['core_offsets']['mark']
        self.assertEqual(cam.w(mark), 0x534D4C53)
        state = cam.w(mark + 8)
        self.assertEqual(cam.w(state + self.f['state_fields']['core_base']), base)
        self.assertEqual(cam.w(mark + M_RESULT), 2, 'the installer answer, for mem get')

    def test_a_payload_runs_through_its_hook(self):
        cam = self.boot()
        flag, log = cam.at(FLAG), cam.at(GS_LOG)
        cam.put(flag, 1)
        r0, _ = cam.call(GS_SITE)
        self.assertEqual((r0, cam.w(log)), (1, 1))
        cam.put(flag, 0)
        cam.call(GS_SITE)
        self.assertEqual(cam.w(log), 1)
        self.assertIn('GS_BACK', cam.calls)

    def test_recording_picker_runs_from_the_block_and_publishes_profile_87(self):
        from test_imx410_fmt import OG3K, TAB, DESC, IMAGER
        import imx410_plan as PL
        cam = self.boot()
        key = SCRATCH + 0x100
        cam.mu.mem_write(key, b'CUST30\0')
        cam.mu.mem_write(DESC, struct.pack('<4I', 0xC0B59500, 70, 0xC0B59DC0, 70))
        cam.put(IMAGER, DESC)
        cam.mu.mem_write(cam.at(PL.AXIS), struct.pack(f'<{len(OG3K)}I', *OG3K))
        cam.mu.mem_write(cam.at(PL.RECIPE), bytes(PL.RECIPE_WORDS * 4))
        entry, sp = cam.call(PICKER, r0=0xAAAA0000, r1=TAB[12], r2=key)
        self.assertEqual(sp, T.STACK - 0x1004)
        self.assertEqual(entry, cam.at(PL.ENTRY_ADDR))
        self.assertEqual((cam.w(entry), cam.w(entry + 4), cam.w(entry + 12)),
                         (5, 87, entry + 20))
        self.assertEqual(bytes(cam.mu.mem_read(entry + 20, 7)), b'CUST30\0')
        cam.power_off()
        for a, n, _ in cam.journal():
            self.assertEqual(bytes(cam.mu.mem_read(a, n)), self.stock(a, n), hex(a))

    # ---- the menu installed --------------------------------------------------
    def test_real_installer_accepts_exact_fit_without_reopening_the_file(self):
        cam = self.boot(install=None)
        mark = cam.at(self.f['mark'])
        self.assertEqual(cam.w(mark + M_RESULT), 1, 'the real emitted installer must install')
        self.assertEqual(len(cam.registry), 49)
        self.assertEqual(cam.w(UI_ENTRIES + 8),
                         cam.block + self.f['area_off'] + 0x1000 + 0x24 - NBU_BASE & 0xFFFFFFFF)
        self.assertEqual(cam.opened.count('\\fpSup\\' + self.name), 2,
                         'only the loader header read and whole-file read')
        self.check_hooks(cam, self.f['late_hooks'])
        self.assertEqual(cam.misaligned, [])

    def test_real_installer_preserves_firmware_layout_and_power_off_restores_claims(self):
        cam = self.boot(install=None)
        self.assertEqual(bytes(cam.mu.mem_read(0xC0730000, 0x8000)),
                         self.stock(0xC0730000, 0x8000), 'all res-lab code and state are in its block')
        covered = {a + off for a, n, _ in cam.journal() for off in range(0, n, 4)}
        unexpected = []
        after = bytes(cam.mu.mem_read(0xC0000000, 0x3000000))
        for page in range(0, len(after), 0x1000):
            if after[page:page + 0x1000] == cam.image_before[page:page + 0x1000]:
                continue
            for off in range(page, page + 0x1000, 4):
                a = 0xC0000000 + off
                if T.CAVE_LOW <= a < 0xC0730000:        # shared loader/arena/rendezvous
                    continue
                if after[off:off + 4] != cam.image_before[off:off + 4] and a not in covered:
                    unexpected.append(hex(a))
        self.assertEqual(unexpected, [], 'every firmware write outside the shared cave is claimed')
        cam.power_off()
        cam.power_off()
        for a, n, _ in cam.journal():
            self.assertEqual(bytes(cam.mu.mem_read(a, n)), self.stock(a, n), hex(a))

    def test_real_installer_bounds_declared_slmp_length_before_parsing(self):
        from unicorn import UC_HOOK_MEM_READ
        cam = self.boot(install=None)
        ins = cam.block + (self.f['install_off'] & ~1)
        cam.registry.clear()
        cam.put(UI_ENTRIES + 8, 0x19C130)
        area, size = cam.block + self.f['area_off'], 0x1000 + self.f['slmp']
        m = cam.block + self.f['state_off']
        for declared, result in ((self.f['slmp'] + 4, 6), (1, 8), (0, 7)):
            with self.subTest(declared=declared):
                cam.put(m, 0)
                cam.put(area, declared)
                reads = []
                hook = cam.mu.hook_add(UC_HOOK_MEM_READ,
                                       lambda mu, access, a, n, value, data: reads.append(a),
                                       begin=area + 0x1000, end=area + 0x1023)
                try:
                    r0, sp = cam.call(ins, r0=m, r1=area, r2=size, thumb=True)
                finally:
                    cam.mu.hook_del(hook)
                self.assertEqual(r0, result)
                self.assertEqual(reads, [], 'reject the declared length before reading SLMP fields')
                self.assertEqual(sp, T.STACK - 0x1004)
                self.assertEqual(cam.registry, {})
                self.assertEqual(cam.w(UI_ENTRIES + 8), 0x19C130)

    def test_debug_shell_and_reslab_load_together(self):
        shell = ((_BUILT['card'] / 'fpSup/00SHELL.BIN').read_bytes()
                 if 'card' in _BUILT and (_BUILT['card'] / 'fpSup/00SHELL.BIN').exists()
                 else BV.shell_sup())
        cam = self.boot(('00SHELL.BIN', shell), install=None)
        self.assertEqual(self.outcome(cam, '00SHELL.BIN'), 'LOADED')
        self.assertEqual(self.outcome(cam), 'LOADED')
        self.assertEqual(cam.w(cam.at(self.f['mark']) + M_RESULT), 1)
        self.assertEqual(len(cam.tasks), 1, 'shell entry creates its worker and returns')
        cam.power_off()
        for a, n, _ in cam.journal():
            self.assertEqual(bytes(cam.mu.mem_read(a, n)), self.stock(a, n), hex(a))

    def test_menu_installed_arms_the_late_hooks_and_exposes_the_page(self):
        cam = self.boot(install=1)
        (m, area, n), = cam.installs
        self.assertEqual(area, cam.block + self.f['area_off'])
        self.assertEqual(cam.w(area), self.f['slmp'])
        self.assertEqual(bytes(cam.mu.mem_read(area + 0x1000, 4)), b'SLMP')
        self.check_hooks(cam, self.f['late_hooks'])
        self.assertEqual(cam.w(SCRATCH + 8), 0x123450, 'B2_5 switched to the private page')
        mark = cam.at(self.f['mark'])
        self.assertEqual(cam.w(mark + M_RESULT), 1)
        self.assertEqual(cam.w(mark + M_READER), 0x4A000000)
        self.assertEqual(cam.w(mark + M_PACK), area + 0x2000)
        lo, hi = cam.block + 32, cam.block + 32 + self.f['text']
        for k in (M_MODES, M_LIVE):
            fn = cam.w(mark + k)
            self.assertTrue(fn & 1 and lo <= fn & ~1 < hi, f'+{k:#x} = {fn:#x}')

    def test_nbr_refused_puts_the_stock_page_back(self):
        cam = self.boot(install=1, nbr=3)
        self.assertEqual(cam.w(SCRATCH + 8), 0x19C130)
        self.assertEqual(cam.w(cam.at(self.f['mark']) + M_RESULT), 12)

    def test_power_off_puts_every_claimed_word_back(self):
        cam = self.boot(install=1)
        cam.power_off()
        for a, n, d in cam.journal():
            self.assertEqual(bytes(cam.mu.mem_read(a, n)), self.stock(a, n), hex(a))

    def test_a_stale_hook_is_repaired_then_armed(self):
        site = h(self.f['core_hooks'][0][0])
        cam = self.boot(stale={site: 0xEA0DEAD0})
        self.assertEqual({a for c, a, _, t in cam.log() if c == 'REPAIRED'}, {site})
        self.check_hooks(cam, self.f['core_hooks'])

    def test_menu_callbacks_run_on_an_aligned_stack(self):
        """MARK+0x50/+0x54 are entered from hook payloads with the firmware's
        stack parity; sl_menu_ui / sl_menu_live must see sp 8-aligned."""
        from unicorn.arm_const import UC_ARM_REG_SP, UC_ARM_REG_LR
        cam = self.boot(install=1)
        mark = cam.at(self.f['mark'])
        seen = []
        for k, off in ((M_MODES, 'ui_off'), (M_LIVE, 'live_off')):
            fn = cam.block + (self.f[off] & ~1)
            cam.by_addr[fn] = ('SP',)
            cam.mu.mem_write(fn, struct.pack('<H', 0x4770))        # bx lr
            orig = cam._hook
            def hook(mu, addr, size, data, fn=fn):
                if addr == fn:
                    seen.append(cam.r(UC_ARM_REG_SP))
                    return cam._ret(0)
                return orig(mu, addr, size, data)
            cam._hook = hook
            sp0 = (T.STACK - 0x1000) & ~7 | 4                       # 4 mod 8, as the firmware may
            self.assertEqual(sp0 % 8, 4)
            cam.call(cam.w(mark + k) & ~1, sp=sp0, thumb=True)
            self.assertEqual(cam.r(UC_ARM_REG_SP), sp0, 'sp put back')
            cam._hook = orig
        self.assertEqual(len(seen), 2)
        self.assertTrue(all(s % 8 == 0 for s in seen), [hex(s) for s in seen])

    # ---- the shared page-id site (ALL_SUPS_MENU.md "0xC056461C") -------------------
    def run_site(self, cam, name):
        """Call the hooked BL at the page-id site with r1 = a page name; stop
        when it returns past the site.  -> r0."""
        from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_SP
        site = h(self.f['gui_site'])
        cam.mu.mem_write(SCRATCH + 0x100, name.encode() + b'\0')
        cam.mu.reg_write(UC_ARM_REG_SP, T.STACK - 0x1004)
        cam.mu.reg_write(UC_ARM_REG_R0, 0)
        cam.mu.reg_write(UC_ARM_REG_R1, SCRATCH + 0x100)
        cam.mu.emu_start(site, site + 4, count=400)
        return cam.r(UC_ARM_REG_R0)

    def test_page_id_site_is_shared_and_alone_it_passes_to_the_firmware(self):
        cam = self.boot(install=1)
        site = h(self.f['gui_site'])
        kinds = {a: k for a, n, k, _, res, _ in
                 (struct.unpack('<IIBBBB', cam.mu.mem_read(cam.state() + T.O_CLAIMS + 12 * i, 12))
                  for i in range(cam.w(cam.state() + T.O_NCLAIMS))) if not res}
        self.assertEqual(kinds[site], 1, 'CHAIN')
        self.assertEqual(cam.w(cam.at(self.f['gui_next'])), 0xC0564638, 'the stock target')
        self.assertNotEqual(self.run_site(cam, 'SL_LAB'), 0, 'our page: the parent id')

    def test_page_id_site_stacks_on_a_layer_below(self):
        below = 0xC0100000                       # another sup's layer: r0 = 0x77, return
        hooked = 0xEB000000 | (((below - h(self.f['gui_site']) - 8) >> 2) & 0xFFFFFF)
        other = self.other('PAGE', (h(self.f['gui_site']), 1, hooked))
        cam = self.boot(('05PAGE.BIN', other), install=1)
        self.assertEqual(self.outcome(cam, '05PAGE.BIN'), 'LOADED')
        self.assertEqual(self.outcome(cam), 'LOADED')
        cam.mu.mem_write(below, struct.pack('<2I', 0xE3A00077, 0xE12FFF1E))
        self.assertEqual(cam.w(cam.at(self.f['gui_next'])), below)
        self.assertEqual(self.run_site(cam, 'B2_5'), 0x77, 'not ours: passed down')
        r0 = self.run_site(cam, 'SL_LAB')
        self.assertNotIn(r0, (0, 0x77), 'ours: answered here')
        cam.power_off()
        self.assertEqual(struct.pack('<I', cam.w(h(self.f['gui_site']))),
                         self.stock(h(self.f['gui_site'])))

    # ---- released: nothing written ---------------------------------------------
    def assert_released_clean(self, cam, held=()):
        self.assertEqual(self.outcome(cam), 'RELEASED')
        self.assertEqual((cam.restores, cam.installs), ([], []))
        for rows in (self.f['core_hooks'], self.f['late_hooks']):
            for a, _, _ in rows:
                if h(a) not in held:
                    self.assertEqual(struct.pack('<I', cam.w(h(a))), self.stock(h(a)), a)
        for lo, _, _ in self.f['pointer_pairs']:
            self.assertEqual(bytes(cam.mu.mem_read(h(lo), 8)), self.stock(h(lo), 8))
        self.assertEqual(sorted(j[0] for j in cam.journal()), sorted(held))

    def other(self, sid, *rows):
        return T.test_sup(sid, [(a, struct.unpack('<I', self.stock(a))[0], k, new)
                                for a, k, new in rows])

    def test_a_late_hook_site_held_by_another_releases(self):
        site = h(self.f['late_hooks'][-1][0])
        cam = self.boot(('05OTHER.BIN', self.other('OTHR', (site, 1, 0))))
        self.assert_released_clean(cam, held=(site,))

    def test_a_static_word_held_by_another_releases(self):
        cam0 = self.boot()
        moved = [a for a, n, d in cam0.journal() if bytes(cam0.mu.mem_read(a, n)) != d
                 and a not in {h(x[0]) for x in self.f['core_hooks']}
                 and a not in {h(x[0]) for x in self.f['pointer_pairs']}]
        cam = self.boot(('05OTHER.BIN', self.other('OTHR', (moved[-1], 2, 0))))
        self.assert_released_clean(cam, held=(moved[-1],))

    def cave_hog(self, n):
        import armasm
        src = pathlib.Path(tempfile.mkdtemp(prefix='hog-')) / 'hog.S'
        src.write_text(f'''.syntax unified
.arm
.text
entry:
    push {{r4, lr}}
    mov r0, r1
    movw r1, #:lower16:{n}
    movt r1, #:upper16:{n}
    ldr ip, [r0, #20]
    blx ip
    mov r0, #0
    pop {{r4, pc}}
''')
        return BV.make_sup(armasm.assemble(src), BV.SL_HEADER_LEN, 'HOG')

    def test_a_full_cave_releases_with_nothing_written(self):
        n = T.cave.CAVE_ARENA_END - T.cave.CAVE_ARENA - 8 * 34      # 35 veneers needed
        cam = self.boot(('05HOG.BIN', self.cave_hog(n)))
        self.assertEqual(self.outcome(cam, '05HOG.BIN'), 'LOADED')
        self.assert_released_clean(cam)


if __name__ == '__main__':
    unittest.main()
