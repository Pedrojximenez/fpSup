"""OpenGate (OG3K, OG2K) as Loader v3 sups, loaded by the real 加載器.

    cd projects/open-gate/build && python3 -B -m unittest test_v3_og

The real loader.S (as the AutoRun spells it), the real LOADER.BIN and the built
30OG3K.BIN / 30OG2K.BIN run in Unicorn against the reference image; the
firmware's file, directory, allocator and power-off routines are Python
(fp_usb_shell/v3/test_v3.Camera).

Two things are stubbed inside the sup and say so: uishare's uia_apply (the
image's RAM has no GUI object; uishare/test_ui_apply.py covers the applier) --
the stub checks the block it is handed: its hash, one QS_OPTION (the shared
Quick Set layer, QS_SHARE.md §9) with the images named after the file and the
private pack, and nothing to relocate (no STRBASE); and og3krestore (it asks the
firmware's settings objects; it is the AutoRun card's camera-tested code, here
only its call is checked). Everything else runs: the claims, the relocation,
the veneers, and OpenGate's own picker and resolution-setter payloads, called
through their hooked firmware sites, reaching their data PC-relative.

Emulated, not on the camera.
"""
import json
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
sys.path.insert(0, str(ROOT / 'fpSup' / 'uishare'))

import test_v3 as T                                       # noqa: E402
import build_v3 as BV                                     # noqa: E402

from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_PC  # noqa: E402

TAB3 = 0xC0BE5B50                                         # the 12-bit CinemaDNG picker table
PICKER, SETTER, SETTER_BACK = 0xC043CCF8, 0xC005C020, 0xC005C024
FMTSET, FMTSET_BACK = 0xC005BE58, 0xC005BE5C               # the recording-format setter (og3kfmt)
CINEMADNG, MOV = 0, 1
# The video clamp of each donor mode (og3k_plan.CLAMP_*): +0x04 bit 3 and +0x18
# bits 14-15 of the mode's clamp record.  Written out here, independently of the
# plan: the same words Jose Hurtado's fpSup-Formats v0.6.1 declares for modes 98
# and 139 (C0B5C6AC/C6C0, C0B5CE54/CE68), and mode 117's record C0B5CF30.
CLAMP = {'og3k': {0xC0B5C6AC: 0x8, 0xC0B5C6C0: 0xC000,      # mode 98
                  0xC0B5CF34: 0x8, 0xC0B5CF48: 0xC000},     # mode 117 (OG3K100)
         'og2k': {0xC0B5CE54: 0x8, 0xC0B5CE68: 0xC000}}     # mode 139
OGSAVE = 0xC30754CC
PREV = [0xC0BDB9CC, 0xC0BDBC28, 0xC0BDBC60, 0xC0BDBC8C, 0xC0BDBC90, 0xC0BDBC94]
PREV_ON, PREV_OFF = 1334, 1125
KEYBUF = T.STACK - 0x8000                                  # mapped, unused by the loader
UIA_OK, UIA_NO_UI = 0, 2
_BUILT = {}


def built(target):
    """(file bytes, facts) from build_v3_og.py, once per target (it must run in
    its own process: the plan reads OG_TARGET when it is imported)."""
    if target not in _BUILT:
        with tempfile.TemporaryDirectory(prefix='ogv3t-') as t:
            out = pathlib.Path(t) / 'o'
            r = subprocess.run([sys.executable, '-B', str(HERE / 'build_v3_og.py'),
                                '--target', target, '--out', str(out)],
                               capture_output=True, text=True)
            if r.returncode:
                raise RuntimeError(r.stderr[-3000:])
            meta = json.loads((out / 'build.json').read_text())
            _BUILT[target] = ((out / meta['file']).read_bytes(), meta['facts'], meta['file'])
    return _BUILT[target]


def h(s):
    return int(s, 16)


class OGCamera(T.Camera):
    """test_v3's camera; uia_apply and og3krestore inside the sups are stubs."""
    def __init__(self, files, dirs, sups, uia=UIA_OK, **kw):
        super().__init__(files, dirs, **kw)
        self.sups = sups                  # {block size: facts}
        self.uia_result, self.uia_calls, self.restores, self.blocks = uia, [], [], {}
        self.pending = []                 # stubs to plant once their block is read in
        self.restore_saw = []             # were the setter and picker hooked by then
        self.mu.mem_write(SETTER_BACK, struct.pack('<I', 0xE12FFF1E))
        self.by_addr[SETTER_BACK] = 'SETTER_BACK'
        self.mu.mem_write(FMTSET_BACK, struct.pack('<I', 0xE12FFF1E))
        self.by_addr[FMTSET_BACK] = 'FMTSET_BACK'

    def _alloc(self, n, align=8):
        p = super()._alloc(n, align)
        f = self.sups.get(n)
        if f is not None:
            self.blocks[f['label']] = p
            uia = p + (f['uia_apply_off'] & ~1)
            self.by_addr[uia] = ('UIA', f['label'])
            self.pending.append((uia, struct.pack('<H', 0x4770)))          # bx lr (Thumb)
            if f['restore']:
                rst = self.at(f, f['restore'])
                self.by_addr[rst] = ('RESTORE', f['label'])
                self.pending.append((rst, struct.pack('<I', 0xE12FFF1E)))  # bx lr
        return p

    def at(self, f, coord):
        """Where a layout coordinate of sup `f` is, now that its block landed."""
        if isinstance(coord, str):
            coord = h(coord)
        return self.blocks[f['label']] + f['img_off'] + coord - h(f['cave0'])

    def _hook(self, mu, addr, size, data):
        name = self.by_addr.get(addr)
        if name == 'DCACHE' and self.pending:
            # The loader publishes after reading the file in, before the entry.
            # Like test_v3's firmware stubs, each also starts with `bx lr`:
            # unicorn sometimes ignores a PC written from a code hook.
            for at, code in self.pending:
                mu.mem_write(at, code)
            self.pending = []
        if isinstance(name, tuple):
            kind, label = name
            if kind == 'UIA':
                self.uia_calls.append((label, self.r(UC_ARM_REG_R0), self.r(UC_ARM_REG_R1)))
                return self._ret(self.uia_result)
            # og3krestore calls the resolution setter: it must go through the hook
            self.restores.append(label)
            self.restore_saw.append(self.w(SETTER) != T.word(self.img, SETTER)
                                    and self.w(PICKER) != T.word(self.img, PICKER))
            return self._ret(0)
        return super()._hook(mu, addr, size, data)


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


@unittest.skipIf(T.Uc is None or not T.IMAGE.exists(), 'needs unicorn and the image')
class OpenGateV3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.og3k, cls.f3, cls.n3 = built('og3k')
        cls.og2k, cls.f2, cls.n2 = built('og2k')
        cls.img = T.IMAGE.read_bytes()

    def stock(self, a):
        return T.word(self.img, a)

    def boot(self, *sups, uia=UIA_OK, stale=None, which=('og3k',), rename=None):
        mine = []
        for t in which:
            data, f, name = (self.og3k, self.f3, self.n3) if t == 'og3k' else \
                            (self.og2k, self.f2, self.n2)
            mine.append(((rename or {}).get(t, name), data, f))
        files, dirs = T.card(*sups, *[(n, d) for n, d, _ in mine])
        cam = OGCamera(files, dirs, {f['block']: f for _, _, f in mine}, uia=uia, stale=stale)
        r0, sp = cam.boot()
        self.assertEqual(sp, T.STACK - 0x1004)
        self.assertEqual(cam.misaligned, [])
        return cam

    def outcome(self, cam, name):
        return {t: c for c, _, _, t in cam.log() if c in ('LOADED', 'RELEASED')}.get(name)

    def claimed(self, f):
        """Memory claims (a resource claim has no bytes and no journal entry)."""
        return {h(c['address']): c for c in f['claims_list'] if c['bytes']}

    def test_the_shared_qs_resource_is_claimed(self):
        """uishare QS_SHARE.md §9: UIS_RES_QSCUR, SHARED_UI -- without it uia_apply
        refuses QS_OPTION (camera 2026-10-07, UIA_HOOK at op 37)."""
        cam = self.boot()
        st = cam.state()
        res = [struct.unpack('<IIBBBB', cam.mu.mem_read(st + T.O_CLAIMS + 12 * i, 12))
               for i in range(cam.w(st + T.O_NCLAIMS))]
        self.assertIn((0x55435351, 0, 3), [(a, n, k) for a, n, k, _, r, _ in res if r])

    # ---- loaded ----------------------------------------------------------
    def check_loaded(self, cam, f, name):
        self.assertEqual(self.outcome(cam, name), 'LOADED')
        j = {a: (n, data) for a, n, data in cam.journal()}
        for a, c in self.claimed(f).items():
            self.assertIn(a, j, hex(a))
            self.assertEqual(j[a][0], c['bytes'])
            self.assertEqual(j[a][1], self.img[a - 0xC0000000:a - 0xC0000000 + c['bytes']],
                             f'{a:#x}: journal holds the reference image')
        lo, hi = T.cave.CAVE_ARENA, T.cave.CAVE_ARENA_END
        for hk in f['hooks_list']:
            site, to = h(hk['site']), h(hk['to'])
            word = cam.w(site)
            if hk['kind'] == 'Thumb B.W':
                ven = thumb_target(site, word)
                self.assertEqual(cam.w(ven), 0xF000F8DF, hex(site))
                self.assertEqual(cam.w(ven + 4), cam.at(f, to) | 1, hex(site))
            else:
                op = 0xEB000000 if hk['kind'] == 'BL' else 0xEA000000
                self.assertEqual(word & 0xFF000000, op, hex(site))
                ven = branch_target(site, word)
                self.assertEqual(cam.w(ven), 0xE51FF004, hex(site))
                self.assertEqual(cam.w(ven + 4), cam.at(f, to), hex(site))
            self.assertTrue(lo <= ven < hi and ven % 8 == 0, f'{site:#x} veneer {ven:#x}')
        return j

    def test_og3k_loads_claims_relocates_hooks_and_restores(self):
        cam = self.boot()
        self.check_loaded(cam, self.f3, self.n3)
        self.assertEqual(cam.restores, ['OG3K'], 'restore once')
        self.assertEqual(cam.restore_saw, [True], 'after the hooks')
        # the format table's key pointers now name the keys where they landed
        f, table = self.f3, cam.at(self.f3, self.f3['table'])
        for n, key in enumerate(f['fmt_keys']):
            e = table + 48 * n
            self.assertEqual(cam.w(e + 0x0C), e + 0x14, key)
            self.assertEqual(cam.cstr(e + 0x14, 16), key)
        self.assertEqual(cam.w(table + 48 * len(f['fmt_keys']) + 0x14), 0, 'terminator')

    def test_og2k_loads_too(self):
        cam = self.boot(which=('og2k',))
        self.check_loaded(cam, self.f2, self.n2)
        self.assertEqual(cam.restores, ['OG2K'])

    def test_the_ui_block_carries_one_qs_option_named_after_the_file(self):
        from ui import fpui
        cam = self.boot()
        (label, at, n), = cam.uia_calls
        f = self.f3
        self.assertEqual((label, at), ('OG3K', cam.blocks['OG3K'] + f['fpui_off']))
        self.assertEqual(n, f['fpui'])
        blk = bytes(cam.mu.mem_read(at, n))
        strings, ops, frag = fpui.decode(blk)              # checks the hash
        self.assertFalse(any(c == fpui.OP_STRBASE for c, _ in ops))
        qs = [a for c, a in ops if c == fpui.OP_QS_OPTION]
        self.assertEqual(len(qs), 1)
        names = [s for s, _ in strings]
        self.assertEqual(f['images'], ['30OG3K_QS', '30OG3K_SET', '30OG3K_FONT'])
        for i in f['images']:
            self.assertIn(i, names)
            self.assertIn(i.encode() + b'\0', bytes(frag), 'the pack names its image the same')
        self.assertEqual(qs[0][1], 4, 'enum 4: what og3ksel / og3krestore expect')
        self.assertEqual(self.f3['enum'], 4)
        self.assertEqual(self.f2['enum'], 7, 'OG2K has its own value, so both fit on one card')

    def test_og2k_names_its_own_images(self):
        self.assertEqual(self.f2['images'], ['30OG2K_QS', '30OG2K_SET', '30OG2K_FONT'])

    def test_no_qs_site_is_claimed_exclusively(self):
        for f in (self.f3, self.f2):
            excl = {c['address'] for c in f['claims_list'] if c['kind'] == 'EXCL'}
            for site in ('0xC05E6400', '0xC05D90F0', '0xC05E84D8'):
                self.assertNotIn(site, excl)

    def test_power_off_puts_every_claimed_word_back(self):
        cam = self.boot()
        cam.power_off()
        for a, c in self.claimed(self.f3).items():
            n = c['bytes']
            self.assertEqual(bytes(cam.mu.mem_read(a, n)),
                             self.img[a - 0xC0000000:a - 0xC0000000 + n], hex(a))

    def test_a_hook_left_by_last_boot_is_repaired_then_armed(self):
        stale = {PICKER: 0xEA0DEAD0, SETTER: 0xEA0DEAD1, PREV[0]: PREV_ON}
        cam = self.boot(stale=stale)
        self.check_loaded(cam, self.f3, self.n3)
        repaired = {a for c, a, _, t in cam.log() if c == 'REPAIRED'}
        self.assertEqual(repaired, set(stale))
        self.assertEqual(cam.w(PREV[0]), PREV_OFF)

    # ---- the payloads run where they landed -------------------------------
    def test_the_picker_finds_our_key_through_its_hook(self):
        cam = self.boot()
        f = self.f3
        cam.mu.mem_write(KEYBUF, b'OG3K30\0\0')
        donor = h(f['donor_timing'])
        r0, _ = cam.call(PICKER, r0=0, r1=TAB3, r2=KEYBUF)
        table = cam.at(f, f['table'])
        n = f['fmt_keys'].index('OG3K30')
        self.assertEqual(r0, table + 48 * n, 'the entry, where the block landed')
        self.assertEqual(cam.w(r0 + 0x0C), r0 + 0x14)
        self.assertEqual(cam.w(r0 + 0x10), donor, 'the donor timing record')
        self.assertEqual((cam.w(donor + 4), cam.w(donor + 8)),
                         (cam.w(r0 + 0x24), cam.w(r0 + 0x28)), 'timing written')
        cam.power_off()
        self.assertEqual((cam.w(donor + 4), cam.w(donor + 8)),
                         (self.stock(donor + 4), self.stock(donor + 8)))

    def test_the_setter_switches_the_groups_and_publishes_the_flag(self):
        cam = self.boot()
        f = self.f3
        flag, latch = cam.at(f, f['flag']), cam.at(f, f['fmtlatch'])
        self.assertEqual(cam.w(latch), 0xFFFFFFFF, 'format unknown until restore')
        cam.call(SETTER, r0=0, r1=4, r2=1)                 # OG chosen, format unknown
        self.assertEqual(cam.w(OGSAVE), 4, 'OGSAVE keeps the chosen OG enum (OG_SAVE_ENUM)')
        self.assertEqual(cam.w(flag), 0)
        self.assertEqual([cam.w(a) for a in PREV], [PREV_OFF] * 6)
        cam.put(latch, 0)                                  # CinemaDNG
        cam.call(SETTER, r0=0, r1=4, r2=1)
        self.assertEqual(cam.w(flag), 1)
        self.assertEqual([cam.w(a) for a in PREV], [PREV_ON] * 6)
        cam.call(SETTER, r0=0, r1=2, r2=1)                 # FHD
        self.assertEqual((cam.w(flag), cam.w(OGSAVE)), (0, 0))
        self.assertEqual([cam.w(a) for a in PREV], [PREV_OFF] * 6)
        cam.call(SETTER, r0=0, r1=4, r2=1)
        cam.power_off()                                    # selected at power-off
        self.assertEqual([cam.w(a) for a in PREV], [PREV_OFF] * 6, 'stock again')

    # ---- released: nothing written ----------------------------------------
    def assert_released_clean(self, cam, f, name, held=()):
        self.assertEqual(self.outcome(cam, name), 'RELEASED')
        self.assertEqual(cam.restores, [])
        for hk in f['hooks_list']:
            a = h(hk['site'])
            if a not in held:
                self.assertEqual(cam.w(a), self.stock(a), f'{a:#x} written')
        self.assertEqual(sorted(j[0] for j in cam.journal()), sorted(held))

    def other(self, sid, *rows):
        return T.test_sup(sid, [(a, self.stock(a), k, new) for a, k, new in rows])

    def test_a_hook_site_held_exclusively_by_another_releases_with_nothing_written(self):
        o = self.other('OTHR', (PICKER, 2, 0))             # EXCL: no layer may join
        cam = self.boot(('05OTHER.BIN', o))
        self.assert_released_clean(cam, self.f3, self.n3, held=(PICKER,))
        self.assertEqual(cam.uia_calls, [])
        self.assertEqual(cam.w(T.cave.CAVE_BUMP), T.cave.CAVE_ARENA, 'cave taken')

    def test_a_runtime_word_held_by_another_releases(self):
        o = self.other('OTHR', (PREV[3], 2, 0))
        cam = self.boot(('05OTHER.BIN', o))
        self.assert_released_clean(cam, self.f3, self.n3, held=(PREV[3],))

    def test_the_ui_block_refused_releases_before_any_hook(self):
        cam = self.boot(uia=UIA_NO_UI)
        self.assert_released_clean(cam, self.f3, self.n3)
        self.assertEqual(len(cam.uia_calls), 1)

    def cave_hog(self, n):
        """A sup whose entry only asks svc->cave_alloc for n bytes."""
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
        n = T.cave.CAVE_ARENA_END - T.cave.CAVE_ARENA - 8 * 13   # 13 veneers' room, 14 needed
        cam = self.boot(('05HOG.BIN', self.cave_hog(n)))
        self.assertEqual(self.outcome(cam, '05HOG.BIN'), 'LOADED')
        self.assert_released_clean(cam, self.f3, self.n3)
        self.assertEqual(cam.uia_calls, [], 'the UI before the cave')

    def test_a_layer_below_gets_what_is_not_ours(self):
        """OG_CHAIN: another sup's CHAIN layer on the picker sits below OpenGate;
        a key that is not OpenGate's goes down to it, ours is answered here."""
        below = 0xC0100000                                   # r0 = 0x55, return
        hooked = 0xEA000000 | (((below - PICKER - 8) >> 2) & 0xFFFFFF)
        o = self.other('OTHR', (PICKER, 1, hooked))
        cam = self.boot(('05OTHER.BIN', o))
        self.assertEqual(self.outcome(cam, self.n3), 'LOADED')
        cam.mu.mem_write(below, struct.pack('<2I', 0xE3A00055, 0xE12FFF1E))
        cam.mu.mem_write(KEYBUF, b'UHD30\0\0\0')
        r0, _ = cam.call(PICKER, r0=0, r1=TAB3, r2=KEYBUF)
        self.assertEqual(r0, 0x55, 'not ours: passed down')
        cam.mu.mem_write(KEYBUF, b'OG3K30\0\0')
        r0, _ = cam.call(PICKER, r0=0, r1=TAB3, r2=KEYBUF)
        f = self.f3
        self.assertEqual(r0, cam.at(f, f['table']) + 48 * f['fmt_keys'].index('OG3K30'))

    def test_an_inactive_layer_leaves_the_shared_words_alone(self):
        """OG_CHAIN: leaving is undoing what this layer did; not active -> nothing
        written (another layer may have just set the preview heights)."""
        cam = self.boot()
        for a in PREV:
            cam.put(a, 0x999)                                 # as another active layer left them
        cam.call(SETTER, r0=0, r1=2, r2=1)                    # FHD; OG3K was never active
        self.assertEqual([cam.w(a) for a in PREV], [0x999] * 6)

    def test_og3k_and_og2k_on_one_card_both_load_and_each_answers_its_own(self):
        cam = self.boot(which=('og2k', 'og3k'))                # 30OG2K first: OG3K is outer
        self.assertEqual(self.outcome(cam, self.n2), 'LOADED')
        self.check_loaded(cam, self.f3, self.n3)                # the sites hold the outer layer
        self.assertEqual(sorted(cam.restores), ['OG2K', 'OG3K'])
        for key, f in (('OG3K30', self.f3), ('OG2K30', self.f2), ('OG2K60', self.f2)):
            cam.mu.mem_write(KEYBUF, key.encode().ljust(8, b'\0'))
            r0, _ = cam.call(PICKER, r0=0, r1=TAB3, r2=KEYBUF)
            self.assertEqual(r0, cam.at(f, f['table']) + 48 * f['fmt_keys'].index(key), key)
        cam.power_off()
        for a in PREV + [PICKER, SETTER]:
            self.assertEqual(cam.w(a), self.stock(a), hex(a))

    def switch_both(self, rename=None):
        """OG3K and OG2K on one card, CinemaDNG: walk FHD -> OG3K -> OG2K -> OG3K ->
        FHD and check, after each step, which layer is live and that the shared
        preview heights belong to it -- in either card order (the outer layer runs
        first, so a leaving layer can run after the one just entered)."""
        order = 'og3k first' if rename else 'og2k first'
        cam = self.boot(which=('og2k', 'og3k'), rename=rename)
        f3, f2 = self.f3, self.f2
        fl3, fl2 = cam.at(f3, f3['flag']), cam.at(f2, f2['flag'])
        cam.put(cam.at(f3, f3['fmtlatch']), 0)
        cam.put(cam.at(f2, f2['fmtlatch']), 0)
        for enum, want in ((2, (0, 0)), (4, (1, 0)), (7, (0, 1)), (4, (1, 0)), (7, (0, 1)), (2, (0, 0))):
            cam.call(SETTER, r0=0, r1=enum, r2=1)
            self.assertEqual((cam.w(fl3), cam.w(fl2)), want, f'{order} enum {enum}: flags')
            self.assertEqual(cam.w(OGSAVE), enum if enum in (4, 7) else 0, f'{order} enum {enum}: OGSAVE')
            on = PREV_ON if any(want) else PREV_OFF
            self.assertEqual([cam.w(a) for a in PREV], [on] * 6, f'{order} enum {enum}: preview heights')
            # each layer's own clamp follows its own flag, whichever layer runs last
            self.assertEqual((self.clamp(cam, 'og3k'), self.clamp(cam, 'og2k')),
                             tuple('on' if x else 'off' for x in want), f'{order} enum {enum}: clamp')
        cam.call(SETTER, r0=0, r1=7, r2=1)                   # OG2K live at power-off
        cam.power_off()
        self.assertEqual([cam.w(a) for a in PREV], [PREV_OFF] * 6)
        self.assertEqual((self.clamp(cam, 'og3k'), self.clamp(cam, 'og2k')), ('off', 'off'))

    def test_switching_between_og3k_and_og2k_og2k_file_first(self):
        self.switch_both()                                   # 30OG2K < 30OG3K: OG3K outer

    def test_switching_between_og3k_and_og2k_og3k_file_first(self):
        self.switch_both(rename={'og3k': '29OG3K.BIN'})      # OG3K loads first: OG2K outer

    # ---- the video clamp (2026-10-07) --------------------------------------
    def clamp(self, cam, target):
        """'on' when every clamp word of the target is stock | its bits, 'off' when
        every one is stock; anything else is a failure."""
        got = {a: cam.w(a) for a in CLAMP[target]}
        if all(v == self.stock(a) for a, v in got.items()):
            return 'off'
        if all(v == self.stock(a) | b for (a, v), b in zip(got.items(), CLAMP[target].values())):
            return 'on'
        return {hex(a): hex(v) for a, v in got.items()}

    def test_the_clamp_words_are_the_donor_modes_and_claimed_exclusively(self):
        for target, f in (('og3k', self.f3), ('og2k', self.f2)):
            self.assertEqual({h(c['address']) for c in f['clamp_words']}, set(CLAMP[target]), target)
            for a, bits in CLAMP[target].items():
                self.assertEqual(self.stock(a) & bits, 0, f'{a:#x}: stock already has the clamp')
            # a stock video mode (106, FHD30) has exactly these bits: the reference
            rec106 = 0xC0B5C638 + 0x38 * [T.word(self.img, 0xC0B59500 + 0x20 * i)
                                          for i in range(70)].index(106)
            self.assertEqual(T.word(self.img, rec106) , 106)
            self.assertEqual(T.word(self.img, rec106 + 4) & 8, 8)
            self.assertEqual(T.word(self.img, rec106 + 0x18) & 0xC000, 0xC000)
            claims = self.claimed(f)
            for a in CLAMP[target]:
                self.assertEqual(claims[a]['kind'], 'EXCL', f'{target} {a:#x}')
                self.assertFalse(claims[a]['writes'], 'claim only: the payloads write it')

    def test_the_clamp_is_on_only_while_the_og_is_live(self):
        cam = self.boot()
        f = self.f3
        flag, latch = cam.at(f, f['flag']), cam.at(f, f['fmtlatch'])
        self.assertEqual(self.clamp(cam, 'og3k'), 'off', 'after load')
        cam.call(SETTER, r0=0, r1=4, r2=1)                 # chosen, format unknown: not live
        self.assertEqual((cam.w(flag), self.clamp(cam, 'og3k')), (0, 'off'))
        cam.put(latch, CINEMADNG)
        cam.call(SETTER, r0=0, r1=4, r2=1)
        self.assertEqual((cam.w(flag), self.clamp(cam, 'og3k')), (1, 'on'))
        cam.call(FMTSET, r0=0, r1=MOV, r2=1)               # MOV: og3kfmt takes the OG down
        self.assertEqual((cam.w(flag), self.clamp(cam, 'og3k')), (0, 'off'))
        self.assertEqual([cam.w(a) for a in PREV], [PREV_OFF] * 6)
        cam.call(FMTSET, r0=0, r1=CINEMADNG, r2=1)         # back to CinemaDNG: live again
        self.assertEqual((cam.w(flag), self.clamp(cam, 'og3k')), (1, 'on'))
        cam.call(SETTER, r0=0, r1=3, r2=1)                 # UHD
        self.assertEqual((cam.w(flag), self.clamp(cam, 'og3k')), (0, 'off'))
        cam.call(SETTER, r0=0, r1=4, r2=1)
        self.assertEqual(self.clamp(cam, 'og3k'), 'on')
        cam.power_off()                                    # live at power-off
        self.assertEqual(self.clamp(cam, 'og3k'), 'off', 'stock again')

    def test_a_clamp_word_held_by_another_releases(self):
        a = next(iter(CLAMP['og3k']))
        o = self.other('OTHR', (a, 2, 0))
        cam = self.boot(('05OTHER.BIN', o))
        self.assert_released_clean(cam, self.f3, self.n3, held=(a,))

    def test_lossless_then_opengate_both_load(self):
        sys.path.insert(0, str(ROOT / 'fpSup' / 'lossless'))
        import build_v3_lossless as L
        with tempfile.TemporaryDirectory(prefix='ogv3l-') as t:
            loss, _ = L.sup_file(pathlib.Path(t))
        cam = self.boot(('10LOSS.BIN', loss))
        self.assertEqual(self.outcome(cam, '10LOSS.BIN'), 'LOADED')
        self.check_loaded(cam, self.f3, self.n3)


if __name__ == '__main__':
    unittest.main()
