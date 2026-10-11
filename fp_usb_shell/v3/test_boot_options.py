"""Run the actual v3 entry inside the shared Instant/Fast boot envelope.
Firmware I/O, allocator and UI are stubbed as in test_v3; ARM/C code is real.
This proves control flow and saved bytes, not hardware timing or flash commit.
"""
import pathlib
import base64
import hashlib
import json
import re
import struct
import unittest

from . import build_v3 as B
from . import test_v3 as T

SITE, SITE_STOCK = 0xC03DA420, 0xEB0000CC
STORE, BOOT_AT = 0xC3075264, 0xC072F700
ECHO, ECHO_STOCK, ABORT = 0xC0BAC2F8, 0xC03D99A0, 0xC072F080
TABLE, LINE, POP = 0xC2F20FC0, 0xC03DA7A8, 0xC0420D90
CTX, FOBJ = 0xC3010000, 0xC3010200
_built = {}


def built(instant, fast, manager=False):
    key = instant, fast, manager
    if key not in _built:
        _built[key] = B.boot_card(instant=instant, fast=fast, allsups=manager)
    return _built[key]


class Camera(T.Camera):
    def __init__(self, ar, blob, active=False):
        patch = T.test_sup('TEST', [(T.SITE_A, T.word(T.IMAGE.read_bytes(), T.SITE_A), 2, T.NOP)])
        super().__init__({'\\fpSup\\LOADER.BIN': blob, '\\fpSup\\10TEST.BIN': patch},
                         {'\\fpSup': [('LOADER.BIN', 0x20, len(blob)), ('10TEST.BIN', 0x20, len(patch))]},
                         autorun=ar)
        self.files.update({f'\\fpSup\\UI\\{i}.BIN': px for i, px in enumerate(B.splash_frames())})
        self.put(T.DRAW, T.DRAW_PAUSED)              # actual cold AutoRun pauses redraw
        for a, v in re.findall(rb'^mem set (0x[0-9A-Fa-f]+) (0x[0-9A-Fa-f]+)', ar, re.M):
            a, v = int(a, 16), int(v, 16)
            if BOOT_AT <= a < BOOT_AT + 0x100:
                self.put(a, v)
        self.by_addr[POP] = 'AR_POP'
        self.put(POP, 0xE12FFF1E)
        self.fallback = None
        self.put(TABLE + 0x21C, 2 if active else 0)
        self.put(TABLE + 36 + 4, 0xC03DA158)
        self.put(TABLE + 72 + 4, LINE)
        self.put(TABLE + 72 + 12, CTX)
        self.put(CTX + 0x90, 1 if active else 0)
        self.put(CTX + 0x94, FOBJ if active else 0)

    def _hook(self, mu, addr, size, data):
        if addr == T.F['D_FILE']:
            path = self.cstr(self.w(self.r(T.UC_ARM_REG_R2)))
            if path not in self.files:
                raise AssertionError('artwork path absent from card: ' + path)
        if addr == POP:
            self.calls.append('AR_POP')
            self.put(TABLE + 0x21C, self.w(TABLE + 0x21C) - 1)
            return self._ret(0)
        if addr == T.F['AR_START']:
            self.fallback = tuple(self.r(x) for x in (T.UC_ARM_REG_R0, T.UC_ARM_REG_R1, T.UC_ARM_REG_LR))
        return super()._hook(mu, addr, size, data)

    def power_off_all(self):
        for obj in dict.fromkeys(o for o, _ in self.registered):
            self.call(self.w(self.w(obj) + 12), r0=obj, r1=4)


@unittest.skipIf(T.Uc is None or not T.IMAGE.exists(), 'needs unicorn and firmware image')
class BootOptionsTests(unittest.TestCase):
    def test_merge_embeds_the_exact_current_builder_pairs(self):
        page = (B.FPSUP / 'tools/merge-v3/index.html').read_text()
        cat = json.loads(re.search(r'<script id="cat"[^>]*>(.*?)</script>', page, re.S).group(1))
        for manager in (False, True):
            for instant in (False, True):
                for fast in (False, True):
                    ar, blob, _ = built(instant, fast, manager)
                    key = ('m1' if manager else '') + f'i{int(instant)}f{int(fast)}'
                    variant = cat['boot']['variants'][key]
                    for meta, expected in zip(variant['files'], (ar, blob)):
                        self.assertEqual(base64.b64decode(meta['data']), expected)
                        self.assertEqual(meta['sha256'], hashlib.sha256(expected).hexdigest())
                        self.assertEqual(meta['size'], len(expected))
        import sys
        sys.path.insert(0, str(B.FPSUP / 'uishare/tab'))
        import build_ft6
        data, _ = build_ft6.data_file()
        self.assertEqual(base64.b64decode(cat['boot']['manager_files'][0]['data']), data)

    def test_four_options_load_real_v3_and_restore_products(self):
        for instant in (False, True):
            for fast in (False, True):
                with self.subTest(instant=instant, fast=fast):
                    ar, blob, _ = built(instant, fast)
                    cam = Camera(ar, blob, active=True)
                    before = bytes(cam.mu.mem_read(STORE, 512))
                    r, sp = cam.boot()
                    self.assertEqual(sp, T.STACK - 0x1004)
                    self.assertEqual(cam.misaligned, [])
                    self.assertEqual(cam.w(T.SITE_A), T.NOP)
                    self.assertEqual(cam.log()[-1][:2], ('DONE', 1))
                    self.assertEqual(cam.w(SITE) != SITE_STOCK, instant)
                    if fast:
                        loader = b''.join(struct.pack('<I', v) for a, v in sorted(B.loader_words(ar).items()))
                        self.assertEqual(bytes(cam.mu.mem_read(STORE + 4, len(loader))), loader)
                        self.assertNotEqual(cam.w(STORE), 0)
                        self.assertEqual(cam.w(ECHO), ABORT)
                    else:
                        self.assertEqual(bytes(cam.mu.mem_read(STORE, 512)), before)
                        self.assertEqual(cam.w(ECHO), ECHO_STOCK)
                    cam.power_off_all()
                    self.assertEqual(cam.w(T.SITE_A), T.word(cam.img, T.SITE_A))
                    self.assertEqual(cam.w(SITE) != SITE_STOCK, instant)
                    self.assertEqual(cam.w(T.DRAW), T.DRAW_STOCK)
                    self.assertEqual(cam.slept, 0, 'no fixed completion hold')
                    self.assertNotIn(b'# pad -- see PAD_TO:', ar)

    def test_instant_warm_restart_reloads_sup_and_skips_autorun(self):
        for fast in (False, True):
            ar, blob, _ = built(True, fast)
            cam = Camera(ar, blob)
            cam.boot()
            cam.power_off_all()
            cam.registered.clear()
            cam.heap_next = T.HEAP
            cam.now = 3_100_000                     # timing is not emulated here
            cam.put(TABLE + 0x21C, 0)
            r, sp = cam.call(T.CAVE_LOW + 4, r0=123, r1=456)
            self.assertEqual((r, sp), (0, T.STACK - 0x1004))
            self.assertIsNone(cam.fallback)
            self.assertEqual(cam.log()[-1][:2], ('DONE', 1))
            self.assertEqual(cam.w(T.SITE_A), T.NOP)
            self.assertEqual(cam.w(ECHO), ECHO_STOCK, 'warm path never arms AutoRun abort')
            self.assertEqual(cam.misaligned, [])

    def test_instant_missing_file_preserves_native_fallback_arguments(self):
        ar, blob, _ = built(True, False)
        cam = Camera(ar, blob)
        del cam.files['\\fpSup\\LOADER.BIN']
        _r, sp = cam.call(T.CAVE_LOW + 4, r0=123, r1=456)
        self.assertEqual(cam.fallback, (123, 456, T.DONE))
        self.assertEqual(sp, T.STACK - 0x1004)

    def test_wrong_loader_hook_word_never_arms_instant(self):
        ar, blob, _ = built(True, False)
        cam = Camera(ar, blob)
        cam.put(T.CAVE_LOW + 4, T.NOP)
        cam.boot()
        self.assertEqual(cam.w(SITE), SITE_STOCK)
        self.assertEqual(cam.log()[-1][:2], ('DONE', 1))

    def test_disabling_instant_removes_previous_warm_hook_but_keeps_foreign_site(self):
        for fast in (False, True):
            ar, blob, _ = built(False, fast)
            ours = 0xEB000000 | (((T.CAVE_LOW + 4 - SITE - 8) >> 2) & 0xFFFFFF)
            cam = Camera(ar, blob)
            cam.put(SITE, ours)
            cam.call(T.CAVE_LOW + 4)
            self.assertEqual(cam.w(SITE), SITE_STOCK)
            self.assertEqual(cam.log()[-1][:2], ('DONE', 1))
            foreign = 0xEB012345
            cam = Camera(ar, blob)
            cam.put(SITE, foreign)
            cam.boot()
            self.assertEqual(cam.w(SITE), foreign)

    def test_fast_miss_then_hit_copies_loader_and_closes_script(self):
        for instant in (False, True):
            with self.subTest(instant=instant):
                ar, blob, _ = built(instant, True)
                cam = Camera(ar, blob, active=True)
                before = bytes(cam.mu.mem_read(T.CAVE_LOW, 0x200))
                r, sp = cam.call(BOOT_AT)
                self.assertEqual((r, sp), (0, T.STACK - 0x1004))
                self.assertEqual(bytes(cam.mu.mem_read(T.CAVE_LOW, 0x200)), before)
                self.assertEqual(cam.opened, [], 'miss returns before file I/O')
                cam.boot()                          # same script's normal fallback
                stored = bytes(cam.mu.mem_read(STORE, 512))
                cam.power_off_all()
                cam.registered.clear()
                cam.heap_next = T.HEAP
                cam.put(T.DRAW, T.DRAW_PAUSED)      # short cold AutoRun also pauses
                cam.mu.mem_write(T.CAVE_LOW, bytes(0x200))
                cam.put(SITE, SITE_STOCK)            # cold image, persisted store
                cam.put(TABLE + 0x21C, 2)
                cam.put(CTX + 0x90, 1)
                cam.put(CTX + 0x94, FOBJ)
                r, sp = cam.call(BOOT_AT)
                self.assertEqual(sp, T.STACK - 0x1004)
                self.assertEqual(cam.log()[-1][:2], ('DONE', 1))
                self.assertEqual(bytes(cam.mu.mem_read(STORE, 512)), stored)
                self.assertEqual(cam.w(SITE) != SITE_STOCK, instant)
                self.assertEqual(cam.w(ECHO), ABORT)
                close_before = cam.calls.count('F_CLOSE')
                _r, sp = cam.call(cam.w(ECHO), sp=T.STACK - 0x1004)
                self.assertEqual(sp, T.STACK - 0x1004)
                self.assertEqual(cam.calls.count('F_CLOSE'), close_before + 1)
                self.assertEqual(cam.w(TABLE + 0x21C), 1)
                self.assertEqual(cam.w(CTX + 0x94), 0)
                self.assertEqual(cam.mu.mem_read(CTX + 0x90, 1), b'\0')
                self.assertEqual(cam.w(ECHO), ECHO_STOCK)
                self.assertEqual(cam.misaligned, [])

    def test_manager_saves_complete_envelope_with_disabled_list(self):
        from . import test_allsups as A
        for instant, fast in ((False, False), (True, False), (False, True), (True, True)):
            with self.subTest(instant=instant, fast=fast):
                ar, blob, _ = built(instant, fast, True)
                cam = A.boot(sups=[('10LOSS.BIN', T.test_sup('LOSS', []))], vbin=blob)
                cam.notify('FT_Choice1', 1)
                saved = cam.written[A.SELF_PATH]
                self.assertEqual(A.disabled(saved), ['LOSS'])
                self.assertEqual(saved[:-128], blob[:-128], 'manager keeps stage2, abort, core and zero string pointers')
                self.assertEqual(len(saved), len(blob))
                again = A.boot(sups=[('10LOSS.BIN', T.test_sup('LOSS', []))], vbin=saved)
                self.assertFalse(any(code == 'LOADED' and name == '10LOSS.BIN' for code, _a, _b, name in again.log()))


if __name__ == '__main__':
    unittest.main()
