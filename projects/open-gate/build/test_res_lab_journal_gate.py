"""Execute the resident Sensor Lab journal guard with fault injection.

The production helper is assembled unchanged and called in ARM Unicorn.  This
test has no camera or card I/O; it models the two ten-slot PowerOffMgr lists and
stage2's copied callback/journal layout.  A native Unicorn SIGILL is detected
in a child process and reported as an unverified skip.
"""
from __future__ import annotations

from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
import unittest

from armasm import assemble, symbols

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
GATE = HERE / "res_lab_journal_gate.S"
STAGE2 = ROOT / "fpSup/fp_usb_shell/asm/stage2.S"

try:
    from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
    from unicorn.arm_const import (UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_R0,
                                   UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_SP)
except ImportError:
    Uc = None


def unicorn_usable():
    if Uc is None:
        return False
    probe = subprocess.run(
        [sys.executable, "-B", "-c",
         "from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM; "
         "u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.mem_map(0x1000,0x1000)"],
        capture_output=True, timeout=10)
    return probe.returncode == 0


USABLE = unicorn_usable()
CODE, TABLE, OBJ = 0x45010000, 0x45000000, 0x45020000
STACK, DONE = 0x46010000, 0x47000000
MGR, POFF_MGR = 0xC30756C4, 0xC0023A98
SITES = ((0xC0011000, 0xE92D4010), (0xC0011010, 0xE1A00004))
UNHOOK_HEAD = (0xE92D4070, 0xE1A0600D, 0xE3CDD007, 0xE5904008)


class GateBuildContract(unittest.TestCase):
    def test_helper_assembles_and_signature_matches_shared_stage2(self):
        code = assemble(GATE)
        self.assertEqual(symbols(GATE)["sl_journal_ready"], 0)
        self.assertGreater(len(code), 100)
        stage2 = assemble(STAGE2, ["LH_RESTORE=1", "CAVE_ARENA=0xC072E068",
                                   "CAVE_BUMP=0xC072E060", "LOAD_DONE_US=0xC072F6F8"])
        start = symbols(STAGE2, ["LH_RESTORE=1", "CAVE_ARENA=0xC072E068",
                                 "CAVE_BUMP=0xC072E060", "LOAD_DONE_US=0xC072F6F8"])["lh_unhook"]
        self.assertEqual(struct.unpack_from("<4I", stage2, start), UNHOOK_HEAD)
        fingerprints = [int(word, 16) for word in re.findall(
            r"SL_LDA\s+r3, (0x[0-9A-F]+)\n\s+cmp\s+r1, r3", GATE.read_text())]
        self.assertEqual(tuple(fingerprints), UNHOOK_HEAD)


@unittest.skipUnless(USABLE, "Unicorn unavailable or native library failed its smoke test")
class GateExecution(unittest.TestCase):
    def camera(self, *, ordinary=True, forced=True, signature=True,
               journal=None, current=None, sites=SITES, gate_bytes=None):
        mu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        mu.mem_map(0xC0000000, 0x00300000)
        mu.mem_map(0xC3000000, 0x00100000)
        mu.mem_map(0x45000000, 0x00040000)
        mu.mem_map(0x46000000, 0x00010000)
        mu.mem_map(DONE, 0x1000)
        gate_bytes = assemble(GATE) if gate_bytes is None else gate_bytes
        mu.mem_write(CODE, gate_bytes)
        mu.mem_write(POFF_MGR, struct.pack("<I", 0xE12FFF1E))
        mu.mem_write(OBJ, struct.pack("<III", OBJ - 8, OBJ + 12, OBJ + 0x80))
        mu.mem_write(OBJ + 12, struct.pack("<4I", *(UNHOOK_HEAD if signature else (0,) * 4)))
        # The firmware normally occupies eight ordinary slots and one forced
        # slot before stage2 registers.  None is the shared journal object.
        mu.mem_write(MGR + 0x0C, struct.pack("<8I", *(0xC3001000 + 4 * i
                                                     for i in range(8))))
        mu.mem_write(MGR + 0x34, struct.pack("<I", 0xC3002000))
        if ordinary:
            mu.mem_write(MGR + 0x2C, struct.pack("<I", OBJ))
        if forced:
            mu.mem_write(MGR + 0x38, struct.pack("<I", OBJ))
        for index, (site, stock) in enumerate(sites):
            mu.mem_write(TABLE + 8 * index, struct.pack("<II", site, stock))
            mu.mem_write(site, struct.pack("<I", dict(current or ()).get(site, stock)))
        records = list(sites if journal is None else journal)
        cursor = OBJ + 0x80
        for site, saved in records:
            mu.mem_write(cursor, struct.pack("<III", site, 4, saved))
            cursor += 12
        mu.mem_write(cursor, struct.pack("<I", 0))

        def hook(machine, address, _size, _user):
            if address == POFF_MGR:
                machine.reg_write(UC_ARM_REG_R0, MGR)
                machine.reg_write(UC_ARM_REG_PC, machine.reg_read(UC_ARM_REG_LR))
            elif address != DONE and not CODE <= address < CODE + len(gate_bytes):
                raise AssertionError(f"unmodelled execution at {address:#x}")

        mu.hook_add(UC_HOOK_CODE, hook)
        return mu

    def call(self, mu, *, count=2, bound=2):
        mu.reg_write(UC_ARM_REG_R0, TABLE)
        mu.reg_write(UC_ARM_REG_R1, count)
        mu.reg_write(UC_ARM_REG_R2, bound)
        mu.reg_write(UC_ARM_REG_SP, STACK - 8)
        mu.reg_write(UC_ARM_REG_LR, DONE)
        mu.emu_start(CODE, DONE, count=1_000_000)
        self.assertEqual(mu.reg_read(UC_ARM_REG_PC), DONE,
                         "guard did not return within its instruction bound")
        return mu.reg_read(UC_ARM_REG_R0)

    def test_both_lists_exact_stock_and_bounded_journal_pass(self):
        self.assertEqual(self.call(self.camera()), 1)

    def test_missing_registration_and_wrong_callback_fail(self):
        for kw in ({"ordinary": False}, {"forced": False}, {"signature": False}):
            with self.subTest(kw=kw):
                self.assertEqual(self.call(self.camera(**kw)), 0)

    def test_missing_wrong_or_duplicate_journal_records_fail(self):
        for records in (SITES[:1], (SITES[0], (SITES[1][0], 0x12345678)),
                        (SITES[0], SITES[0], SITES[1])):
            with self.subTest(records=records):
                self.assertEqual(self.call(self.camera(journal=records), bound=3), 0)

    def test_patched_live_site_and_exhausted_bound_fail(self):
        site, stock = SITES[0]
        self.assertEqual(self.call(self.camera(current={site: stock ^ 4})), 0)
        self.assertEqual(self.call(self.camera(), bound=1), 0)

    def test_invalid_input_limits_fail(self):
        for count, bound in ((0, 2), (33, 2), (2, 0), (2, 513)):
            with self.subTest(count=count, bound=bound):
                self.assertEqual(self.call(self.camera(), count=count, bound=bound), 0)

    def test_29_sites_with_296_records_fit_the_declared_bound(self):
        sites = tuple((0xC0011000 + 4 * i, 0xE1A00000 + i) for i in range(29))
        others = tuple((0xC0012000 + 4 * i, 0xE3A00000 + i) for i in range(267))
        cam = self.camera(sites=sites, journal=others + sites)
        self.assertEqual(self.call(cam, count=29, bound=296), 1)

    def test_full_32_descriptor_mask(self):
        sites = tuple((0xC0011000 + 4 * i, 0xE1A00000 + i) for i in range(32))
        self.assertEqual(self.call(self.camera(sites=sites), count=32, bound=32), 1)

    def test_mutated_guard_would_admit_a_wrong_saved_word(self):
        source = GATE.read_text()
        check = "    cmp     r6, ip\n    bne     .Lfail\n    ldr     r6, [r3]"
        self.assertEqual(source.count(check), 1)
        mutant = source.replace(check, "    cmp     r6, ip\n    nop\n    ldr     r6, [r3]", 1)
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "mutated_gate.S"
            file.write_text(mutant)
            bad_code = assemble(file)
        bad_journal = (SITES[0], (SITES[1][0], 0x12345678))
        self.assertEqual(self.call(self.camera(journal=bad_journal)), 0)
        self.assertEqual(self.call(self.camera(journal=bad_journal,
                                               gate_bytes=bad_code)), 1)


if __name__ == "__main__":
    unittest.main()
