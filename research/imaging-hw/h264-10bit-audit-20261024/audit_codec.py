#!/usr/bin/env python3
"""Offline, hash-pinned fp codec investigation. No device or USB access.

Executes selected original ARM routines against simulated RAM/MMIO. External
OS/power calls are explicit stubs; the codec hardware and its control ISA are
NOT emulated. Register writes never establish working encoded pixel precision.
"""
from __future__ import annotations

import hashlib
from importlib.metadata import version
from itertools import product
import json
from pathlib import Path
import re
import struct

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn import arm_const as R

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
BASE = 0xC0000000
EXPECTED = "aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622"
ROM = (ROOT / "out/seg0_c0000000.bin").read_bytes()
if hashlib.sha256(ROM).hexdigest() != EXPECTED:
    raise RuntimeError("Unexpected firmware; review all addresses")

SOURCE_PATH = ROOT / "out/decomp/full/blk_c07.c"
SOURCE = SOURCE_PATH.read_text()
FUNCTIONS = {}
for m in re.finditer(r"/\* ==== ([^\n]+) @ ([0-9a-f]{8}) ==== \*/(.*?)(?=\n/\* ==== |\Z)", SOURCE, re.S):
    FUNCTIONS[int(m[2], 16)] = (m[0], SOURCE.count("\n", 0, m.start()) + 1)
STARTS = sorted(FUNCTIONS)

# Only these ROM functions may execute. Every other firmware transfer must
# be an explicit stub below, or the audit fails before executing it.
APPROVED = [
    0xC0708598, 0xC0709158, 0xC070D858, 0xC070CAF0, 0xC070CED8,
    0xC070C578, 0xC070AB40, 0xC070D638, 0xC070E8D8,
    0xC07254E0, 0xC0725A38, 0xC0725AD0, 0xC0725AF0,
    0xC0725B30, 0xC0725B58, 0xC0725B78, 0xC0725B98,
    0xC0725C08, 0xC0725C28, 0xC0725C78,
    0xC0709A80, 0xC070A7E8, 0xC070B580, 0xC070A870,
    0xC070A890, 0xC070A8B0, 0xC070D4F8,
]
RANGES = [(a, STARTS[STARTS.index(a) + 1]) for a in APPROVED]


class Harness:
    INPUT, STACK, STOP = 0x20000000, 0x1000FFF0, 0x10010000

    def __init__(self):
        self.uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        for a, n in [(BASE, 0x4000000), (0x300C0000, 0x1000), (0x30002000, 0x1000),
                     (0x10000000, 0x11000), (self.INPUT, 0x80000)]:
            self.uc.mem_map(a, n)
        self.uc.mem_write(BASE, ROM)
        self.uc.hook_add(UC_HOOK_CODE, self.code)
        self.uc.hook_add(UC_HOOK_MEM_WRITE, self.write)
        self.reset()

    def reset(self):
        self.uc.mem_write(0xC38D0000, bytes(0x10000))
        self.uc.mem_write(0x300C0000, bytes(0x1000))
        self.uc.mem_write(self.INPUT, bytes(0x80000))
        self.captured = []
        self.events = []
        self.mmio = []
        self.done = False

    def u32(self, a):
        return struct.unpack("<I", self.uc.mem_read(a, 4))[0]

    def put(self, a, v):
        self.uc.mem_write(a, struct.pack("<I", v & 0xFFFFFFFF))

    def code(self, uc, a, size, _):
        if a == self.STOP:
            self.done = True
            uc.emu_stop()
            return
        args = [uc.reg_read(getattr(R, f"UC_ARM_REG_R{i}")) for i in range(4)]
        if a == 0xC0015058:  # memset
            assert args[2] < 0x20000
            uc.mem_write(args[0], bytes([args[1] & 255]) * args[2])
            result = args[0]
        elif a == 0xC001510C:  # memcpy
            assert args[2] < 0x40000
            uc.mem_write(args[0], bytes(uc.mem_read(args[1], args[2])))
            result = args[0]
        elif a in {0xC01F8C04, 0xC070A928}:
            # Semaphore validity and hardware command/wait are assumptions.
            # This checks the host-side copy/register path, not codec boot.
            self.events.append(dict(address=hex(a), args=args))
            result = 0
        elif a in {0xC0708C60, 0xC07095A8, 0xC062EF10, 0xC0708640, 0xC0708668, 0xC0708978}:
            self.events.append(dict(address=hex(a), args=args))
            if a == 0xC0708978:
                self.captured.append(list(struct.unpack("<65I", uc.mem_read(args[1], 0x104))))
            result = 0
        else:
            if not any(lo <= a < hi for lo, hi in RANGES):
                raise AssertionError(f"Unapproved ROM execution {a:08x}")
            return
        # These are original vendor routines, not our injected AAPCS code.
        # C07254E0 pushes 16 bytes then subtracts 0x10c: its own call sites
        # are 4-byte aligned. Preserve/record that fact instead of silently
        # changing the original stack frame to meet an 8-byte assumption.
        assert uc.reg_read(R.UC_ARM_REG_SP) % 4 == 0
        lr = uc.reg_read(R.UC_ARM_REG_LR)
        for n in (0, 1, 2, 3, 12):
            uc.reg_write(getattr(R, f"UC_ARM_REG_R{n}"), 0xBAD00000 + n)
        uc.reg_write(R.UC_ARM_REG_R0, result)
        uc.reg_write(R.UC_ARM_REG_PC, lr)

    def write(self, uc, access, a, size, value, _):
        if 0x300C0000 <= a < 0x300C1000:
            self.mmio.append(dict(address=hex(a), size=size, value=value))

    def call(self, address, *args):
        self.done = False
        for n in range(13):
            uc_reg = getattr(R, f"UC_ARM_REG_R{n}")
            self.uc.reg_write(uc_reg, 0x55550000 + n if 4 <= n <= 11 else 0)
        self.uc.reg_write(R.UC_ARM_REG_SP, self.STACK)
        self.uc.reg_write(R.UC_ARM_REG_LR, self.STOP)
        for i, v in enumerate(args):
            if i < 4:
                self.uc.reg_write(getattr(R, f"UC_ARM_REG_R{i}"), v)
            else:
                self.put(self.STACK + (i - 4) * 4, v)
        self.uc.emu_start(address | 1, self.STOP + 4, count=100000)
        assert self.done, f"Instruction limit at {self.uc.reg_read(R.UC_ARM_REG_PC):08x}"
        assert self.uc.reg_read(R.UC_ARM_REG_SP) == self.STACK
        for n in range(4, 12):
            assert self.uc.reg_read(getattr(R, f"UC_ARM_REG_R{n}")) == 0x55550000 + n
        return self.uc.reg_read(R.UC_ARM_REG_R0)


def main():
    h = Harness()
    setters = []
    for fn, reg, mask, expected in [
        (0xC070C578, 0x300C020C, 3, [0, 1, 2, 3, 0]),
        (0xC070AB40, 0x300C02C0, 0x18, [0, 8, 16, 0, 0]),
        (0xC070D638, 0x300C0238, 7, [0, 5, 3, 0, 0]),
    ]:
        for value in range(5):
            h.reset()
            h.put(reg, 0xA5A5)
            h.call(fn, value)
            actual = h.u32(reg)
            assert actual == (0xA5A5 & ~mask) | expected[value]
            setters.append(dict(function=hex(fn), input=value, register=hex(reg), value=actual))

    # Exercise the real SDK descriptor builder and its pure conversion helpers.
    # The OS/codec entry calls are stubbed; descriptor bytes are captured BEFORE
    # the hardware entry. Inputs here are explicit synthetic SDK scenarios.
    wrapper = []
    for (width, height), rate_enum, profile, sdk_option in product(
            [(1920, 1080), (3840, 2160)], range(11), range(4), range(3)):
        h.reset()
        p = [0] * 29
        p[0] = p[1] = rate_enum
        p[2], p[3], p[4], p[5] = 100000, width, height, 0x21000000
        p[0x16], p[0x17], p[0x18], p[0x19], p[0x1A] = 0, 0, profile, 0, sdk_option
        h.uc.mem_write(h.INPUT, struct.pack("<29I", *p))
        assert h.call(0xC07254E0, h.INPUT) == 0
        assert len(h.captured) == 1
        d = h.captured[0]
        assert d[5] == 2 and d[0x2A] == 0 and d[0x40] == 0
        assert d[0x1A] == [2, 1, 0, 0][profile]
        wrapper.append(dict(width=width, height=height, sdk_rate_enum=rate_enum, sdk_profile=profile,
                            sdk_option_1a=sdk_option, codec_mode=h.events[-1]["args"][0],
                            descriptor_words=d))

    # Use the ORIGINAL QP table. No table or instruction bytes are patched.
    qp = []
    cases = [(1920, 1080, 2997, 100000, 1), (1920, 1080, 2997, 50000, 15),
             (1920, 1080, 4800, 50000, 15), (1920, 1080, 5994, 50000, 15),
             (1920, 1080, 5000, 50000, 15), (3840, 2160, 2997, 400000, 1),
             (1920, 1080, 2997, 20000, 15)]
    for width, height, rate, bitrate, gop in cases:
        for profile in range(3):
            h.reset()
            d = [0] * 65
            d[0], d[2], d[4], d[0x18], d[0x1A] = rate, bitrate, width | (height << 16), gop, profile
            h.uc.mem_write(h.INPUT, struct.pack("<65I", *d))
            h.call(0xC070C578, profile)
            h.call(0xC070CAF0, h.INPUT)
            actual = h.u32(0x300C020C) & 3
            expected = (3 if profile == 2 and bitrate >= 50000 and
                        not (rate in (4800, 5000) and gop > 1) else profile)
            # The 4K high-bitrate scenario and FHD 50/100 Mbps scenarios use
            # table entries with minima 4; the 20 Mbps scenario uses 19/16.
            assert actual == expected, (width, rate, bitrate, gop, profile, actual)
            qp.append(dict(width=width, height=height, rate=rate, bitrate_kbps=bitrate,
                           gop=gop, requested_profile_selector=profile,
                           resulting_profile_selector=actual,
                           qp_i_min=h.u32(0xC38D6110), qp_p_min=h.u32(0xC38D6118),
                           mmio_writes=h.mmio))

    images = []
    for address in range(0xC2EB4390, 0xC2EF4390, 0x10000):
        data = ROM[address-BASE:address-BASE+0x10000]
        nonzero = [i for i, v in enumerate(data) if v]
        images.append(dict(address=hex(address), size=len(data),
                           sha256=hashlib.sha256(data).hexdigest(),
                           first_word=hex(struct.unpack_from("<I", data)[0]),
                           nonzero_bytes=len(nonzero), last_nonzero_offset=hex(nonzero[-1]),
                           limitation="64 KiB partitions by inspection; execution/bank selection not established"))

    initialization = []
    for mode, alternate in product([0, 5, 8, 9, 10, 11], [0, 1]):
        h.reset()
        destination = h.INPUT + 0x10000
        assert h.call(0xC0709A80, mode, destination, 0, alternate) == 0
        size = 0x10000 if alternate else 0x30000
        source = 0xC2EE4390 if alternate else 0xC2EB4390
        copied = bytes(h.uc.mem_read(destination, size))
        assert copied == ROM[source-BASE:source-BASE+size]
        assert h.u32(0x300C03F8) & 1 == int(8 <= mode <= 11)
        encoded_address = ((destination + BASE) & 0xFFFFFFFF) >> 3
        assert h.u32(0x300C0100) == encoded_address >> 16
        assert h.u32(0x300C0104) == encoded_address & 0xFFFF
        initialization.append(dict(mode=mode, alternate=alternate, control_source=hex(source),
            copied_bytes=size, copied_sha256=hashlib.sha256(copied).hexdigest(),
            register_300c03f8=h.u32(0x300C03F8), mmio_writes=h.mmio,
            limitation="OS validity and command completion stubbed; no control-ISA execution or silicon validation"))

    refs = []
    for width, height in [(1920, 1080), (3840, 2160)]:
        h.reset()
        h.call(0xC070E8D8, 0, width, height, 0, 0, h.INPUT, h.INPUT + 4)
        y, uv = h.u32(h.INPUT), h.u32(h.INPUT+4)
        assert y == ((width+63)//64)*((height+255)//256)*0xC000
        assert uv == ((width+63)//64)*(((height//2)+255)//256)*0xC000
        refs.append(dict(width=width, height=height, first_region_bytes=y, second_region_bytes=uv,
                         limitation="allocation arithmetic only; sample precision and frame count not established"))

    # Reuse existing observations only. Zero DITHER shadow words in standby
    # must not be generalized to REC or to the precision of the pixel output.
    capture = ROOT / "projects/lut-sup/validation/20261009-native-controls-trial-01/report.json"
    captured_bytes = capture.read_bytes()
    dither_samples = []
    def walk(value, path=""):
        if isinstance(value, dict):
            for key, child in value.items():
                if "PST_TOP DITHER" in key and isinstance(child, dict) and "words" in child:
                    dither_samples.append(dict(path=path + "/" + key, **child))
                else:
                    walk(child, path + "/" + key)
        elif isinstance(value, list):
            for i, child in enumerate(value):
                walk(child, path + "/" + str(i))
    walk(json.loads(captured_bytes))
    assert len(dither_samples) == 252
    assert all(item["words"] == [0, 0] for item in dither_samples)

    # Inventory every existing decompiled call to the ISP packer, including
    # paths outside the MOV frame setup examined in the previous audit.
    isp_path = ROOT / "out/decomp/full/blk_c01.c"
    isp = isp_path.read_text()
    isp_calls, isp_excerpts = [], []
    for match in re.finditer(r"(?m)^\s+FUN_c01570d0\([^\n]+", isp):
        header = isp.rfind("/* ==== ", 0, match.start())
        owner = re.match(r"/\* ==== ([^\n]+) @ ([0-9a-f]{8})", isp[header:])
        line = isp.count("\n", 0, match.start()) + 1
        lines = isp.splitlines()
        isp_calls.append(dict(caller=hex(int(owner[2], 16)), caller_name=owner[1],
                              source=str(isp_path.relative_to(ROOT)), line=line,
                              call=match[0].strip()))
        isp_excerpts.append(f"/* {isp_path.relative_to(ROOT)}:{line}; {owner[1]} */\n" +
                            "\n".join(lines[max(0, line-34):line+5]))
    assert len(isp_calls) == 8 and len({item["caller"] for item in isp_calls}) == 6

    h.reset()
    try:
        h.call(0xC0001000)
    except AssertionError as error:
        assert "Unapproved ROM execution" in str(error)
    else:
        raise AssertionError("Strict execution guard did not reject an unapproved address")

    records, excerpts, disassembly = [], [], []
    cs = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
    for a in APPROVED:
        source, line = FUNCTIONS[a]
        end = STARTS[STARTS.index(a)+1]
        data = ROM[a-BASE:end-BASE]
        records.append(dict(address=hex(a), end=hex(end), source=str(SOURCE_PATH.relative_to(ROOT)),
                            line=line, sha256=hashlib.sha256(data).hexdigest()))
        excerpts.append(f"/* {SOURCE_PATH.relative_to(ROOT)}:{line} */\n{source}")
        disassembly.append(f"\n/* ROM {a:08x}..{end:08x} */")
        for insn in cs.disasm(data, a):
            disassembly.append(f"{insn.address:08x} {insn.bytes.hex():10} {insn.mnemonic:10} {insn.op_str}")
    report = dict(date="2026-10-24", firmware_sha256=EXPECTED,
                  audit_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  decomp_sha256=hashlib.sha256(SOURCE_PATH.read_bytes()).hexdigest(),
                  runtime=dict(unicorn=version("unicorn"), capstone=version("capstone")),
                  scope="offline ARM execution against simulated RAM/MMIO; no codec pixel model or camera I/O",
                  functions=records, setter_cases=setters, sdk_descriptor_cases=wrapper,
                  native_qp_table_cases=qp, control_partitions=images, buffer_size_cases=refs,
                  initialization_cases=initialization,
                  isp_packer_calls=isp_calls,
                  strict_execution_guard="unapproved ROM address rejected before execution",
                  saved_dither_observations=dict(source=str(capture.relative_to(ROOT)),
                      sha256=hashlib.sha256(captured_bytes).hexdigest(), sample_count=len(dither_samples),
                      values=[0, 0], limitation="existing CINE standby shadow snapshots; no MOV/REC precision claim"),
                  verdict="No verified 10-bit path. Selector 3 is reachable automatically without changing source packing.")
    HERE.mkdir(exist_ok=True)
    (HERE / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    (HERE / "evidence.c").write_text("\n".join(excerpts))
    (HERE / "disassembly.txt").write_text("\n".join(disassembly) + "\n")
    (HERE / "isp-packer-callers.c").write_text("\n\n".join(isp_excerpts) + "\n")
    print(json.dumps(dict(setter_cases=len(setters), descriptor_cases=len(wrapper),
                          qp_cases=len(qp), buffer_size_cases=len(refs),
                          initialization_cases=len(initialization),
                          functions=len(records), report=str(HERE / "report.json"))))


if __name__ == "__main__":
    main()
