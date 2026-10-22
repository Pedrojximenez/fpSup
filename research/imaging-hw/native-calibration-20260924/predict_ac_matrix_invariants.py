#!/usr/bin/env python3
"""Read-only A/C DNG math audit; outputs JSON, never touches images or DNGs.

The Bradford-neutral model is an illustrative hypothesis, not Resolve emulation.
No temperature or interpolation parameter is inferred from rendered images here.
"""

from pathlib import Path
import json
import numpy as np


ROOT = Path(__file__).resolve().parent
INPUT = ROOT.parent / "fp-colormatrix-ab-20260923/candidate-verification.json"
N = np.array([0.5130260521, 1.0, 0.583143508])
BRADFORD = np.array([[0.8951, 0.2664, -0.1614],
                     [-0.7502, 1.7135, 0.0367],
                     [0.0389, -0.0685, 1.0296]])
TARGET_WHITE = np.array([0.96422, 1.0, 0.82521])


def interpolated(report, name, weight):
    pairs = report["matrices"]
    return ((1.0 - weight) * np.array(pairs["50721"][name])
            + weight * np.array(pairs["50722"][name]))


def invariants(matrix):
    return {
        "matrix_column_vector_XYZ_basis": matrix.tolist(),
        "eigenvalues_real_imag": [[float(v.real), float(v.imag)]
                                 for v in np.linalg.eigvals(matrix)],
        "determinant": float(np.linalg.det(matrix)),
        "trace": float(np.trace(matrix)),
    }


def neutral_normalized_map(matrix):
    inv = np.linalg.inv(matrix)
    source_white = inv @ N
    cat = np.linalg.solve(
        BRADFORD,
        np.diag((BRADFORD @ TARGET_WHITE) / (BRADFORD @ source_white))
        @ BRADFORD,
    )
    return cat @ inv, source_white


def main():
    report = json.loads(INPUT.read_text())
    result = {
        "input": str(INPUT),
        "image_analysis_performed": False,
        "note": "Conditional linear predictions only; no absolute accuracy conclusion.",
        "unchanged_AsShotNeutral": N.tolist(),
        "weight_definition": "CM2 fraction; 0=CM1/illuminant17, 1=CM2/illuminant21",
        "samples": [],
    }
    for weight in [0, 0.25, 0.5, 0.75, 1]:
        a = interpolated(report, "A", weight)
        c = interpolated(report, "C", weight)
        ar = interpolated(report, "OFF_ROM_matrix", weight)
        cr = interpolated(report, "normal_ROM_matrix", weight)
        direct = np.linalg.solve(c, a)
        direct_rom = np.linalg.solve(cr, ar)
        da, wa = neutral_normalized_map(a)
        dc, wc = neutral_normalized_map(c)
        adapted = dc @ np.linalg.inv(da)
        sample = {
            "CM2_weight_for_both_profiles": weight,
            "bare_CM_inverse_ratio": invariants(direct),
            "bare_ROM_inverse_ratio": invariants(direct_rom),
            "max_abs_difference_from_quantization": float(
                np.max(np.abs(direct - direct_rom))),
            "illustrative_Bradford_neutral_normalized_ratio": invariants(adapted),
            "A_source_white_xy": (wa[:2] / wa.sum()).tolist(),
            "C_source_white_xy": (wc[:2] / wc.sum()).tolist(),
            "white_invariant_max_abs_error": float(
                np.max(np.abs(adapted @ TARGET_WHITE - TARGET_WHITE))),
        }
        assert sample["white_invariant_max_abs_error"] < 1e-12
        result["samples"].append(sample)
    # Body scaling cancels algebraically before quantization, including when
    # A and C use different CM2 interpolation fractions.
    body = np.array(report["Sigma_private_CameraCalibration"])
    residuals = []
    for ta, tc in [(0.2, 0.7), (0.8, 0.4)]:
        ar = interpolated(report, "OFF_ROM_matrix", ta)
        cr = interpolated(report, "normal_ROM_matrix", tc)
        a = np.linalg.solve(body, ar)
        c = np.linalg.solve(body, cr)
        residuals.append(float(np.max(np.abs(
            np.linalg.solve(c, a) - np.linalg.solve(cr, ar)))))
    result["body_cancellation_numerical_residuals"] = residuals
    assert max(residuals) < 1e-12
    output = ROOT / "ac-matrix-invariants.json"
    with output.open("x") as handle:
        json.dump(result, handle, indent=2)
        handle.write("\n")
    print(output)
    for sample in result["samples"]:
        print(sample["CM2_weight_for_both_profiles"],
              sample["illustrative_Bradford_neutral_normalized_ratio"]["eigenvalues_real_imag"],
              sample["max_abs_difference_from_quantization"])


if __name__ == "__main__":
    main()
