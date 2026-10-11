#!/usr/bin/env python3
"""OG_UISHARE OpenGate with nested strings (fpSup/uishare/NESTED_HOOKS.md),
on the real image (fp-unicorn-emulation).

    OG_TARGET=og3k python3 -B test_og_nested_strings.py     (og2k likewise)

A nested OG card is built into a temporary directory and booted through the
real loader and stage2 (fpSup/fp_usb_shell/test_loader_hook.Camera); then the
card's own UI section -- the bytes in its fpSup.BIN -- runs where the loader
would run it. What is asserted:

  - the three string sites are declared with their stock words, journaled,
    hung by the UI section, and written back by the power-off callback;
  - ui_aliases holds the offsets OpenGate's labels were given (word 3 unused),
    and the firmware's own C05E5B58 resolves each to its label; stock offsets
    resolve as on a stock camera; the stock pool is never repointed;
  - OpenGate's record hook (C05E6400): before the offsets exist it leaves the
    summary and the aliased Quick Set records stock; after, it hands the
    parser exactly the archived replacement, with OpenGate's FFFFFFF2..F6
    placeholders replaced by the offsets it was given;
  - ui_layout takes no Quick Set snapshot before the offsets exist, and does
    after (so a layout built before then is still re-parsed).

Emulation is not the camera: timing, GUI redraw and the screen stay untested.
"""
import json
import os
import pathlib
import re
import struct
import subprocess
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SHELL = ROOT / "fpSup" / "fp_usb_shell"
UISHARE = ROOT / "fpSup" / "uishare"
sys.path[:0] = [str(SHELL), str(UISHARE), str(HERE)]
TARGET = os.environ.get("OG_TARGET", "og3k")
os.environ["OG_TARGET"] = TARGET
sys.argv[1:] = [a for a in sys.argv[1:] if a.startswith("-")]
import test_loader_hook as T                      # noqa: E402
from ui import chain                              # noqa: E402
from unicorn import UC_HOOK_CODE                  # noqa: E402
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_SP,  # noqa: E402
                               UC_ARM_REG_LR)

GUI_OBJECT, UI_AREA = 0xC37B7048, 0xC3A00000
NBU_BASE, POOL, POOL_LEN = 0xC18C0460, 0xC18C0474, 176152
B2_5_ENTRY = 0x19C130
HEAP2, HEAP2_SIZE = 0x48000000, 0x01000000      # fresh memory for every allocation
STAGING = HEAP2 + 0xF00000
STATE, REQ = 0xC0732700, 0xC07327C8
RECORD_SITE, RECORD_GO = 0xC05E6400, 0xC05E6404  # the stock body after the replayed push
LAYOUT_SITE, LAYOUT_GO = 0xC05D90F0, 0xC05D90F4
POP_RECORD = bytes.fromhex("bde8f08f")            # pop.w {r4-r11, pc}
POP_LAYOUT = bytes.fromhex("bde8f08c")            # pop.w {r4-r7, r10, r11, pc}
FIRST = 0x40000000


def vbin(blob):
    _, count, entry, _ = struct.unpack_from("<4sIII", blob)
    off, out = 16 + 8 * count, []
    for i in range(count):
        d, n = struct.unpack_from("<II", blob, 16 + 8 * i)
        out.append((d, blob[off:off + n]))
        off += n + (-n % 4)
    return entry, out


class Card(T.Camera):
    """Every allocation gets fresh memory (the loader's staging included)."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.mu.mem_map(HEAP2, HEAP2_SIZE)
        self.next = HEAP2

    def _hook(self, mu, addr, size, ud):
        if addr == T.F["H_ADDR"]:
            got, self.next = self.next, self.next + 0x40000
            return self._ret(got)
        return super()._hook(mu, addr, size, ud)

    def put(self, a, v):
        self.mu.mem_write(a, struct.pack("<I", v & 0xFFFFFFFF))

    def call_thumb(self, fn, r0, r1=0):
        self.mu.reg_write(UC_ARM_REG_SP, T.STACK - 0x2000)
        self.mu.reg_write(UC_ARM_REG_R0, r0)
        self.mu.reg_write(UC_ARM_REG_R1, r1)
        self.mu.reg_write(UC_ARM_REG_LR, T.DONE)
        self.mu.emu_start(fn | 1, T.DONE, count=2_000_000)
        return self.r(UC_ARM_REG_R0)


class Nested(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix=f"og-nested-{TARGET}-")
        out = pathlib.Path(cls.tmp.name) / "card"
        env = dict(os.environ, OG_UISHARE="1", OG_TARGET=TARGET)
        # --loader-hook-mark: stage2 publishes its journal block at MARK+8 (the
        # harness's convention); only stage2 differs from the release card
        r = subprocess.run([sys.executable, "-B", str(HERE / "build_og3k_gyro.py"), "--no-gyro",
                            "--release", "--out", str(out), "--loader-hook-mark", hex(T.MARK)],
                           env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
        text = (out / "AutoRun.txt").read_text()
        sets = re.findall(r"^mem set (0x\w+) (0x\w+)", text, re.M)
        cls.loader = {int(a, 16): int(v, 16) for a, v in sets
                      if T.CAVE_LO <= int(a, 16) < T.CAVE_LOW + 0x200}
        cls.bin = (out / "fpSup.BIN").read_bytes()
        cls.manifest = json.loads((out / "MANIFEST.json").read_text())
        aliases = cls.manifest["ui"]["aliases"]
        assert aliases, "the card was not built with nested strings"
        cls.table = int(aliases["table"], 16)
        cls.labels = {s["index"]: s["text"] for s in aliases["strings"]}
        import build_og3k_gyro
        import build_section
        cls.section = build_section.section(
            build_og3k_gyro.ui_block(TARGET.upper(), cls.manifest).encode())[0]
        import build_og3k_ui_candidate as C
        cls.plans = {int(p["address"], 16): p for p in C.selected_plans()[0]}
        cls.sites = [(a, w) for a, w, _ in chain.SITES.values()]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    # ---- a booted camera ----------------------------------------------------
    def boot(self):
        cam = Card(self.loader, self.bin)
        cam.put(T.SITE, 0xEB000000 | ((((T.CAVE_LOW + 4) - T.SITE - 8) >> 2) & 0xFFFFFF))
        cam.call(T.CAVE_LOW + 4, r0=0xC0BABDD8, r1=1, lr=T.AR_RET, sp=T.STACK - 0x1004)
        return cam

    def run_ui(self, cam):
        """The card's UI section, where the loader would run it, with the native
        UI objects it looks for (fp-native-ui §8a)."""
        _, sections = vbin(self.bin)
        self.assertIn((0, self.section), sections, "the card does not carry its UI section")
        app, screens, screen, reader, entries, names = (UI_AREA + o for o in
                                                        (0, 0x1000, 0x2000, 0x3000, 0x4000, 0x6000))
        for a, v in ((GUI_OBJECT, app), (app + 0x80, 1), (app + 0x8C, screens), (screens, screen),
                     (screen + 0x24, reader), (reader + 0x10, POOL_LEN), (reader + 0x14, POOL),
                     (reader + 0x24, NBU_BASE), (reader + 0xA8, 1), (reader + 0xAC, entries),
                     (entries + 4, names), (entries + 8, B2_5_ENTRY)):
            cam.put(a, v)
        cam.mu.mem_write(names, b"B2_5\0")
        cam.put(0xC072E060, 0xC072E064)          # stage2 resets the cave bump every boot
        cam.mu.mem_write(STAGING, self.section)
        cam.call(STAGING, r0=STAGING, lr=T.DONE, sp=T.STACK - 0x1000)
        return reader

    def journal(self, cam):
        x = cam.word(T.MARK + 8)
        j, got = cam.word(x + 8), {}
        while cam.word(j):
            a, n = cam.word(j), cam.word(j + 4)
            got[a] = bytes(cam.mu.mem_read(j + 8, n))
            j += 8 + n
        return x, got

    def aliases(self, cam):
        return [cam.word(self.table + 4 * k) for k in range(5)]

    # ---- sites ----------------------------------------------------------------
    def test_string_sites_are_journaled_hung_and_written_back(self):
        cam = self.boot()
        x, j = self.journal(cam)
        for a, w in self.sites:
            self.assertEqual(j[a][:4], struct.pack("<I", w), hex(a))
            self.assertEqual(cam.word(a), w, hex(a))         # nothing hung before the entry
        self.run_ui(cam)
        self.assertTrue(all(cam.word(a) != w for a, w in self.sites))
        for _ in range(2):
            cam.call(cam.word(x + 4), r0=x, r1=4)
        for a, w in self.sites:
            self.assertEqual(cam.word(a), w, hex(a))

    # ---- strings --------------------------------------------------------------
    def test_ui_aliases_name_the_labels_and_the_firmware_resolves_them(self):
        cam = self.boot()
        self.assertEqual(self.aliases(cam), [0] * 5, "offsets before the UI section ran")
        reader = self.run_ui(cam)
        words = self.aliases(cam)
        self.assertEqual(words[3], 0)
        for k, text in self.labels.items():
            self.assertGreaterEqual(words[k], FIRST)
            p = cam.call_thumb(0xC05E5B58, reader, words[k])
            self.assertEqual(cam.cstr(p), text)
        layers = chain.layers(cam.word)
        self.assertEqual(len(layers), 1)
        self.assertEqual(sorted(layers[0][1]), sorted(set(self.labels.values())))
        self.assertEqual((cam.word(reader + 0x14), cam.word(reader + 0x10)), (POOL, POOL_LEN))
        stock = Card(self.loader, self.bin)
        stock.mu.mem_write(UI_AREA + 0x3000 + 0x10, struct.pack("<II", POOL_LEN, POOL))
        for off in (0, 1000, 0x12BC4, POOL_LEN - 1, POOL_LEN, 0xFFFFFFF2, 0xFFFFFFFF):
            self.assertEqual(cam.call_thumb(0xC05E5B58, reader, off),
                             stock.call_thumb(0xC05E5B58, UI_AREA + 0x3000, off), hex(off))

    # ---- the record hook ------------------------------------------------------
    def parse(self, cam, address):
        """C05E6400 on the stock record at `address`; returns (base, record
        bytes) the stock parser body was handed."""
        obj, ctx = HEAP2 + 0xE00000, HEAP2 + 0xE01000
        cam.put(obj + 36, NBU_BASE)
        cam.put(obj + 4, address - NBU_BASE)
        cam.put(obj + 8, ctx)
        cam.put(STATE, ctx)
        cam.put(STATE + 4, 1)                         # the private NBR pack: ready
        cam.mu.mem_write(RECORD_GO, POP_RECORD)
        seen = []

        def go(mu, addr, size, _):
            base, pos = cam.word(obj + 36), cam.word(obj + 4)
            n = struct.unpack(">I", bytes(mu.mem_read(base + pos + 4, 4)))[0]
            seen.append((base, bytes(mu.mem_read(base + pos, n))))
        h = cam.mu.hook_add(UC_HOOK_CODE, go, begin=RECORD_GO, end=RECORD_GO)
        try:
            cam.call_thumb(RECORD_SITE, obj)
        finally:
            cam.mu.hook_del(h)
        self.assertEqual(len(seen), 1)
        return seen[0]

    def expected(self, plan, words):
        new = bytearray.fromhex(plan["new"])
        swapped = 0
        for k in range(5):
            placeholder = struct.pack(">I", 0xFFFFFFF2 + k)
            while placeholder in new:
                i = new.index(placeholder)
                new[i:i + 4] = struct.pack(">I", words[k])
                swapped += 1
        return bytes(new), swapped

    def alias_plans(self):
        out = [a for a, p in self.plans.items() if p["kind"] == "summary-label"]
        out += [a for a, p in self.plans.items() if p["kind"] == "layout-keys" and p.get("aliases")][:3]
        return out

    def test_the_record_hook_waits_for_the_offsets_then_uses_them(self):
        cam = self.boot()
        for address in self.alias_plans():
            plan = self.plans[address]
            base, rec = self.parse(cam, address)
            self.assertEqual((base, rec), (NBU_BASE, bytes.fromhex(plan["old"])),
                             f"0x{address:08X} edited before the strings existed")
        self.run_ui(cam)
        words = self.aliases(cam)
        for address in self.alias_plans():
            plan = self.plans[address]
            want, swapped = self.expected(plan, words)
            self.assertGreater(swapped, 0, f"0x{address:08X}: the plan has no placeholder")
            base, rec = self.parse(cam, address)
            self.assertNotEqual(base, NBU_BASE)
            self.assertEqual(rec, want, f"0x{address:08X}")

    def test_records_without_labels_are_edited_once_armed(self):
        cam = self.boot()
        self.run_ui(cam)
        plain = [a for a, p in self.plans.items() if p["kind"] in ("state-end", "QS-limit")][:3]
        for address in plain:
            _, rec = self.parse(cam, address)
            self.assertEqual(rec, bytes.fromhex(self.plans[address]["new"]), f"0x{address:08X}")

    # ---- the layout hook ------------------------------------------------------
    def load_layout(self, cam):
        layout = HEAP2 + 0xE02000
        cam.put(layout + 4, HEAP2 + 0xE03000)
        cam.mu.mem_write(LAYOUT_GO, POP_LAYOUT)
        cam.call_thumb(LAYOUT_SITE, layout)

    def test_the_layout_snapshot_waits_for_the_offsets(self):
        cam = self.boot()
        self.load_layout(cam)
        self.assertEqual(cam.word(REQ), 0, "a snapshot before the strings existed")
        self.run_ui(cam)
        self.load_layout(cam)
        self.assertEqual(cam.word(REQ), 1)


if __name__ == "__main__":
    unittest.main()
