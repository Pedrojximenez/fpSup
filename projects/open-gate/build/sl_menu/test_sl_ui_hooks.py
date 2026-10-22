"""Offline late-hook transaction tests; no camera or card access."""
from __future__ import annotations

import ctypes as C
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import sl_excl as SLX  # noqa: E402
SOURCE = HERE / 'sl_ui_hooks.c'
SITES = (0xC059B2F8, 0xC059BA10, 0xC05931D0, 0xC059C640, 0xC059C9F0,
         0xC057A6A0, 0xC05824D0, 0xC057A5F0, 0xC056461C, 0xC05E82F0)
STOCK = (0xE92D4070,) * 5 + (0xE92D40F0,) * 3 + (0xEB000005, 0x48F0E92D)
FIXTURE = r'''
#include <stdint.h>
static struct { uint32_t a, v; } cells[256];
static uint32_t n, writes, cache, gate_ok = 1, gate_count, gate_bound;
uint32_t slui_test_read(uintptr_t a) {
    for (uint32_t i = 0; i < n; ++i) if (cells[i].a == a) return cells[i].v;
    return 0;
}
void slui_test_write(uintptr_t a, uint32_t v) {
    for (uint32_t i = 0; i < n; ++i) if (cells[i].a == a) { cells[i].v = v; ++writes; return; }
    cells[n].a = a; cells[n++].v = v; ++writes;
}
void slui_test_publish(void) { ++cache; }
uint32_t slui_test_gate(const uint32_t *pairs, uint32_t count, uint32_t bound) {
    gate_count = count; gate_bound = bound;
    if (count != 10) return 0;
    for (uint32_t i = 0; i < count; ++i)
        if (slui_test_read(pairs[2*i]) != pairs[2*i+1]) return 0;
    return gate_ok;
}
void reset(void) { n = writes = cache = gate_count = gate_bound = 0; gate_ok = 1; }
void seed(uint32_t a, uint32_t v) { slui_test_write(a, v); --writes; }
void allow(uint32_t v) { gate_ok = v; }
uint32_t value(uint32_t a) { return slui_test_read(a); }
uint32_t metric(uint32_t which) {
    return which == 0 ? writes : which == 1 ? cache : which == 2 ? gate_count : gate_bound;
}
'''


class LateHooks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='sl-ui-hooks-')
        fixture = Path(cls.tmp.name) / 'fixture.c'
        fixture.write_text(FIXTURE)
        libfile = Path(cls.tmp.name) / 'hooks.dylib'
        subprocess.run([shutil.which('clang') or 'clang', '-shared', '-fPIC', '-O2',
                        '-std=c11', '-Wall', '-Wextra', '-Werror', '-DSL_UI_HOOK_HOST_TEST',
                        str(SOURCE), str(fixture), '-o', str(libfile)], check=True)
        cls.lib = C.CDLL(str(libfile))
        for name, args, ret in (('reset', [], None), ('seed', [C.c_uint32] * 2, None),
                                ('allow', [C.c_uint32], None), ('value', [C.c_uint32], C.c_uint32),
                                ('metric', [C.c_uint32], C.c_uint32),
                                ('sl_menu_arm', [C.c_uint32, C.POINTER(C.c_uint32), C.c_uint32, C.c_uint32], C.c_uint32)):
            fn = getattr(cls.lib, name)
            fn.argtypes, fn.restype = args, ret

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.lib.reset()
        self.bump = 0xC072E0FC       # arena + 19 core veneers: naturally 4 mod 8
        self.lib.seed(0xC072E060, self.bump)
        for site, stock in zip(SITES, STOCK):
            self.lib.seed(site, stock)
        words = []
        for i, (site, stock) in enumerate(zip(SITES, STOCK)):
            words.extend((site, stock, 0x100 + i * 0x40, 2 if i == 9 else 1 if i == 8 else 0))
        self.hooks = (C.c_uint32 * len(words))(*words)

    def arm(self):
        return self.lib.sl_menu_arm(0x45100000, self.hooks, 0x2800, 128)

    def test_all_veneers_precede_all_sites(self):
        self.assertEqual(self.arm(), 1)
        self.assertEqual(self.lib.metric(2), 10)
        self.assertEqual(self.lib.metric(3), 128)
        self.assertEqual(self.lib.value(0xC072E060), self.bump + 80)
        self.assertEqual(self.lib.metric(1), 2)
        for i, site in enumerate(SITES):
            veneer = self.bump + i * 8
            self.assertEqual(self.lib.value(veneer), 0xF000F8DF if i == 9 else 0xE51FF004)
            self.assertEqual(self.lib.value(veneer + 4), 0x45100100 + i * 0x40 | (1 if i == 9 else 0))
            patched = self.lib.value(site)
            if i == 9:
                self.assertEqual(patched, SLX._bw(site, veneer))
            elif i == 8:
                self.assertEqual(patched, SLX._bl(site, veneer))
            else:
                self.assertEqual(patched, SLX._b(site, veneer))

    def test_gate_refusal_writes_nothing(self):
        self.lib.allow(0)
        self.assertEqual(self.arm(), 0)
        self.assertEqual((self.lib.metric(0), self.lib.metric(1)), (0, 0))
        self.assertEqual(self.lib.value(0xC072E060), self.bump)

    def test_nonstock_site_writes_nothing(self):
        self.lib.seed(SITES[3], 0)
        self.assertEqual(self.arm(), 0)
        self.assertEqual((self.lib.metric(0), self.lib.metric(1), self.lib.metric(2)), (0, 0, 0))

    def test_cave_room_refusal_writes_nothing(self):
        self.lib.seed(0xC072E060, 0xC072EFB4 - 72)
        self.assertEqual(self.arm(), 0)
        self.assertEqual((self.lib.metric(0), self.lib.metric(1), self.lib.metric(2)), (0, 0, 0))


if __name__ == '__main__':
    unittest.main()
