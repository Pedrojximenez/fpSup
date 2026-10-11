#!/usr/bin/env python3
"""Execute the exact Sensor Lab card through the shared loader, offline only.

The worker spawn and named firmware services are stubs. The real loader,
stage2, entries trampoline, Sensor Lab restore entry, selector and picker run.
"""
import argparse
import json
from pathlib import Path
import re
import struct
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[2] / "fpSup/fp_usb_shell")]
import build_res_lab_card as B
import imx410_plan as PL
import test_loader_hook as T
from armasm import symbols
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2,
                               UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6,
                               UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_SP)


class SensorCamera(T.Camera):
    def __init__(self, directory, have_file=True, preference=0, movie_format=0, blob=None):
        self.blob = blob if blob is not None else (directory / "fpSup.BIN").read_bytes()
        entry, records = B.decode(self.blob)
        self.worker_pc = None
        self.worker_offset = None
        if entry < 0x40000000 and entry:
            table = symbols(B.SHELL / "asm/entries.S")["table"]
            self.worker_offset = struct.unpack_from("<I", self.blob, entry + table + 4)[0]
        text = (directory / "AutoRun.txt").read_text()
        loader = {int(a, 16): int(v, 16) for a, v in
                  re.findall(r"^mem set (0x[0-9A-Fa-f]+) (0x[0-9A-Fa-f]+)", text, re.M)
                  if T.CAVE_LOW <= int(a, 16) < T.CAVE_LOW + 0x200}
        assert loader
        self.movie_format = movie_format
        self.sensor_entries = 0
        self.stop_at = set()
        self.native_calls = []
        super().__init__(loader, self.blob, have_file=have_file)
        self.mu.mem_write(0xC30754CC, struct.pack("<I", preference))

    def _hook(self, mu, address, size, data):
        if address in self.stop_at:
            mu.emu_stop()
            return
        if address == self.worker_pc:
            assert self.r(UC_ARM_REG_R0) == address and self.r(UC_ARM_REG_SP) % 8 == 0, (hex(address), hex(self.r(UC_ARM_REG_R0)), hex(self.r(UC_ARM_REG_SP)))
            self.calls.append("WORKER_STUB")
            return self._ret(0)
        if address == PL.RESTORE_CODE:
            assert self.r(UC_ARM_REG_R0) == address and self.r(UC_ARM_REG_SP) % 8 == 0, (hex(address), hex(self.r(UC_ARM_REG_R0)), hex(self.r(UC_ARM_REG_SP)))
            self.sensor_entries += 1
            self.calls.append("SENSOR_ENTRY")
        native = {0xC0057AE8: 0xC3000300, 0xC005BE90: self.movie_format,
                  0xC0423C48: 0xC3000400}  # getter, format, inactive LV holder
        if address in native:
            assert self.r(UC_ARM_REG_SP) % 8 == 0
            self.native_calls.append(address)
            return self._ret(native[address])
        if address == PL.SEL_HOOK + 4:
            # Original setter body is a declared stub. Its displaced push has
            # executed; perform the matching pop and return, preserving ABI.
            sp = self.r(UC_ARM_REG_SP)
            words = struct.unpack("<4I", mu.mem_read(sp, 16))
            for reg, value in zip((UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_PC), words):
                mu.reg_write(reg, value)
            mu.reg_write(UC_ARM_REG_SP, sp + 16)
            return
        if address == T.F["F_READ"]:
            if self.worker_offset is not None:
                self.worker_pc = self.r(UC_ARM_REG_R1) + self.worker_offset
            super()._hook(mu, address, size, data)
            self.entry = None  # execute our entry/trampoline instead of T's entry stub
            return
        # Reject unexpected firmware execution instead of accepting ROM noise.
        if 0xC0000000 <= address < 0xC3000000:
            allowed = (address in self.by_addr or
                       T.CAVE_LOW <= address < T.CAVE_LOW + 0x200 or
                       PL.CAVE_LO <= address < PL.CAVE_HI or
                       address in (PL.SEL_HOOK, PL.PIK_HOOK, PL.RAT_HOOK))
            if not allowed:
                raise AssertionError(f"unstubbed firmware execution at {address:#x}")
        return super()._hook(mu, address, size, data)

    def boot(self):
        result = self.call(T.CAVE_LOW)
        assert result[1] == T.STACK - 0x1004
        if self.have_file:
            assert self.sensor_entries == 1
            loader = [(o, f) for o, f in self.registered if o != PL.POFF_OBJ]
            ours = [(o, f) for o, f in self.registered if o == PL.POFF_OBJ]
            assert [flag for _, flag in loader] == [0, 1]
            # 14-bit power-off revert: one object, first list, registered before RESTORE runs.
            assert ours == ([(PL.POFF_OBJ, 0)] if PL.WITH_BIT_POFF else []), ours
            if PL.WITH_BIT_POFF:
                assert self.word(PL.POFF_STATE) == 1   # POFF_ADD result
            assert self.word(0xC0731C20) == self.movie_format
            assert "DCACHE" in self.calls and "ICACHE" in self.calls
            assert self.calls.index("DCACHE") < self.calls.index("ICACHE") < self.calls.index("SENSOR_ENTRY")
        return result


def poff_callback(cam, bit_depth):
    """Run the registered power-off callback against stubbed settings; return setter calls."""
    from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2
    vtbl = cam.word(PL.POFF_OBJ)
    fn = cam.word(vtbl + 0xC)
    sets = []
    hooks = {0xC0057AE8: lambda: 0xC3000300,
             0xC005BF28: lambda: bit_depth,
             0xC005BEF0: lambda: sets.append((cam.r(UC_ARM_REG_R0), cam.r(UC_ARM_REG_R1),
                                              cam.r(UC_ARM_REG_R2))) or 0}
    def h(mu, address, size, data):
        if address in hooks:
            cam._ret(hooks[address]())
    handle = cam.mu.hook_add(UC_HOOK_CODE, h)
    try:
        cam.call(fn, r0=PL.POFF_OBJ, r1=1)
    finally:
        cam.mu.hook_del(handle)
    return sets


def verify(directory):
    manifest = json.loads((directory / "MANIFEST.json").read_text())
    for name, digest in manifest["artifacts"].items():
        assert B.sha(directory / name) == digest, name
    cam = SensorCamera(directory)
    cam.boot()
    if PL.WITH_BIT_POFF:
        # 14-bit (1) -> setter(mgr, 0, 0) once; 12-bit (0) and 10-bit (3) untouched.
        assert poff_callback(cam, 1) == [(0xC3000300, 0, 0)]
        assert poff_callback(cam, 0) == [] and poff_callback(cam, 3) == []
        st = struct.unpack("<4I", cam.mu.mem_read(PL.POFF_STATE, 16))
        assert st[1] == 3 and st[2] == 1, st          # runs, reverts
    assert cam.word(0xC0731C08) == 0
    if manifest["debug"]:
        assert cam.calls.index("WORKER_STUB") < cam.calls.index("SENSOR_ENTRY")
    else:
        assert "WORKER_STUB" not in cam.calls
    _, records = B.decode(cam.blob)
    firmware = [(a, data) for a, _, data in records
                if a >= 0x40000000 and not T.CAVE_LO <= a < T.CAVE_HI]
    obj = cam.registered[0][0]
    journal, saved = cam.word(obj + 8), {}
    while cam.word(journal):
        a, size = cam.word(journal), cam.word(journal + 4)
        for i in range(0, size, 4):
            saved[a + i] = cam.word(journal + 8 + i)
        journal += 8 + size
    runtime = [int(a, 16) for a in manifest["runtime_restore_addresses"]]
    assert len(runtime) == 146 and all(a in saved for a in runtime)
    for a in runtime:
        cam.mu.mem_write(a, struct.pack("<I", saved[a] ^ 0x00123456))
    for _ in range(2):
        cam.call(cam.word(obj + 4), r0=obj, r1=4)
    for address, data in firmware:
        assert bytes(cam.mu.mem_read(address, len(data))) == cam.stock[address - PL.B:address - PL.B + len(data)]
    # Warm image: firmware restored, cave retained, BSS/heap recreated as at boot.
    warm = SensorCamera(directory)
    warm.mu.mem_write(T.CAVE_LO, bytes(cam.mu.mem_read(T.CAVE_LO, T.CAVE_HI - T.CAVE_LO)))
    warm.boot()
    assert warm.word(0xC0731C08) == 0 and warm.word(PL.RECIPE + 9 * 4) == 0

    for preference, fmt, expected in ((1, 0, 1), (1, 1, 0)):
        selected = SensorCamera(directory, preference=preference, movie_format=fmt)
        selected.boot()
        assert selected.word(0xC0731C08) == expected
    missing = SensorCamera(directory, have_file=False)
    missing.boot()
    assert missing.sensor_entries == 0 and missing.registered == []
    assert missing.word(PL.PIK_HOOK) == PL.PIK_STOCK

    # Exact delivered picker bytes: a 14-bit menu request must replace stale 12.
    actual = SensorCamera(directory)
    actual.boot()
    from imx410_block import axis_words, expected_recipe, RECIPE_WORDS
    axis = axis_words(bit=12, rate="30", raster=(5712, 3216))
    mu = actual.mu
    mu.mem_write(PL.AXIS, struct.pack("<9I", *axis))
    mu.mem_write(0xC2F1E654, struct.pack("<4I", 0xC0B59500, 70, 0xC0B59DC0, 70))
    mu.mem_write(0xC343B588, struct.pack("<I", 0xC2F1E654))
    mu.mem_write(0xC3000600, b"CUST24\x00" + bytes(25))
    mu.mem_write(0xC3000720, struct.pack("<I", 1))
    for reg, value in ((UC_ARM_REG_R0, 0xC3000300), (UC_ARM_REG_R1, 0xC0BE5B50),
                       (UC_ARM_REG_R2, 0xC3000600), (UC_ARM_REG_R6, 0xC3000700),
                       (UC_ARM_REG_LR, 0xC043B92C), (UC_ARM_REG_SP, T.STACK - 0x1000)):
        mu.reg_write(reg, value)
    actual.stop_at.add(0xC043B92C)
    mu.emu_start(PL.PIK_HOOK, 0xC043B92C, count=2_000_000)
    want = expected_recipe(PL.Registry(), axis_words(bit=14, rate="24", raster=(5712, 3216)))
    got = list(struct.unpack(f"<{RECIPE_WORDS}I", mu.mem_read(PL.RECIPE, RECIPE_WORDS * 4)))
    assert got == want and actual.word(PL.BITLATCH) == 1

    # Exercise the native menu converters from the delivered bytes, then feed
    # the real suffix into the installed picker. These are three different enum
    # spaces; a synthetic CUST240 key alone would miss the old export-5 assert.
    from test_imx410_rate_native import verify_installed
    installed = {a + i: struct.unpack_from("<I", data, i)[0]
                 for a, _, data in records if a >= 0x40000000
                 for i in range(0, len(data), 4)}
    native_rate = verify_installed(installed)
    # ⛔ SETTINGS_AREA_FIRST_RULE: row nine hands stock 119.88 ("120"); 239.76 is
    # the RAM flag only.  After committing row nine the summary shows the tenth label.
    assert native_rate["internal"] == 7 and native_rate["suffix"] == "120"
    assert native_rate["summary_state"] == 9
    from imx410_rate_ui import verify_installed as verify_summary
    summary = verify_summary(installed, base_image=PL.FIRMWARE.read_bytes(), native=True)
    assert summary["native_selected_summary_child"] == 4458
    from imx410_rate_lv import verify_installed as verify_liveview, SETS as LV_SETS
    liveview = verify_liveview(installed, base_image=PL.FIRMWARE.read_bytes(), native=True)
    assert len(liveview) == len(LV_SETS) and all(v["row9"] == "240" and v["row10"] == "15"
                                      for v in liveview)
    high = SensorCamera(directory, preference=1, movie_format=0)
    high.boot()
    ax120 = axis_words(bit=12, rate="120", raster=(2016, 672), rwzm=(2048, 1024))
    ax240 = axis_words(bit=12, rate="240", raster=(2016, 672), rwzm=(2048, 1024))
    mu = high.mu
    mu.mem_write(PL.AXIS, struct.pack("<9I", *ax120))
    mu.mem_write(0xC2F1E654, struct.pack("<4I", 0xC0B59500, 70, 0xC0B59DC0, 70))
    mu.mem_write(0xC343B588, struct.pack("<I", 0xC2F1E654))
    key = ("CUST" + native_rate["suffix"]).encode() + b"\0"
    mu.mem_write(0xC3000600, key.ljust(32, b"\0"))
    mu.mem_write(PL.RATE_NATIVE.RATE240, struct.pack("<I", 1))   # row nine committed
    mu.mem_write(0xC3000720, struct.pack("<I", 0))  # native RAW12 enum
    for reg, value in ((UC_ARM_REG_R0, 0xC3000300), (UC_ARM_REG_R1, 0xC0BE5B50),
                       (UC_ARM_REG_R2, 0xC3000600), (UC_ARM_REG_R6, 0xC3000700),
                       (UC_ARM_REG_LR, 0xC043B92C), (UC_ARM_REG_SP, T.STACK - 0x1000)):
        mu.reg_write(reg, value)
    high.stop_at.add(0xC043B92C)
    mu.emu_start(PL.PIK_HOOK, 0xC043B92C, count=2_000_000)
    assert list(struct.unpack("<9I", mu.mem_read(PL.AXIS, 36))) == ax240
    want = expected_recipe(PL.Registry(), ax240)
    assert want[9] == 1
    got = list(struct.unpack(f"<{RECIPE_WORDS}I", mu.mem_read(PL.RECIPE, RECIPE_WORDS * 4)))
    assert got == want and high.word(PL.PICKOK) == 1
    assert high.r(UC_ARM_REG_R0) == PL.ENTRY_ADDR
    high.call(PL.RAT_HOOK, r0=0xC3000800, sp=T.STACK - 0x1000)
    assert struct.unpack("<II", mu.mem_read(0xC3000800, 8)) == (240000, 1001)
    # Same stock value without the RAM flag (e.g. after any boot) stays 119.88.
    low = SensorCamera(directory, preference=1, movie_format=0)
    low.boot()
    lm = low.mu
    lm.mem_write(PL.AXIS, struct.pack("<9I", *ax240))
    lm.mem_write(0xC2F1E654, struct.pack("<4I", 0xC0B59500, 70, 0xC0B59DC0, 70))
    lm.mem_write(0xC343B588, struct.pack("<I", 0xC2F1E654))
    lm.mem_write(0xC3000600, key.ljust(32, b"\0"))
    lm.mem_write(0xC3000720, struct.pack("<I", 0))
    assert low.word(PL.RATE_NATIVE.RATE240) == 0, "loader must zero the row-nine flag"
    for reg, value in ((UC_ARM_REG_R0, 0xC3000300), (UC_ARM_REG_R1, 0xC0BE5B50),
                       (UC_ARM_REG_R2, 0xC3000600), (UC_ARM_REG_R6, 0xC3000700),
                       (UC_ARM_REG_LR, 0xC043B92C), (UC_ARM_REG_SP, T.STACK - 0x1000)):
        lm.reg_write(reg, value)
    low.stop_at.add(0xC043B92C)
    lm.emu_start(PL.PIK_HOOK, 0xC043B92C, count=2_000_000)
    assert list(struct.unpack("<9I", lm.mem_read(PL.AXIS, 36))) == ax120

    # Mutate the delivered BIN, not shared source: move one runtime declaration
    # into unused private cave so stage2 no longer journals that native word.
    mutant = bytearray(cam.blob)
    index = next(i for i, (a, _, _) in enumerate(records) if a == runtime[0])
    struct.pack_into("<I", mutant, 16 + index * 8, 0xC0732C80)
    broken = SensorCamera(directory, blob=bytes(mutant))
    broken.boot()
    j = broken.word(broken.registered[0][0] + 8)
    covered = set()
    while broken.word(j):
        a, size = broken.word(j), broken.word(j + 4)
        covered.update(range(a, a + size, 4))
        j += 8 + size
    assert runtime[0] not in covered, "journal mutation was not exercised"
    missing_runtime = set(runtime) - covered
    assert missing_runtime, "coverage check failed to detect removed runtime declaration"
    # Removing the stage2 alignment from the exact card must fail at entry.
    marker = bytes.fromhex("0d40a0e107d0cde300c0a0e13cff2fe104d0a0e1")
    assert cam.blob.count(marker) == 1
    mutant = bytearray(cam.blob)
    offset = mutant.index(marker) + 4
    mutant[offset:offset + 4] = bytes.fromhex("0000a0e1")
    try:
        SensorCamera(directory, blob=bytes(mutant)).boot()
    except AssertionError as error:
        assert error.args and isinstance(error.args[0], tuple), error
    else:
        raise AssertionError("unaligned entry mutation escaped detection")
    return dict(directory=str(directory), checks=["exact-bytes", "entry-ABI", "cache-order",
                "journal-146-runtime-words", "power-off-twice", "warm-image",
                "saved-selection", "MOV-guard", "missing-BIN", "packaged-RAW14-picker",
                "packaged-native-240-menu", "packaged-240-summary-visibility",
                "packaged-240-LV-text-and-preserved-15", "packaged-240-picker-and-FrameRate",
                "journal-coverage-mutation", "entry-alignment-mutation"], artifacts=manifest["artifacts"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--axis-preset")
    args = parser.parse_args()
    output = args.out or Path(tempfile.mkdtemp(prefix="res-lab-card-test-"))
    output.mkdir(parents=True, exist_ok=True)
    results = []
    axis = None
    if args.axis_preset:
        from imx410_axis import preset_axis
        axis, _ = preset_axis(PL.Registry(), args.axis_preset)
    # Fast Start 3 is a supported dev-card variant (SUP_BUILD_RULES: a product that
    # supports Fast verifies its own plain, debug AND Fast combinations).
    for fast in (False, True):
        for debug in (False, True):
            name = ("fast-" if fast else "") + ("debug" if debug else "plain")
            directory = output / name
            B.build(directory, debug=debug, fast=fast, axis=axis)
            results.append(verify(directory))
            print(f"PASS {name}: {len(results[-1]['checks'])} checks", flush=True)
            variant = output / f"{name}-alternate-axis"
            alternate_axis = list(axis or PL.INITIAL_AXIS)
            alternate_axis[5] = 1600
            B.build(variant, debug=debug, axis=alternate_axis, fast=fast)
            assert (variant / "AutoRun.txt").read_bytes() == (directory / "AutoRun.txt").read_bytes()
            assert (variant / "fpSup.BIN").read_bytes() != (directory / "fpSup.BIN").read_bytes()
            if fast:
                ui = sorted((directory / "FPSUPUI").glob("*.BIN"))
                assert [u.name for u in ui] == [f"{i}.BIN" for i in range(5)], ui
                m = json.loads((directory / "MANIFEST.json").read_text())
                assert m["fast"] and m["persistent_settings_write"], m
                assert (m["loader_hook_mark"] is not None) == debug, m
    (output / "verification.json").write_text(json.dumps(dict(cards=results, autorun_independent=True,
                   hardware_verified=False, stubs="worker spawn, file/allocator/cache/OS services, native getters, original setter body, inactive LV",
                   fast_note="Fast cards pass the same exact-BIN checks; the settings-block store and the warm loader-hook path are covered by the shared test_loader_hook, not emulated here"), indent=2) + "\n")
    print(f"PASS payload-only changes preserve AutoRun; report: {output / 'verification.json'}")


if __name__ == "__main__":
    main()
