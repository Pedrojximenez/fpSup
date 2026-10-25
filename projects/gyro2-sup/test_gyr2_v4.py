#!/usr/bin/env python3
"""Gyro2 for Loader v4 with its fpSup-page row (build.build_v4, src/gyr2_row4.c),
under the real v4 core and its fpSup page (fpSup/loader-v4/test_ui_v4's camera).

    python3 -B -m unittest test_gyr2_v4

Checked: it loads cached with its name; the "Gyro2" row is on the fpSup page,
ON on a first install; OFF makes the take start add no tag and the frames
write nothing, latched for the whole take; the choice is written into
GYR2.BIN's own record (and read back) and the next boot starts with it; a
file that is no longer this sup is never written; no change while recording;
the v3 build is byte-for-byte what it was.
Not checked: the camera (UI thread timing, the real file system).
"""
import hashlib, pathlib, struct, sys, unittest

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / 'fpSup' / 'loader-v4'))

import build as G                          # noqa: E402
import test_gyr2 as T2                     # noqa: E402
import test_ui_v4 as U                     # noqa: E402
import test_v4 as T4                       # noqa: E402
from armasm import symbols                 # noqa: E402

PATH = '\\fpSup\\GYR2.BIN'
F_SEEK = 0xC03661E0
MOVREC_DEFAULT = 0xC347E08F
V3_SHA = '2cbfe477bf8b11cc'                # build/40GYR2.BIN, build 6, before the v4 row
_built = {}


def built():
    if not _built:
        sup, info = G.build_v4()
        code4, fn = G.row4_code()
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            blob = pathlib.Path(t) / 'row4.bin'
            blob.write_bytes(code4)
            syms = symbols(G.SRC, defines=['GYR2_V4', f'G2_BIN="{blob}"', f'G2_INSTALL={fn:#x}'])
        _built.update(sup=sup, info=info, syms=syms)
    return _built


class Cam(U.Cam):
    """The v4 fpSup-page camera plus the routines Gyro2 calls (as test_gyr2.Cam),
    a seek, and reads of what was written."""
    def __init__(self, files, dirs):
        super().__init__(files, dirs)
        for a in (T2.MODE_FN, T2.F_TIMING, T2.F_GEOM, T2.F_SUBJECT, T2.F_ATTACH, T2.F_RATE,
                  T2.F_ADD_TAG, F_SEEK):
            self.mu.mem_write(a, struct.pack('<I', 0xE12FFF1E))
        self.by_addr[F_SEEK] = 'F_SEEK'
        self.subject = self._alloc(0x28)
        self.mu.mem_write(self.subject, struct.pack('<10I', *([0xC3498D5C] * 6 + [0] * 4)))
        self.attached, self.added, self.rate = [], [], (24000, 1001)
        self.t_row, self.g_row = self._alloc(0x20), self._alloc(0x60)
        self.mu.mem_write(self.t_row, struct.pack('<IH', 0, 380))
        self.mu.mem_write(self.g_row, struct.pack('<III', 0, 3000, 2000))
        self.mu.mem_write(self.g_row + 0x44, struct.pack('<II', 2, 2))

    def _hook(self, mu, addr, size, data):
        R = T4.T3
        if addr == T2.MODE_FN:
            return self._ret(106)
        if addr in (T2.F_TIMING, T2.F_GEOM):
            return self._ret(self.t_row if addr == T2.F_TIMING else self.g_row)
        if addr == T2.F_SUBJECT:
            return self._ret(self.subject)
        if addr == T2.F_ATTACH:
            subj, obs = self.r(R.UC_ARM_REG_R0), self.r(R.UC_ARM_REG_R1)
            self.attached.append((subj, obs))
            slots = list(struct.unpack('<9I', mu.mem_read(subj, 36)))
            self.put(subj + 4 * slots.index(0), obs)
            return self._ret(0)
        if addr == T2.F_RATE:
            mu.mem_write(self.r(R.UC_ARM_REG_R0), struct.pack('<2I', *self.rate))
            return self._ret(0)
        if addr == T2.F_ADD_TAG:
            sp = self.r(R.UC_ARM_REG_SP)
            count, _ = struct.unpack('<2I', mu.mem_read(sp, 8))
            self.added.append((self.r(R.UC_ARM_REG_R2), count))
            return self._ret(1)
        name = self.by_addr.get(addr)
        if name == 'F_OPEN' and self.r(R.UC_ARM_REG_R2) == 7:      # in place: keep the file
            path = self.cstr(self.r(R.UC_ARM_REG_R1))
            self.written.setdefault(path, self.files.get(path, b''))
            self.fobj[self.r(R.UC_ARM_REG_R0)] = [path, 0]
            return self._ret(1)
        if name == 'F_SEEK':
            self.fobj[self.r(R.UC_ARM_REG_R0)][1] = self.r(R.UC_ARM_REG_R1)
            return self._ret(1)
        if name == 'F_READ':
            fo = self.fobj.get(self.r(R.UC_ARM_REG_R0))
            if fo and fo[0] in self.written:
                path, pos = fo
                n = self.r(R.UC_ARM_REG_R2)
                d = self.written[path][pos:pos + n]
                mu.mem_write(self.r(R.UC_ARM_REG_R1), d)
                fo[1] += len(d)
                if self.r(R.UC_ARM_REG_R3):
                    self.put(self.r(R.UC_ARM_REG_R3), len(d))
                return self._ret(len(d))
        return super()._hook(mu, addr, size, data)


def boot(sup=None):
    b = U.built()
    sup = sup or built()['sup']
    vbin = b['vbin']
    files = {'\\fpSup\\LOADER.BIN': vbin, U.UI_PATH: b['data'], PATH: sup}
    cam = Cam(files, {'\\fpSup': [('LOADER.BIN', 0x20, len(vbin)), ('UI', 0x10, 0),
                                  ('GYR2.BIN', 0x20, len(sup))]})
    cam.boot()
    return cam


def row(cam):
    for k in range(6):
        s = U.slot(cam, k)
        if s['N'] == 'Gyro2':
            return k, s
    raise AssertionError('no Gyro2 row: ' + repr([U.slot(cam, k)['N'] for k in range(6)]))


def var(cam, name):
    blk = T4.blocks(cam)['GYR2.BIN']
    return cam.w(blk + 48 + built()['syms']['vars'] + {'ROWOFF': 176, 'TAKEOFF': 180, 'TAGS': 168}[name])


@unittest.skipIf(T4.Uc is None or not T4.T3.IMAGE.exists(), 'needs unicorn and the image')
class GyroRowTests(unittest.TestCase):
    def test_v3_build_unchanged(self):
        self.assertEqual(hashlib.sha256(G.build()[0]).hexdigest()[:16], V3_SHA)

    def test_header_and_name(self):
        sup = built()['sup']
        h = struct.unpack_from('<12I', sup)
        self.assertEqual((h[0], h[1], h[2], h[7], h[8]), (T4.B.SL4_MAGIC, 48, len(sup), 6, T4.B.SL_F_CACHED_OK))
        self.assertEqual(sup[h[11]:h[11] + 6], b'Gyro2\0')
        self.assertEqual(len(sup) % 8, 0, 'gbuf starts where the file ends')

    def test_loads_cached_with_an_on_row(self):
        cam = boot()
        self.assertIn('GYR2.BIN', T4.blocks(cam))
        self.assertGreaterEqual(T4.blocks(cam)['GYR2.BIN'], 0xC0000000)
        self.assertEqual(len(cam.attached), 1)
        k, s = row(cam)
        self.assertEqual((U.shown(s), s['Default'], s['Tog']), ('On', 1, 1))   # the page's stock Off / On
        self.assertEqual(var(cam, 'ROWOFF'), 0)

    def take(self, cam):
        n = len(cam.added)
        T2.notify(cam, 0, 3)
        return cam.added[n:]

    def test_off_adds_no_tag_and_is_saved_into_its_own_file(self):
        cam = boot()
        k, _ = row(cam)
        self.assertEqual(len(self.take(cam)), 1)                    # ON: our tag
        cam.notify(f'FT_Choice{k}', 0)                             # OFF
        self.assertEqual(var(cam, 'ROWOFF'), 1)
        self.assertEqual(self.take(cam), [])                        # no tag this take
        self.assertEqual(var(cam, 'TAKEOFF'), 1)
        w = cam.written[PATH]
        rec = 48 + built()['syms']['g2_rec']
        self.assertEqual(struct.unpack_from('<4I', w, rec)[:3], (0x54533247, 1, 1))
        sup = built()['sup']
        self.assertEqual(w[:rec], sup[:rec])                        # nothing else moved
        self.assertEqual(w[rec + 16:], sup[rec + 16:])
        again = boot(w)                                             # the next boot: OFF
        self.assertEqual(var(again, 'ROWOFF'), 1)
        self.assertEqual(self.take(again), [])
        again.notify(f'FT_Choice{row(again)[0]}', 1)               # ON again
        self.assertEqual(len(self.take(again)), 1)

    def test_off_mid_take_waits_for_the_next(self):
        cam = boot()
        k, _ = row(cam)
        self.assertEqual(len(self.take(cam)), 1)
        cam.notify(f'FT_Choice{k}', 0)
        self.assertEqual(var(cam, 'TAKEOFF'), 0, 'latched at the take start')
        f = T2.notify(cam, 3, 3)                                    # this take's frame runs on
        self.assertEqual((f['r0'], f['regs_ok']), (1, True))

    def test_a_file_that_is_not_this_sup_is_never_written(self):
        cam = boot()
        k, _ = row(cam)
        cam.files[PATH] = b'FSB4' + bytes(60)                      # replaced on the card
        cam.notify(f'FT_Choice{k}', 0)
        self.assertNotIn(PATH, cam.written)
        self.assertEqual(var(cam, 'ROWOFF'), 1, 'still applies until power-off')

    def test_no_change_while_recording(self):
        cam = boot()
        k, _ = row(cam)
        cam.mu.mem_write(MOVREC_DEFAULT, b'\x01')
        cam.notify(f'FT_Choice{k}', 0)
        self.assertEqual(var(cam, 'ROWOFF'), 0)
        self.assertNotIn(PATH, cam.written)


if __name__ == '__main__':
    unittest.main()
