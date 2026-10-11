"""Install Jose Hurtado's exact monitor releases with the published boot pairs.

The firmware file/UI/task services are the existing declared test doubles.
The loader and both product entries execute their real ARM/Thumb bytes. This
checks installation, claim chaining and restoration, not image processing,
touch events, recording, worker scheduling or physical display outputs.
"""
import base64
import hashlib
import json
import re
import struct
import sys
import unittest

from . import build_v3 as B
from . import test_boot_options as BO
from . import test_v3 as T

sys.path.insert(0, str(B.FPSUP / 'uishare/tab'))
import test_ft6 as F6

PICTURE = 0xC02E828C
ORIGINALS = {
    'desqueeze': ('fpsup-desqueeze-v0.1.4test', '41DSQZ.BIN', 'DSQZ',
                  'cddf6da4b3dac81ac158e5a04dcc8b9ec4e9579dc5ca1fe0773366d4c1883448'),
    'tap-to-zoom': ('fpsup-tap-to-zoom-v0.1.0test', '42TAPZ.BIN', 'TAPZ',
                    '7eb0be22dbc5eca86876e05fcfe039268a40cfb89f24a8933138d5ba0fe8156a'),
}


def catalogue():
    page = (B.FPSUP / 'tools/merge-v3/index.html').read_text()
    return json.loads(re.search(r'<script id="cat"[^>]*>(.*?)</script>', page, re.S).group(1))


class Camera(F6.Cam):
    def __init__(self, cat, ids, key='i0f0', reverse=False, blocker=False):
        pair = cat['boot']['variants'][key]['files']
        files = {'\\' + f['path'].replace('/', '\\'): base64.b64decode(f['data'])
                 for f in pair + cat['shared'][2:]}
        entries = [('LOADER.BIN', 0x20, len(files['\\fpSup\\LOADER.BIN']))]
        if key.startswith('m1'):
            for f in cat['boot']['manager_files']:
                files['\\' + f['path'].replace('/', '\\')] = base64.b64decode(f['data'])
        for p in cat['products']:
            if p['id'] in ids:
                data = base64.b64decode(p['data'])
                files['\\fpSup\\' + p['file']] = data
                entries.append((p['file'], 0x20, len(data)))
        if blocker:
            data = T.test_sup('TAKE', [(PICTURE, T.word(T.IMAGE.read_bytes(), PICTURE), 2, T.NOP)])
            files['\\fpSup\\01TAKE.BIN'] = data
            entries.append(('01TAKE.BIN', 0x20, len(data)))
        super().__init__(files, {'\\fpSup': entries[::-1] if reverse else entries})
        ar = base64.b64decode(pair[0]['data'])
        for addr, value in re.findall(rb'^mem set (0x[0-9A-Fa-f]+) (0x[0-9A-Fa-f]+)', ar, re.M):
            self.put(int(addr, 16), int(value, 16))
        self.put(BO.TABLE + 0x21C, 0)  # no AutoRun callback is active in this scenario
        self.mu.hook_add(T.UC_HOOK_CODE, self.strict_firmware)

    def strict_firmware(self, mu, addr, size, data):
        declared = {F6.NBR_LOAD, F6.VAR_REGISTER, F6.VAR_SUBSCRIBE,
                    F6.POST_INT, F6.POST_STR, F6.F_RENAME}
        if (0xC0000000 <= addr < 0xC3000000 and addr not in self.by_addr and
                addr not in declared and not T.CAVE_LOW <= addr < 0xC072F900):
            self.error = AssertionError(f'unmocked firmware execution at 0x{addr:08X}')
            mu.emu_stop()


class OriginalPayloadTests(unittest.TestCase):
    def test_exact_original_headers_and_author(self):
        cat = catalogue()
        for product, (release, name, sid, expected) in ORIGINALS.items():
            with self.subTest(product=product):
                p = next(p for p in cat['products'] if p['id'] == product)
                data = (B.FPSUP / 'releases' / release / 'fpSup' / name).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(), expected)
                self.assertEqual(base64.b64decode(p['data']), data)
                self.assertEqual(p['author'], 'Jose Hurtado')
                magic, hlen, flen, block, entry, ident, version, svc = struct.unpack_from('<8I', data)
                self.assertEqual((magic, hlen, flen), (B.SL_MAGIC, B.SL_HEADER_LEN, len(data)))
                self.assertGreaterEqual(block, flen)
                self.assertTrue(hlen <= (entry & ~1) < flen)
                self.assertEqual(ident.to_bytes(4, 'little').decode(), sid)
                self.assertLessEqual(svc, B.SL_SVC_VERSION)


@unittest.skipIf(T.Uc is None or not T.IMAGE.exists(), 'needs unicorn and firmware image')
class MonitorInstallationTests(unittest.TestCase):
    def boot(self, ids, **options):
        cam = Camera(catalogue(), ids, **options)
        _, sp = cam.boot()
        self.assertEqual(sp, T.STACK - 0x1004)
        self.assertEqual(cam.misaligned, [])
        loaded = [name for code, _, _, name in cam.log() if code == 'LOADED']
        expected = [ORIGINALS[p][1] for p in ORIGINALS if p in ids]
        self.assertEqual([name for name in loaded if name in expected], expected)
        self.assertFalse(any(code == 'RELEASED' and name in expected
                             for code, _, _, name in cam.log()))
        if 'tap-to-zoom' in ids:
            self.assertNotEqual(cam.w(PICTURE), T.word(cam.img, PICTURE))
        return cam

    def assert_restored(self, cam, journal):
        self.assertTrue(journal)
        for addr, length, stock in journal:
            self.assertEqual(bytes(cam.mu.mem_read(addr, length)), stock, f'0x{addr:08X}')

    def test_each_original_installs_and_restores(self):
        for product in ORIGINALS:
            with self.subTest(product=product):
                cam = self.boot([product])
                journal = cam.journal()  # save it before power-off; avoid an empty-list pass
                self.assertTrue(any(addr <= PICTURE < addr + length for addr, length, _ in journal))
                cam.power_off()
                self.assert_restored(cam, journal)

    def test_pair_with_all_published_boot_choices(self):
        cat = catalogue()
        for key in cat['boot']['variants']:
            with self.subTest(key=key):
                cam = self.boot(list(ORIGINALS), key=key)
                if key.startswith('m1'):
                    self.assertTrue(any(code == 'LOADED' and name == 'LOADER.BIN'
                                        for code, _, _, name in cam.log()))
                st = cam.state()
                delta = 4 if cam.w(st) == 4 else 0
                claims = [struct.unpack('<IIBBBx', cam.mu.mem_read(st + T.O_CLAIMS + delta + 12 * i, 12))
                          for i in range(cam.w(st + T.O_NCLAIMS + delta))]
                shared = [c for c in claims if c[0] == PICTURE and not c[4]]
                self.assertEqual(len(shared), 2)
                self.assertTrue(all(c[1] == 4 and c[2] == 1 for c in shared), 'both picture claims are CHAIN')
                journal = cam.journal()
                cam.power_off()
                self.assert_restored(cam, journal)

    def test_reversed_directory_preserves_filename_chain_order(self):
        cam = self.boot(list(ORIGINALS), reverse=True)
        journal = cam.journal()
        cam.power_off()
        self.assert_restored(cam, journal)

    def test_exclusive_picture_owner_releases_both_without_hooks(self):
        cam = Camera(catalogue(), list(ORIGINALS), blocker=True)
        cam.boot()
        released = [name for code, _, _, name in cam.log() if code == 'RELEASED']
        self.assertEqual(released, [v[1] for v in ORIGINALS.values()])
        self.assertEqual(cam.w(PICTURE), T.NOP)
        self.assertEqual(cam.tasks, [])
        journal = cam.journal()
        cam.power_off()
        self.assert_restored(cam, journal)

    def test_restore_assertion_detects_noop_poweroff_mutation(self):
        cam = self.boot(list(ORIGINALS))
        journal = cam.journal()
        callback = cam.w(cam.w(cam.state() + T.O_POFF) + 12)
        # Mutate only this emulator: the published files and source stay intact.
        cam.mu.mem_write(callback & ~1, struct.pack('<H', 0x4770) if callback & 1
                         else struct.pack('<I', 0xE12FFF1E))
        cam.power_off()
        with self.assertRaises(AssertionError):
            self.assert_restored(cam, journal)


if __name__ == '__main__':
    unittest.main()
