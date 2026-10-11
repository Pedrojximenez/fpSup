"""Offline extractor tests; generated objects are never installed or executed."""
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

from elf_text import ELFError, load_text


class ELFTextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.clang = shutil.which("clang")
        if not cls.clang:
            raise RuntimeError("clang required; no skipped compiler tests")
        cls.tmp = tempfile.TemporaryDirectory(prefix="fpl-elf-text-")
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.next_id = 0
        cls.good = cls.compile("""
            typedef unsigned int u32;
            typedef int (*native_fn)(void *, const char *, u32 *);
            __attribute__((noinline)) int native_lookup(void *app, const char *name, u32 *out) {
                return ((native_fn)0xc05dca89u)(app, name, out);
            }
            int increment(int value) { return value + 1; }
        """)

    @classmethod
    def compile(cls, source):
        target = Path(cls.tmp.name) / ("%d.o" % cls.next_id)
        cls.next_id += 1
        subprocess.run([cls.clang, "--target=armv7-none-eabi", "-mcpu=cortex-a9", "-mthumb",
                        "-mfloat-abi=soft", "-mfpu=none", "-O2", "-ffreestanding", "-fno-builtin",
                        "-Wall", "-Wextra", "-Werror", "-x", "c", "-c", "-", "-o", str(target)],
                       input=source, text=True, capture_output=True, check=True)
        return target.read_bytes()

    @staticmethod
    def sections(blob):
        shoff = struct.unpack_from("<I", blob, 32)[0]
        count, strings_index = struct.unpack_from("<HH", blob, 48)
        sections = [struct.unpack_from("<10I", blob, shoff + n * 40) for n in range(count)]
        string_sec = sections[strings_index]
        strings = blob[string_sec[4]:string_sec[4] + string_sec[5]]
        names = [strings[s[0]:].split(b"\0", 1)[0].decode("ascii") for s in sections]
        return shoff, sections, names

    def mutate_header(self, offset, fmt, value):
        result = bytearray(self.good)
        struct.pack_into(fmt, result, offset, value)
        return result

    def mutate_section(self, name, word_index, value):
        result = bytearray(self.good)
        shoff, _, names = self.sections(result)
        struct.pack_into("<I", result, shoff + names.index(name) * 40 + word_index * 4, value)
        return result

    def test_fixed_native_function_pointer_and_thumb_offsets(self):
        result = load_text(self.good)
        self.assertEqual(set(result.functions), {"native_lookup", "increment"})
        self.assertGreater(len(result.code), 4)
        self.assertTrue(all(offset & 1 for offset in result.functions.values()))
        _, sections, names = self.sections(self.good)
        text = sections[names.index(".text")]
        self.assertEqual(result.code, self.good[text[4]:text[4] + text[5]])

    def test_path_input(self):
        self.assertEqual(load_text(Path(self.tmp.name) / "0.o"), load_text(self.good))

    def test_truncated_header(self):
        for length in (0, 4, 16, 51):
            with self.subTest(length=length), self.assertRaises(ELFError):
                load_text(self.good[:length])

    def test_elf_identity_and_abi(self):
        for offset, fmt, value in [(0, "<I", 0), (4, "B", 2), (5, "B", 2), (6, "B", 0),
                                   (7, "B", 3), (8, "B", 1), (16, "<H", 2), (18, "<H", 62),
                                   (20, "<I", 2), (24, "<I", 1), (28, "<I", 52),
                                   (36, "<I", 0x05000400), (36, "<I", 0x05800000),
                                   (40, "<H", 64), (46, "<H", 64),
                                   (48, "<H", 0), (50, "<H", 0xffff)]:
            with self.subTest(offset=offset), self.assertRaises(ELFError):
                load_text(self.mutate_header(offset, fmt, value))

    def test_section_table_bounds(self):
        with self.assertRaisesRegex(ELFError, "bounds"):
            load_text(self.mutate_header(32, "<I", len(self.good) & ~3))

    def test_section_body_bounds(self):
        with self.assertRaisesRegex(ELFError, "bounds"):
            load_text(self.mutate_section(".text", 5, len(self.good)))

    def test_section_overlap(self):
        with self.assertRaisesRegex(ELFError, "overlaps"):
            load_text(self.mutate_section(".text", 4, 0))

    def test_section_alignment(self):
        with self.assertRaisesRegex(ELFError, "alignment"):
            load_text(self.mutate_section(".text", 8, 3))

    def test_unsupported_section_type(self):
        # SHT_RELR cannot silently bypass the explicit REL/RELA rejection path.
        with self.assertRaisesRegex(ELFError, "unsupported section type"):
            load_text(self.mutate_section(".rel.ARM.exidx", 1, 19))

    def test_writable_allocated_empty_section(self):
        with self.assertRaisesRegex(ELFError, "writable allocated"):
            load_text(self.mutate_section(".note.GNU-stack", 2, 3))

    def test_undefined_function(self):
        blob = self.compile("extern int unresolved(int); int call(int x) { return unresolved(x); }")
        with self.assertRaisesRegex(ELFError, "undefined symbol: unresolved"):
            load_text(blob)

    def test_undefined_data(self):
        blob = self.compile("extern int unresolved; int read(void) { return unresolved; }")
        with self.assertRaisesRegex(ELFError, "undefined symbol: unresolved"):
            load_text(blob)

    def test_text_relocation_to_defined_function(self):
        blob = self.compile("__attribute__((noinline)) int other(int x) { return x+1; } int call(int x) { return other(x); }")
        with self.assertRaisesRegex(ELFError, r"\.text relocation"):
            load_text(blob)

    def test_writable_allocated_data(self):
        blob = self.compile("int global = 2; int call(int x) { global = x; return x; }")
        with self.assertRaisesRegex(ELFError, "writable allocated"):
            load_text(blob)

    def test_additional_executable_section(self):
        blob = self.compile('__attribute__((section(".other"))) int other(int x) { return x+1; } int call(int x) { return x; }')
        with self.assertRaisesRegex(ELFError, "additional executable"):
            load_text(blob)

    def test_symbol_name_bounds(self):
        blob = bytearray(self.good)
        _, sections, _ = self.sections(blob)
        sym = next(s for s in sections if s[1] == 2)
        struct.pack_into("<I", blob, sym[4] + 16, 0xffffffff)
        with self.assertRaisesRegex(ELFError, "string offset"):
            load_text(blob)

    def test_function_bounds(self):
        blob = bytearray(self.good)
        _, sections, _ = self.sections(blob)
        sym = next(s for s in sections if s[1] == 2)
        for offset in range(sym[4] + 16, sym[4] + sym[5], 16):
            if blob[offset + 12] & 15 == 2:
                struct.pack_into("<I", blob, offset + 8, 0xffffffff)
                break
        with self.assertRaisesRegex(ELFError, "symbol exceeds section bounds"):
            load_text(blob)

    def test_symbol_table_entry_size(self):
        with self.assertRaisesRegex(ELFError, "symbol table entry size"):
            load_text(self.mutate_section(".symtab", 9, 8))

    def test_relocation_symbol_bounds(self):
        blob = bytearray(self.good)
        _, sections, _ = self.sections(blob)
        rel = next(s for s in sections if s[1] == 9)
        struct.pack_into("<I", blob, rel[4] + 4, 0xffffff00)
        with self.assertRaisesRegex(ELFError, "relocation symbol index"):
            load_text(blob)

    def test_relocation_target_bounds(self):
        blob = bytearray(self.good)
        _, sections, _ = self.sections(blob)
        rel = next(s for s in sections if s[1] == 9)
        struct.pack_into("<I", blob, rel[4], 0xffffffff)
        with self.assertRaisesRegex(ELFError, "relocation exceeds target"):
            load_text(blob)


if __name__ == "__main__":
    unittest.main(verbosity=2)
