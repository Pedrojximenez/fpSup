#!/usr/bin/env python3
"""Generate two ColorMatrix-only candidates, preserving the original RAW bytes.

C applies the same per-body normalization and integer truncation as the fp
firmware's DNG writer, but selects its normal matrices instead of OFF matrices.
D copies Adobe Camera OFF's ColorMatrix payloads only, not its full profile.
Neither candidate is a validated camera calibration.
"""

from hashlib import sha256
from io import BytesIO
from pathlib import Path
import json
import struct
import subprocess

import numpy as np
import rawpy


OUT = Path(__file__).resolve().parent
PROJECT = OUT.parent.parent
A_PATH = OUT / "A_original.DNG"
SOURCE = PROJECT / (
    "projects/gyro-sup/captures/fpGFTest_stage4_20260817_2226/"
    "CINEMA/A001_001/A001_001_20260817_000249.DNG"
)
ROM_PATH = PROJECT / "out/MAIN_c0000000.bin"
NORMAL_CAPTURE = PROJECT / (
    "research/imaging-hw/color-characterisation/captures/_SDI5625.DNG"
)
DCP_PATH = Path(
    "/Library/Application Support/Adobe/CameraRaw/CameraProfiles/Camera/"
    "Sigma fp/SIGMA fp Camera_OFF.dcp"
)
C_PATH = OUT / "C_firmware_normal.DNG"
D_PATH = OUT / "D_adobe_cm_only.DNG"
REPORT_PATH = OUT / "candidate-verification.json"
EXPECTED_A_SHA256 = "8b838d0a27b5a8a11a39ff903933793930706b7a6b46f7a4ef8e08a400e2c324"
ROM_BASE = 0xC0000000
NORMAL_ADDRESSES = {50721: 0xC096FD2C, 50722: 0xC096FC9C}
OFF_ADDRESSES = {50721: 0xC096FD74, 50722: 0xC096FCE4}
EXPECTED_C_NUMERATORS = {
    50721: [[14643, -7511, -5102], [-3330, 11711, -604], [-748, 1634, 5867]],
    50722: [[8252, -2044, -1744], [-4961, 11648, 631], [-1137, 1581, 3549]],
}
TYPE_SIZE = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2,
             9: 4, 10: 8, 11: 4, 12: 8, 13: 4}


class RootIFD:
    def __init__(self, data, accepted_magic=(42,)):
        self.data = data
        self.endian = {b"II": "<", b"MM": ">"}[data[:2]]
        magic, root = struct.unpack_from(self.endian + "HI", data, 2)
        assert magic in accepted_magic, f"Unexpected TIFF-like magic: {magic}"
        count = struct.unpack_from(self.endian + "H", data, root)[0]
        self.entries = {}
        for index in range(count):
            position = root + 2 + 12 * index
            tag, typ, number = struct.unpack_from(self.endian + "HHI", data, position)
            size = TYPE_SIZE[typ] * number
            start = position + 8 if size <= 4 else struct.unpack_from(
                self.endian + "I", data, position + 8
            )[0]
            assert start + size <= len(data)
            self.entries[tag] = (typ, number, start, size)

    def payload(self, tag):
        _, _, start, size = self.entries[tag]
        return self.data[start:start + size]

    def integers(self, tag):
        typ, number, start, _ = self.entries[tag]
        return struct.unpack_from(
            self.endian + {3: "H", 4: "I"}[typ] * number, self.data, start
        )

    def matrix(self, tag):
        assert self.entries[tag][0:2] == (10, 9)
        rational = np.array(struct.unpack(self.endian + "18i", self.payload(tag)))
        return (rational[::2] / rational[1::2]).reshape(3, 3)


def body_calibration(path):
    result = subprocess.check_output(
        ["exiftool", "-j", "-n", "-CameraCalibration", str(path)], text=True
    )
    values = json.loads(result)[0]["CameraCalibration"]
    return np.array([float(value) for value in values.split()]).reshape(3, 3)


def firmware_payload(matrix, inverse_calibration, endian):
    # The writer uses signed conversion toward zero after multiplication by 10000.
    numerators = np.trunc((inverse_calibration @ matrix) * 10000).astype(np.int64)
    payload = b"".join(
        struct.pack(endian + "ii", int(value), 10000) for value in numerators.flat
    )
    return payload, numerators


def decode_check(data):
    with rawpy.imread(BytesIO(data)) as raw:
        bayer = raw.raw_image.copy()
        rgb = raw.postprocess(
            use_camera_wb=True, no_auto_bright=True, output_bps=16,
            gamma=(1, 1), output_color=rawpy.ColorSpace.XYZ,
            demosaic_algorithm=rawpy.DemosaicAlgorithm.LINEAR,
        )
    assert rgb.dtype == np.uint16 and rgb.ndim == 3 and rgb.shape[-1] == 3
    return bayer, {
        "library": "rawpy/LibRaw",
        "rawpy_version": rawpy.__version__,
        "bayer_shape": list(bayer.shape),
        "bayer_sha256": sha256(bayer.tobytes()).hexdigest(),
        "rgb_decode_succeeded": True,
        "rgb_shape": list(rgb.shape),
        "rgb_sha256": sha256(rgb.tobytes()).hexdigest(),
        "note": "File-readability cross-check, not a Resolve rendering or color-accuracy test.",
    }


def main():
    for path in (C_PATH, D_PATH, REPORT_PATH):
        if path.exists():
            raise FileExistsError(f"Refusing to overwrite {path}")
    original = A_PATH.read_bytes()
    assert sha256(original).hexdigest() == EXPECTED_A_SHA256
    assert original == SOURCE.read_bytes(), "A must remain byte-identical to source"
    a = RootIFD(original)
    dcp_data = DCP_PATH.read_bytes()
    dcp = RootIFD(dcp_data, accepted_magic=(0x4352,))
    normal = RootIFD(NORMAL_CAPTURE.read_bytes())
    assert a.endian == dcp.endian == normal.endian
    assert dcp.payload(50708).rstrip(b"\0") == b"SIGMA fp"
    for parsed in (a, dcp, normal):
        assert parsed.integers(50778) == (17,)
        assert parsed.integers(50779) == (21,)
    assert a.integers(262) == (32803,) and a.integers(259) == (1,)
    assert 50964 not in a.entries and 50965 not in a.entries

    calibration = body_calibration(A_PATH)
    assert np.array_equal(calibration, body_calibration(NORMAL_CAPTURE))
    inverse_calibration = np.linalg.inv(calibration)
    rom = ROM_PATH.read_bytes()
    candidates = {"C": bytearray(original), "D": bytearray(original)}
    allowed = np.zeros(len(original), dtype=bool)
    matrices = {}
    for tag in (50721, 50722):
        typ, count, start, length = a.entries[tag]
        assert (typ, count, length) == (10, 9, 72)
        assert dcp.entries[tag][0:2] == (10, 9)
        firmware_normal = np.array(struct.unpack_from(
            "<9d", rom, NORMAL_ADDRESSES[tag] - ROM_BASE
        )).reshape(3, 3)
        firmware_off = np.array(struct.unpack_from(
            "<9d", rom, OFF_ADDRESSES[tag] - ROM_BASE
        )).reshape(3, 3)
        reconstructed_off, _ = firmware_payload(firmware_off, inverse_calibration, a.endian)
        assert reconstructed_off == a.payload(tag), "OFF reconstruction failed"
        c_payload, c_numerators = firmware_payload(
            firmware_normal, inverse_calibration, a.endian
        )
        assert np.array_equal(c_numerators, EXPECTED_C_NUMERATORS[tag])
        assert c_payload == normal.payload(tag), "C differs from same-body normal capture"
        d_payload = dcp.payload(tag)
        assert len(c_payload) == len(d_payload) == length
        candidates["C"][start:start + length] = c_payload
        candidates["D"][start:start + length] = d_payload
        allowed[start:start + length] = True
        matrices[str(tag)] = {
            "name": "ColorMatrix1" if tag == 50721 else "ColorMatrix2",
            "payload_offset": start, "payload_length": length,
            "A": a.matrix(tag).tolist(),
            "C": (c_numerators / 10000).tolist(),
            "D": dcp.matrix(tag).tolist(),
            "C_denominator": 10000,
            "normal_ROM_virtual_address": hex(NORMAL_ADDRESSES[tag]),
            "OFF_ROM_virtual_address": hex(OFF_ADDRESSES[tag]),
            "normal_ROM_matrix": firmware_normal.tolist(),
            "OFF_ROM_matrix": firmware_off.tolist(),
            "OFF_reconstruction_payload_exact": True,
            "C_matches_genuine_same_body_normal_capture_payload": True,
            "D_payload_exact_copy_from_DCP": True,
        }

    offsets, lengths = a.integers(273), a.integers(279)
    assert len(offsets) == len(lengths)
    strips = [{"offset": offset, "length": length} for offset, length in zip(offsets, lengths)]
    raw_sha = sha256()
    for strip in strips:
        start, length = strip["offset"], strip["length"]
        assert start + length <= len(original)
        assert not allowed[start:start + length].any()
        raw_sha.update(original[start:start + length])
    bayer_a, decode_a = decode_check(original)
    report = {
        "purpose": "ColorMatrix-only candidate comparison; not validated color calibration",
        "A": str(A_PATH), "source": str(SOURCE),
        "A_identical_to_source": True, "A_sha256": EXPECTED_A_SHA256,
        "ROM_source": str(ROM_PATH), "ROM_sha256": sha256(rom).hexdigest(),
        "Adobe_profile_source": str(DCP_PATH),
        "Adobe_profile_sha256": sha256(dcp_data).hexdigest(),
        "normal_capture_cross_check": str(NORMAL_CAPTURE),
        "Sigma_private_CameraCalibration": calibration.tolist(),
        "C_method": "inverse(CameraCalibration) times normal ROM; trunc toward zero after times10000",
        "D_method": "Exact ColorMatrix1/2 payload copy; no per-body scaling or ForwardMatrix/Look/Tone copy",
        "retained_from_A": "RAW, AsShotNeutral, illuminants, tone/profile/look payloads and every byte outside two CM payloads",
        "raw_strips": strips, "raw_payload_sha256_A": raw_sha.hexdigest(),
        "matrices": matrices, "A_decode": decode_a,
        "Resolve_candidate_test_performed": False,
        "color_accuracy_validated": False,
        "candidates": {},
    }
    for key, path in (("C", C_PATH), ("D", D_PATH)):
        data = bytes(candidates[key])
        diff = np.frombuffer(original, dtype=np.uint8) != np.frombuffer(data, dtype=np.uint8)
        assert diff.any() and not np.any(diff & ~allowed)
        candidate_raw_sha = sha256()
        for strip in strips:
            start, length = strip["offset"], strip["length"]
            candidate_raw_sha.update(data[start:start + length])
        assert candidate_raw_sha.digest() == raw_sha.digest()
        bayer, decoded = decode_check(data)
        assert np.array_equal(bayer, bayer_a)
        parsed = RootIFD(data)
        determinants = {str(tag): float(np.linalg.det(parsed.matrix(tag))) for tag in (50721, 50722)}
        assert all(value > 0 for value in determinants.values())
        report["candidates"][key] = {
            "path": str(path), "sha256": sha256(data).hexdigest(),
            "file_size_bytes": len(data), "changed_bytes": int(diff.sum()),
            "only_ColorMatrix_payloads_changed": True,
            "all_other_bytes_identical_to_A": True,
            "raw_payload_sha256": candidate_raw_sha.hexdigest(),
            "Bayer_array_identical_to_A": True,
            "matrix_determinants": determinants, "decode": decoded,
        }

    # All checks pass before any binary output is created. Never replace prior artifacts.
    for key, path in (("C", C_PATH), ("D", D_PATH)):
        with path.open("xb") as handle:
            handle.write(candidates[key])
        assert path.read_bytes() == candidates[key]
    with REPORT_PATH.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps(report["candidates"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
