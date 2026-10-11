#!/usr/bin/env python3
"""Create a controlled, metadata-only CinemaDNG decoder test.

A is a byte-identical copy of a genuine SIGMA fp CinemaDNG frame.
B changes only the existing ColorMatrix1/2 SRATIONAL payloads in place.
This is a deliberately perturbed profile, not a camera calibration.
"""

from fractions import Fraction
from hashlib import sha256
from pathlib import Path
import json
import struct

import numpy as np


SOURCE = Path(
    "/Users/dido/Developer.localized/SIGMAfp_re/projects/gyro-sup/captures/"
    "fpGFTest_stage4_20260817_2226/CINEMA/A001_001/"
    "A001_001_20260817_000249.DNG"
)
OUT = Path(__file__).resolve().parent
A_PATH = OUT / "A_original.DNG"
B_PATH = OUT / "B_matrix_probe.DNG"
REPORT_PATH = OUT / "verification.json"
WHITES = {
    50721: (Fraction("1.09850"), Fraction(1), Fraction("0.35585")),
    50722: (Fraction("0.95047"), Fraction(1), Fraction("1.08883")),
}
DENOMINATOR = 100_000_000
TYPE_SIZE = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2,
             9: 4, 10: 8, 11: 4, 12: 8, 13: 4}


def main():
    for path in (A_PATH, B_PATH, REPORT_PATH):
        if path.exists():
            raise FileExistsError(f"Refusing to overwrite {path}")

    original = SOURCE.read_bytes()
    endian = {b"II": "<", b"MM": ">"}[original[:2]]
    assert struct.unpack_from(endian + "H", original, 2)[0] == 42
    root = struct.unpack_from(endian + "I", original, 4)[0]
    count = struct.unpack_from(endian + "H", original, root)[0]
    entries = {}
    for idx in range(count):
        pos = root + 2 + 12 * idx
        tag, typ, number = struct.unpack_from(endian + "HHI", original, pos)
        size = TYPE_SIZE[typ] * number
        start = pos + 8 if size <= 4 else struct.unpack_from(
            endian + "I", original, pos + 8
        )[0]
        assert start + size <= len(original)
        entries[tag] = (typ, number, start, size)

    def integer_values(tag):
        typ, number, start, _ = entries[tag]
        return struct.unpack_from(endian + {3: "H", 4: "I"}[typ] * number,
                                  original, start)

    assert integer_values(262) == (32803,), "Expected CFA image in IFD0"
    assert integer_values(259) == (1,), "Expected uncompressed CinemaDNG"
    assert integer_values(50778) == (17,), "CM1 must use Standard A"
    assert integer_values(50779) == (21,), "CM2 must use D65"
    assert 50964 not in entries and 50965 not in entries, "Unexpected ForwardMatrix"

    patched = bytearray(original)
    allowed = np.zeros(len(original), dtype=bool)
    matrix_report = {}
    for tag, white in WHITES.items():
        typ, number, start, size = entries[tag]
        assert (typ, number, size) == (10, 9, 72)
        integers = struct.unpack_from(endian + "18i", original, start)
        old = [Fraction(integers[i], integers[i + 1]) for i in range(0, 18, 2)]
        new = []
        for row in range(3):
            x, y, z = old[row * 3: row * 3 + 3]
            new.extend((x / 2, y + (white[0] * x + white[2] * z) / 2, z / 2))
        payload = b"".join(
            struct.pack(endian + "ii", round(value * DENOMINATOR), DENOMINATOR)
            for value in new
        )
        patched[start:start + size] = payload
        allowed[start:start + size] = True
        quantized = [Fraction(round(v * DENOMINATOR), DENOMINATOR) for v in new]
        old_m = np.array(old, dtype=float).reshape(3, 3)
        new_m = np.array(quantized, dtype=float).reshape(3, 3)
        white_v = np.array(white, dtype=float)
        white_error = float(np.max(np.abs(old_m @ white_v - new_m @ white_v)))
        assert white_error < 2e-8
        assert np.linalg.det(old_m) * np.linalg.det(new_m) > 0
        assert abs(np.linalg.det(new_m) / np.linalg.det(old_m) - 0.25) < 1e-7
        matrix_report[str(tag)] = {
            "name": "ColorMatrix1" if tag == 50721 else "ColorMatrix2",
            "payload_offset": start,
            "payload_length": size,
            "calibration_white_XYZ": list(map(float, white)),
            "A": old_m.tolist(),
            "B": new_m.tolist(),
            "B_denominator": DENOMINATOR,
            "endpoint_camera_white_max_abs_error": white_error,
            "determinant_A": float(np.linalg.det(old_m)),
            "determinant_B": float(np.linalg.det(new_m)),
        }

    differences = np.frombuffer(original, dtype=np.uint8) != np.frombuffer(
        patched, dtype=np.uint8
    )
    assert differences.any()
    assert not np.any(differences & ~allowed), "Changed bytes outside ColorMatrix payloads"

    offsets = integer_values(273)
    lengths = integer_values(279)
    assert len(offsets) == len(lengths)
    pixel_a, pixel_b = sha256(), sha256()
    strips = []
    for offset, length in zip(offsets, lengths):
        assert offset + length <= len(original)
        assert not allowed[offset:offset + length].any()
        pixel_a.update(original[offset:offset + length])
        pixel_b.update(patched[offset:offset + length])
        strips.append({"offset": offset, "length": length})
    assert pixel_a.digest() == pixel_b.digest()

    # Exclusive creation keeps all originals and any previous outputs untouched.
    with A_PATH.open("xb") as handle:
        handle.write(original)
    with B_PATH.open("xb") as handle:
        handle.write(patched)
    assert A_PATH.read_bytes() == original
    assert B_PATH.read_bytes() == bytes(patched)

    report = {
        "purpose": "ColorMatrix metadata response test, not calibrated color",
        "source": str(SOURCE),
        "A": str(A_PATH),
        "B": str(B_PATH),
        "source_sha256": sha256(original).hexdigest(),
        "A_sha256": sha256(A_PATH.read_bytes()).hexdigest(),
        "B_sha256": sha256(B_PATH.read_bytes()).hexdigest(),
        "file_size_bytes": len(original),
        "A_identical_to_original": True,
        "B_changed_bytes": int(differences.sum()),
        "B_only_changes_existing_colormatrix_payloads": True,
        "all_other_bytes_identical": True,
        "raw_strips": strips,
        "raw_payload_sha256_A": pixel_a.hexdigest(),
        "raw_payload_sha256_B": pixel_b.hexdigest(),
        "matrices": matrix_report,
        "Resolve_test_performed": False,
    }
    with REPORT_PATH.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({key: report[key] for key in (
        "A", "B", "file_size_bytes", "B_changed_bytes",
        "all_other_bytes_identical", "raw_payload_sha256_A",
        "raw_payload_sha256_B", "Resolve_test_performed",
    )}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
