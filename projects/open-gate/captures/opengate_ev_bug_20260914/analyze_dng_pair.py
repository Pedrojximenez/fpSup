#!/usr/bin/env python3
"""Compare two uncompressed 12-bit SIGMA fp CinemaDNG frames.

The wider frame is mapped to the narrower frame's field of view before the
black-subtracted signal ratio is measured.  This is intended for the fp FHD /
OG3K geometry pair, where FHD is a 1.5625x resize plus a vertical crop.
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import subprocess

import numpy as np
from PIL import Image


META_FIELDS = (
    "ImageWidth",
    "ImageHeight",
    "StripOffsets",
    "StripByteCounts",
    "BlackLevel",
    "ExposureTime",
    "ISO",
    "FNumber",
    "BaselineExposure",
)


def metadata(path: pathlib.Path) -> dict:
    command = ["exiftool", "-j", "-n"]
    command.extend(f"-{field}" for field in META_FIELDS)
    command.append(str(path))
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return json.loads(result.stdout)[0]


def unpack_raw12(path: pathlib.Path, meta: dict) -> np.ndarray:
    width = int(meta["ImageWidth"])
    height = int(meta["ImageHeight"])
    offset = int(meta["StripOffsets"])
    row_bytes = width * 3 // 2
    packed = np.fromfile(
        path, dtype=np.uint8, count=row_bytes * height, offset=offset
    ).reshape(height, row_bytes)
    b0 = packed[:, 0::3].astype(np.uint16)
    b1 = packed[:, 1::3].astype(np.uint16)
    b2 = packed[:, 2::3].astype(np.uint16)
    raw = np.empty((height, width), dtype=np.uint16)
    raw[:, 0::2] = (b0 << 4) | (b1 >> 4)
    raw[:, 1::2] = ((b1 & 0x0F) << 8) | b2
    return raw


def black_scalar(meta: dict) -> float:
    value = meta["BlackLevel"]
    if isinstance(value, str):
        return float(value.split()[0])
    if isinstance(value, list):
        return float(value[0])
    return float(value)


def cfa_luma(raw: np.ndarray, black: float) -> np.ndarray:
    # Average each complete Bayer cell.  A large, matched region makes this
    # useful for exposure ratios without assuming a particular CFA ordering.
    height = raw.shape[0] & ~1
    width = raw.shape[1] & ~1
    cells = raw[:height, :width].astype(np.float32) - black
    cells = cells.reshape(height // 2, 2, width // 2, 2).mean(axis=(1, 3))
    return np.maximum(cells, 0.0)


def resize_float(image: np.ndarray, width: int, height: int) -> np.ndarray:
    pil = Image.fromarray(image.astype(np.float32), mode="F")
    return np.asarray(pil.resize((width, height), Image.Resampling.BILINEAR))


def map_wide_to_narrow(wide: np.ndarray, narrow_shape: tuple[int, int]) -> np.ndarray:
    narrow_h, narrow_w = narrow_shape
    scale = wide.shape[1] / narrow_w
    source_h = narrow_h * scale
    y0 = (wide.shape[0] - source_h) / 2.0
    y1 = y0 + source_h
    lo = max(0, int(math.floor(y0)))
    hi = min(wide.shape[0], int(math.ceil(y1)))
    cropped = wide[lo:hi]
    return resize_float(cropped, narrow_w, narrow_h)


def best_shift(reference: np.ndarray, candidate: np.ndarray, radius: int = 12):
    # Search on a 4x reduced image so small framing changes do not masquerade
    # as exposure differences.
    ref = reference[::4, ::4]
    cand = candidate[::4, ::4]
    margin = radius + 8
    best = (-np.inf, 0, 0)
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            a = ref[margin:-margin, margin:-margin]
            b = cand[
                margin + dy : cand.shape[0] - margin + dy,
                margin + dx : cand.shape[1] - margin + dx,
            ]
            if a.shape != b.shape or not a.size:
                continue
            av = a - np.mean(a)
            bv = b - np.mean(b)
            denom = float(np.sqrt(np.sum(av * av) * np.sum(bv * bv)))
            corr = float(np.sum(av * bv) / denom) if denom else -np.inf
            if corr > best[0]:
                best = (corr, dx * 4, dy * 4)
    return best


def overlap_shift(a: np.ndarray, b: np.ndarray, dx: int, dy: int):
    x0 = max(0, dx)
    x1 = min(a.shape[1], b.shape[1] + dx)
    y0 = max(0, dy)
    y1 = min(a.shape[0], b.shape[0] + dy)
    return a[y0:y1, x0:x1], b[y0 - dy : y1 - dy, x0 - dx : x1 - dx]


def save_preview(path: pathlib.Path, image: np.ndarray, lo: float, hi: float):
    normalized = np.clip((image - lo) / max(hi - lo, 1e-6), 0, 1)
    encoded = np.round(np.sqrt(normalized) * 255).astype(np.uint8)
    Image.fromarray(encoded, mode="L").save(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("narrow", type=pathlib.Path)
    parser.add_argument("wide", type=pathlib.Path)
    parser.add_argument("--out", type=pathlib.Path, required=True)
    args = parser.parse_args()

    narrow_meta = metadata(args.narrow)
    wide_meta = metadata(args.wide)
    narrow = cfa_luma(unpack_raw12(args.narrow, narrow_meta), black_scalar(narrow_meta))
    wide = cfa_luma(unpack_raw12(args.wide, wide_meta), black_scalar(wide_meta))
    mapped = map_wide_to_narrow(wide, narrow.shape)
    corr, dx, dy = best_shift(narrow, mapped)
    n, w = overlap_shift(narrow, mapped, dx, dy)

    # Exclude borders, deep noise-floor values, and near-clipped highlights.
    border_y = max(8, n.shape[0] // 10)
    border_x = max(8, n.shape[1] // 10)
    n = n[border_y:-border_y, border_x:-border_x]
    w = w[border_y:-border_y, border_x:-border_x]
    mask = (n > 12) & (w > 12) & (n < 3500) & (w < 3500)
    ratios = w[mask] / n[mask]
    log_ratios = np.log2(ratios)

    # Also report distribution ratios; disagreement flags scene movement or an
    # invalid geometry assumption instead of silently presenting a false EV.
    n_values = n[mask]
    w_values = w[mask]
    median_ratio = float(np.median(ratios))
    distribution_ratio = float(np.median(w_values) / np.median(n_values))
    mean_ratio = float(np.mean(w_values) / np.mean(n_values))

    args.out.mkdir(parents=True, exist_ok=True)
    preview_lo = float(min(np.percentile(narrow, 1), np.percentile(mapped, 1)))
    preview_hi = float(max(np.percentile(narrow, 99.7), np.percentile(mapped, 99.7)))
    save_preview(args.out / "narrow.png", narrow, preview_lo, preview_hi)
    save_preview(args.out / "wide_mapped.png", mapped, preview_lo, preview_hi)

    result = {
        "narrow": {field: narrow_meta.get(field) for field in META_FIELDS},
        "wide": {field: wide_meta.get(field) for field in META_FIELDS},
        "mapping": {
            "correlation": corr,
            "shift_cfa_cells": [dx, dy],
            "sample_count": int(mask.sum()),
        },
        "wide_over_narrow": {
            "median_pixel_ratio": median_ratio,
            "median_pixel_ev": math.log2(median_ratio),
            "median_distribution_ratio": distribution_ratio,
            "median_distribution_ev": math.log2(distribution_ratio),
            "mean_distribution_ratio": mean_ratio,
            "mean_distribution_ev": math.log2(mean_ratio),
            "log2_ratio_p10_p50_p90": [
                float(x) for x in np.percentile(log_ratios, (10, 50, 90))
            ],
        },
    }
    output = json.dumps(result, indent=2, ensure_ascii=False)
    (args.out / "result.json").write_text(output + "\n")
    print(output)


if __name__ == "__main__":
    main()
