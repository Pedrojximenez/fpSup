#!/usr/bin/env python3
"""Offline ARM check of the stock WAV header and an isolated 18p iXML proposal.

No camera access or card modification.  The candidate is patched only into
Unicorn memory at the two iXML speed lookups; the BWF timecode lookup and stock
WAV format object are left untouched.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import sys

from unicorn import UC_ARCH_ARM, UC_MODE_ARM, Uc
from unicorn.arm_const import (UC_ARM_REG_C1_C0_2, UC_ARM_REG_FPEXC,
                               UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_R0,
                               UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3,
                               UC_ARM_REG_R7, UC_ARM_REG_R10, UC_ARM_REG_SP)


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / "projects/open-gate/build"))
from armasm import assemble  # noqa: E402
from imx410_block import (AXIS_WORDS, RECIPE_WORDS, axis_words,
                          expected_recipe)  # noqa: E402
from imx410_full import Registry  # noqa: E402


FW = ROOT / "out/MAIN_c0000000.bin"
SHA256 = "92a8ee993f6c3d66c251e88d45a2ccd5135c6cf7342717784321c2ed506e2fb4"
BASE = 0xC0000000
AXIS, RECIPE = 0xC0732490, 0xC07324C0
FLAG, RATE18 = 0xC0731C08, 0xC0731C4C
CANDIDATE = 0xC0735000
IXML = 0xC0685B78
SPEED_CALLS = (0xC0685BF8, 0xC0685C04)
TIMECODE_CALL = 0xC0685BEC
WAVE_FORMAT = 0xC0685788
WAVE_OBJECT = 0xC31F848C
RAM, RAM_SIZE = 0x40000000, 0x40000
CONFIG, HEADER, STACK, DONE = RAM + 0x1000, RAM + 0x2000, RAM + 0x30000, RAM + 0x3F000


def p32(value: int) -> bytes:
    return struct.pack("<I", value)


def branch_link(site: int, target: int) -> int:
    delta = target - site - 8
    assert delta % 4 == 0 and -(1 << 25) <= delta < (1 << 25)
    return 0xEB000000 | ((delta >> 2) & 0xFFFFFF)


class StockAudio:
    def __init__(self, image: bytes, *, candidate: bool, marker=1, bit=14,
                 rate_index=11, bad_snapshot=False, movie_enum=1):
        self.uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        u = self.uc
        u.mem_map(BASE, (len(image) + 4095) & ~4095)
        u.mem_write(BASE, image)
        u.mem_map(0xC31F8000, 0x1000)
        u.mem_map(RAM, RAM_SIZE)
        u.reg_write(UC_ARM_REG_C1_C0_2, 0xF << 20)
        u.reg_write(UC_ARM_REG_FPEXC, 1 << 30)
        u.mem_write(WAVE_OBJECT, struct.pack("<3I", 0xC2E3629C, 0x20010, 48000))
        axis = axis_words(bit=14, rate="18", raster=(6064, 4042), mode=0x100)
        recipe = expected_recipe(Registry(), axis)
        assert recipe[9] == 1 and recipe[10] == 0 and recipe[18] == 18
        axis[0], axis[1] = bit, rate_index
        if bad_snapshot:
            recipe[0] ^= 1
        u.mem_write(AXIS, struct.pack(f"<{AXIS_WORDS}I", *axis))
        u.mem_write(RECIPE, struct.pack(f"<{RECIPE_WORDS}I", *recipe))
        u.mem_write(FLAG, p32(1))
        u.mem_write(RATE18, p32(marker))
        config = bytearray(0x30)
        struct.pack_into("<6H", config, 0, 2026, 10, 4, 12, 0, 0)
        struct.pack_into("<4I", config, 0x10, movie_enum, 1, 0, 24)
        u.mem_write(CONFIG, bytes(config))
        u.mem_write(HEADER, bytes(0x800))
        if candidate:
            original = tuple(struct.unpack_from("<I", image, a - BASE)[0]
                             for a in SPEED_CALLS)
            assert original == (0xEBFFFFC8, 0xEBFFFFC5), original
            assert struct.unpack_from("<I", image, TIMECODE_CALL - BASE)[0] == 0xEBFFFFCB
            code = assemble(HERE / "wav18_speed_candidate.S")
            u.mem_write(CANDIDATE, code)
            for site in SPEED_CALLS:
                u.mem_write(site, p32(branch_link(site, CANDIDATE)))
            self.candidate_bytes = len(code)
        else:
            self.candidate_bytes = 0

    def run(self, entry: int, args: tuple[int, ...], *, stop=DONE, count=500000):
        u = self.uc
        for reg, value in zip((UC_ARM_REG_R0, UC_ARM_REG_R1,
                               UC_ARM_REG_R2, UC_ARM_REG_R3), args):
            u.reg_write(reg, value)
        u.reg_write(UC_ARM_REG_SP, STACK)
        u.reg_write(UC_ARM_REG_LR, DONE)
        u.emu_start(entry, stop, count=count)
        assert u.reg_read(UC_ARM_REG_PC) == stop, hex(u.reg_read(UC_ARM_REG_PC))
        return u.reg_read(UC_ARM_REG_R0)

    def cstring(self, address: int) -> str:
        raw = bytes(self.uc.mem_read(address, 64))
        return raw.split(b"\0", 1)[0].decode("ascii")

    def three_speed_values(self) -> list[str]:
        # Stop after the third C0685B20 return, before the XML formatter.
        self.run(IXML, (HEADER, CONFIG), stop=0xC0685C08)
        u = self.uc
        return [self.cstring(u.reg_read(reg)) for reg in
                (UC_ARM_REG_R0, UC_ARM_REG_R10, UC_ARM_REG_R7)]

    def wave_header(self) -> bytes:
        self.run(WAVE_FORMAT, (WAVE_OBJECT, HEADER, 0x3AC + 192000, CONFIG))
        return bytes(self.uc.mem_read(HEADER, 0x3AC))


def verify() -> dict:
    image = FW.read_bytes()
    digest = hashlib.sha256(image).hexdigest()
    assert digest == SHA256, digest
    controls = []
    for case, options, want in (
        ("private18", {}, ["18/1", "18/1", "24000/1001"]),
        ("marker_off", {"marker": 0}, ["24000/1001"] * 3),
        ("raw12", {"bit": 12}, ["24000/1001"] * 3),
        ("native_axis", {"rate_index": 0}, ["24000/1001"] * 3),
        ("stale_snapshot", {"bad_snapshot": True}, ["24000/1001"] * 3),
        ("native24", {"movie_enum": 2}, ["24/1", "24/1", "24000/1001"]),
    ):
        trial = StockAudio(image, candidate=True, **options)
        speeds = trial.three_speed_values()
        assert speeds == want, (case, speeds, want)
        controls.append({"case": case, "master_current_timecode_rate": speeds})
    original = StockAudio(image, candidate=False)
    stock_speeds = original.three_speed_values()
    assert stock_speeds == ["24000/1001"] * 3

    # Check the complete native WAV formatter with and without the candidate.
    stock = StockAudio(image, candidate=False)
    proposed = StockAudio(image, candidate=True)
    a, b = stock.wave_header(), proposed.wave_header()
    for header in (a, b):
        assert header[:4] == b"RIFF" and header[8:12] == b"WAVE"
        assert header[0x38C:0x390] == b"fmt "
        assert struct.unpack_from("<H", header, 0x394)[0] == 1  # PCM
        assert struct.unpack_from("<H", header, 0x396)[0] == 2  # channels
        assert struct.unpack_from("<I", header, 0x398)[0] == 48000
        assert struct.unpack_from("<I", header, 0x39C)[0] == 192000
        assert struct.unpack_from("<H", header, 0x3A0)[0] == 4
        assert struct.unpack_from("<H", header, 0x3A2)[0] == 16
    assert a[:0x274] == b[:0x274]  # RIFF, bext, BWF TimeReference unchanged.
    assert a[0x38C:] == b[0x38C:]  # PCM fmt and data length unchanged.
    assert a[0x274:0x38C] != b[0x274:0x38C]  # Only iXML differs.
    assert struct.unpack_from("<Q", a, 0x166)[0] == struct.unpack_from("<Q", b, 0x166)[0]
    assert b"<MASTER_SPEED>18/1</MASTER_SPEED>" in b
    assert b"<CURRENT_SPEED>18/1</CURRENT_SPEED>" in b
    assert b"<TIMECODE_RATE>24000/1001</TIMECODE_RATE>" in b
    return {"firmware_sha256": digest,
            "candidate_bytes": proposed.candidate_bytes,
            "stock_three_speeds": stock_speeds,
            "controls": controls,
            "pcm": {"encoding": 1, "channels": 2, "sample_rate": 48000,
                    "bytes_per_second": 192000, "block_align": 4,
                    "bits_per_sample": 16},
            "bwf_time_reference": struct.unpack_from("<Q", b, 0x166)[0],
            "iXML_only_changed": True,
            "limits": ["Candidate exists only in Unicorn memory and validation files",
                       "Private 18p selection/REC/timecode bridge is not deployed",
                       "DSP hardware sample clock and live A/V sync are unmeasured"]}


if __name__ == "__main__":
    report = verify()
    out = HERE / "wav18_audio_candidate_unicorn.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
