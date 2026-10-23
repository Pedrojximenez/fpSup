"""Full-zero semantics and bounds for the word-at-a-time REC state reset."""
import ctypes as C
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
WRAPPERS = '''#include "state_memory.h"
void clear(void *p, uint32_t n) { fpl_state_clear(p, n); }
uint32_t check(const void *p, uint32_t n) { return fpl_state_is_zero(p, n); }
'''


def build(out, mutation=None):
    header = (HERE / 'state_memory.h').read_text()
    if mutation:
        old, new = mutation
        assert header.count(old) == 1
        header = header.replace(old, new)
    (out / 'state_memory.h').write_text(header)
    (out / 'fixture.c').write_text(WRAPPERS)
    lib = out / 'memory.dylib'
    subprocess.run(['clang', '-O2', '-std=c11', '-Wall', '-Wextra', '-Werror',
                    '-shared', '-fPIC', str(out / 'fixture.c'), '-o', str(lib)],
                   check=True, capture_output=True)
    dll = C.CDLL(str(lib))
    for name in ('clear', 'check'):
        getattr(dll, name).argtypes = [C.c_void_p, C.c_uint32]
    return dll


class StateMemoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='fpl-state-')
        cls.lib = build(Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()

    def test_reset_covers_tail_and_preserves_both_neighbors(self):
        for words in (0, 1, 2, 7, 8, 9, 15, 16, 17, 173004):
            data = (C.c_uint32 * (words + 2))(*([0xa5a5a5a5] * (words + 2)))
            ptr = C.byref(data, 4)
            self.lib.clear(ptr, words * 4)
            self.assertEqual((data[0], data[-1]), (0xa5a5a5a5, 0xa5a5a5a5))
            self.assertEqual(bytes(data)[4:-4], bytes(words * 4))
            self.assertEqual(self.lib.check(ptr, words * 4), 1)

    def test_every_byte_and_bit_is_checked_in_unrolled_and_tail_words(self):
        data = (C.c_uint32 * 19)()
        raw = (C.c_ubyte * C.sizeof(data)).from_buffer(data)
        for byte in range(len(raw)):
            for bit in range(8):
                raw[byte] = 1 << bit
                self.assertEqual(self.lib.check(data, len(raw)), 0, (byte, bit))
                self.assertEqual(raw[byte], 1 << bit, 'validation is read-only')
                raw[byte] = 0
        self.assertEqual(self.lib.check(data, len(raw)), 1)

    def test_targeted_mutations_are_detected(self):
        mutations = [
            ('p[4] = p[5] = p[6] = p[7] = 0;', 'p[4] = p[5] = p[6] = 0;', 'clear'),
            ('p[4] | p[5] | p[6] | p[7]', 'p[4] | p[5] | p[6]', 'check'),
            ('while (words--) *p++ = 0;', 'while (words-- > 1u) *p++ = 0;', 'tail'),
        ]
        for old, new, name in mutations:
            with self.subTest(name=name), tempfile.TemporaryDirectory(prefix='fpl-state-mut-') as tmp:
                lib = build(Path(tmp), (old, new))
                data = (C.c_uint32 * 9)(*([0xa5a5a5a5] * 9))
                with self.assertRaises(AssertionError):
                    if name == 'check':
                        data = (C.c_uint32 * 8)(); data[7] = 1
                        self.assertEqual(lib.check(data, C.sizeof(data)), 0)
                    else:
                        lib.clear(data, C.sizeof(data))
                        self.assertEqual(bytes(data), bytes(C.sizeof(data)))


if __name__ == '__main__': unittest.main()
