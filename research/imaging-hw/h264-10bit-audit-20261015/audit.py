#!/usr/bin/env python3
"""Offline evidence extraction for the fp Ver.5.02 movie codec audit.

Reads existing firmware, decompilation and saved MOVs. No camera connection,
device access, firmware execution or installation is performed.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
BASE = 0xC0000000
EXPECTED_SHA256 = "aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622"

FUNCTIONS = {
    "blk_c03.c": [0xC0388680, 0xC0389CA8, 0xC038A3E8],
    "blk_c06.c": [0xC06B07A0, 0xC06B0AE0],
    "blk_c07.c": [
        0xC0708978, 0xC0708D28, 0xC0708F98,
        0xC0709A80, 0xC0709E50, 0xC070A7E8, 0xC070A870,
        0xC070A890, 0xC070A8B0, 0xC070AB40, 0xC070B330,
        0xC070B3E8, 0xC070B7A0, 0xC070C098, 0xC070C578,
        0xC070C930, 0xC070CAB0, 0xC070CAF0, 0xC070D638,
        0xC070D7C8, 0xC070D858, 0xC070E8D8, 0xC070EED0,
        0xC070F6D0, 0xC07101C0, 0xC071F3E8, 0xC071FCD8,
        0xC07254E0, 0xC0725800,
        0xC0725860, 0xC0725B30,
    ],
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Bits:
    def __init__(self, data: bytes):
        self.bits = "".join(f"{v:08b}" for v in data)
        self.pos = 0

    def read(self, n: int) -> int:
        if self.pos + n > len(self.bits):
            raise ValueError("Truncated SPS")
        result = int(self.bits[self.pos:self.pos + n], 2) if n else 0
        self.pos += n
        return result

    def ue(self) -> int:
        zeros = 0
        while self.read(1) == 0:
            zeros += 1
            if zeros > 31:
                raise ValueError("Invalid Exp-Golomb value")
        return (1 << zeros) - 1 + self.read(zeros)


def sps_precision(nal: bytes) -> dict:
    if nal[0] & 31 != 7:
        raise ValueError("Not an SPS NAL")
    # Remove emulation-prevention bytes from the RBSP, after the NAL header.
    rbsp = bytearray()
    zeros = 0
    for value in nal[1:]:
        if zeros >= 2 and value == 3:
            zeros = 0
            continue
        rbsp.append(value)
        zeros = zeros + 1 if value == 0 else 0
    r = Bits(bytes(rbsp))
    profile = r.read(8)
    constraints = r.read(8)
    level = r.read(8)
    sps_id = r.ue()
    chroma, luma_depth, chroma_depth = 1, 8, 8
    if profile in {100, 110, 122, 244, 44, 83, 86, 118, 128, 138, 139, 134, 135}:
        chroma = r.ue()
        if chroma == 3:
            r.read(1)
        luma_depth = 8 + r.ue()
        chroma_depth = 8 + r.ue()
    return dict(profile_idc=profile, constraint_byte=constraints, level_idc=level,
                seq_parameter_set_id=sps_id, chroma_format_idc=chroma,
                luma_bit_depth=luma_depth, chroma_bit_depth=chroma_depth,
                nal_hex=nal.hex())


def movie_evidence(path: Path) -> dict:
    data = path.read_bytes()
    offset = data.find(b"avcC")
    if offset < 4:
        raise ValueError(f"Missing avcC in {path}")
    size = struct.unpack_from(">I", data, offset - 4)[0]
    payload = data[offset + 4:offset - 4 + size]
    if payload[0] != 1:
        raise ValueError("Unsupported avcC version")
    count, pos = payload[5] & 31, 6
    sps = []
    for _ in range(count):
        n = struct.unpack_from(">H", payload, pos)[0]
        pos += 2
        sps.append(sps_precision(payload[pos:pos + n]))
        pos += n
    probe = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=codec_name,profile,width,height,pix_fmt,level,bits_per_raw_sample,r_frame_rate",
        "-of", "json", str(path),
    ], text=True))
    for item in sps:
        if item["luma_bit_depth"] != int(probe["streams"][0]["bits_per_raw_sample"]):
            raise ValueError("SPS precision disagrees with ffprobe")
    return dict(path=str(path.relative_to(ROOT)), sha256=digest(data),
                avcC_offset=hex(offset), sps=sps, ffprobe=probe["streams"])


def main() -> None:
    rom_path = ROOT / "out/seg0_c0000000.bin"
    rom = rom_path.read_bytes()
    if digest(rom) != EXPECTED_SHA256:
        raise ValueError("Unexpected fp firmware image; offsets need review")
    functions = []
    excerpts = []
    for filename, addresses in FUNCTIONS.items():
        path = ROOT / "out/decomp/full" / filename
        source = path.read_text()
        for address in addresses:
            match = re.search(
                r"/\* ==== ([^\n]+) @ " + f"{address:08x}" +
                r" ==== \*/.*?(?=\n/\* ==== |\Z)", source, re.S)
            if match is None:
                raise ValueError(f"Missing function {address:08x}")
            line = source.count("\n", 0, match.start()) + 1
            functions.append(dict(address=hex(address), name=match[1],
                                  source=str(path.relative_to(ROOT)), line=line))
            excerpts.append(f"/* {path.relative_to(ROOT)}:{line} */\n{match[0]}")
    microcode = []
    for address, size, purpose in [
        (0xC2EB4390, 0x30000, "normal codec control image copied by C070A870"),
        (0xC2EE4390, 0x10000, "alternate control image copied by C070A890"),
    ]:
        block = rom[address - BASE:address - BASE + size]
        microcode.append(dict(address=hex(address), size=size,
                              sha256=digest(block), purpose=purpose))
    rows = []
    for i in range(26):
        address = 0xC0B9BA08 + 36 * i
        values = struct.unpack_from("<9I", rom, address - BASE)
        rows.append(dict(address=hex(address), words=list(values)))
    movies = [movie_evidence(p) for p in sorted(
        (ROOT / "projects/rawview/captures/2026-09-24-movcheck").glob("*.MOV"))]
    if len(movies) != 2:
        raise ValueError("Expected the two existing fp MOV reference captures")
    report = dict(
        date="2026-10-15", scope="offline static analysis and existing MOV parsing",
        firmware=dict(path=str(rom_path.relative_to(ROOT)), size=len(rom), sha256=digest(rom)),
        functions=functions, codec_control_images=microcode,
        movie_mode_table=dict(address="0xc0b9ba08", row_bytes=36, rows=rows),
        saved_movies=movies,
        hevc_candidate=dict(
            selector="mode 8..11 sets 0x300c03f8 bit 0 at C0709A80",
            max_luma_picture_sizes=[36864, 122880, 245760, 552960, 983040, 2228224, 8912896],
            source="C070C930; constants equal HEVC level limits",
            external_comparison="https://github.com/FFmpeg/FFmpeg/blob/master/libavcodec/h265_profile_level.c",
            limitation="generic driver path; working silicon, Main10 support and precision unverified",
        ),
        h264_10bit_verdict="no verified enable path; physical impossibility not established",
    )
    (HERE / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    (HERE / "evidence.c").write_text("\n".join(excerpts))
    try:
        from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB
    except ImportError:
        raise RuntimeError("capstone is required for byte-level verification")
    cs = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
    lines = []
    for start, stop in [(0xC070A870, 0xC070A88E), (0xC070C578, 0xC070C5C8),
                        (0xC0709A80, 0xC0709B80), (0xC070AB40, 0xC070AB88),
                        (0xC070CAB0, 0xC070CAEC)]:
        lines.append(f"\n/* {start:08x}..{stop:08x} Thumb ROM bytes */")
        for insn in cs.disasm(rom[start - BASE:stop - BASE], start):
            lines.append(f"{insn.address:08x} {insn.bytes.hex():10} {insn.mnemonic:10} {insn.op_str}")
    (HERE / "disassembly.txt").write_text("\n".join(lines) + "\n")
    print(json.dumps(dict(functions=len(functions), saved_movies=len(movies),
                          report=str(HERE / "report.json")), ensure_ascii=False))


if __name__ == "__main__":
    main()
