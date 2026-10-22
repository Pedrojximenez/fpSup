#!/usr/bin/env python3
"""Measure the predictor against ACTUAL compressed sizes.

The host encoder is the ground truth generator, and it earned that on
2026-09-26: against the camera's own twelve tile sizes for A001_090 frame 1 it
matched nine exactly, three within three bytes, and the twelfth differed only by
the 457 zero bytes the camera pads onto the last tile. So a stock frame plus
this encoder is a calibration point, and no camera session is needed to make
more of them.

What is reported is the SIGNED error, because the two directions are not
equivalent. Under-estimating is the dangerous one: it is what would wrongly
send a frame down the zero-copy path, where being wrong destroys it. The number
that decides whether a threshold can exist at all is the worst under-estimate
over the set, and it is printed on its own line.

Offline only.
"""
import argparse
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
SLIMRAW = "/Users/dido/Developer.localized/SIGMAfp_re/research/slimRAW"
sys.path.insert(0, SLIMRAW)

import compression_precheck as precheck


def actual_payload(padded, tile_w, tile_h):
    import ljenc
    total = 0
    for y in range(0, padded.shape[0], tile_h):
        for x in range(0, padded.shape[1], tile_w):
            total += len(ljenc.encode_tile(padded[y:y + tile_h, x:x + tile_w], 12, 1))
    return total


def synthetic(kind, shape, rng):
    import numpy as np
    h, w = shape
    if kind == "flat":
        return np.full(shape, 512, dtype=np.uint16)
    if kind == "uniform-noise":
        return rng.integers(0, 4096, size=shape, dtype=np.uint16)
    if kind == "alternating-extremes":
        a = np.zeros(shape, dtype=np.uint16)
        a[:, 0::2] = 4095
        return a
    if kind == "gradient":
        return (np.arange(w, dtype=np.uint16)[None, :] % 4096).repeat(h, 0)
    if kind == "flat-with-noisy-patch":
        # Most of the frame is trivial; one block is the worst case. A sparse
        # sampler can miss the block entirely.
        a = np.full(shape, 512, dtype=np.uint16)
        a[h // 3:h // 3 + 400, w // 3:w // 3 + 400] = rng.integers(
            0, 4096, size=(400, 400), dtype=np.uint16)
        return a
    if kind == "noise-off-the-sampled-rows":
        # THE adversarial case. The sampler reads fixed rows, so put the noise
        # everywhere it does NOT read and leave those rows flat. If the score
        # comes back low, the predictor is blind in exactly the way that would
        # send an expanding frame down the zero-copy path.
        a = rng.integers(0, 4096, size=shape, dtype=np.uint16)
        for row in sampled_rows(shape, 512, 368):
            a[row, :] = 512
        return a
    if kind == "noise-only-on-the-sampled-rows":
        # The mirror image: it should make the predictor OVER-estimate, which
        # is the harmless direction, and confirms the sampler reads what it
        # thinks it reads.
        a = np.full(shape, 512, dtype=np.uint16)
        for row in sampled_rows(shape, 512, 368):
            a[row, :] = rng.integers(0, 4096, size=shape[1], dtype=np.uint16)
        return a
    raise ValueError(kind)


def sampled_rows(shape, tile_w, tile_h, seq=0):
    """Every image row the sampler actually reads, from the sampler's own
    window positions rather than a second copy of the arithmetic."""
    import tilegeom
    import numpy as np
    padded, _, _ = tilegeom.pad_image(np.zeros(shape, dtype=np.uint16), tile_w, tile_h)
    height, width = padded.shape
    rows = set()
    for ty in range(height // tile_h):
        for _wx, wy in precheck.window_origins(tile_w, tile_h, seq):
            for dy in range(precheck.ROWS_PER_WINDOW):
                r = ty * tile_h + wy + dy
                if r < shape[0]:
                    rows.add(r)
    return sorted(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dng", type=Path, nargs="*")
    parser.add_argument("--tile", default="512x368")
    parser.add_argument("--synthetic", action="store_true",
                        help="also run the adversarial shapes")
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    tw, th = (int(p) for p in args.tile.lower().split("x"))

    import numpy as np
    import rawpy
    import tilegeom
    rng = np.random.default_rng(20260926)

    cases = []
    for path in args.dng:
        with rawpy.imread(str(path)) as raw:
            cases.append((path.name, raw.raw_image_visible.copy()))
    if args.synthetic:
        shape = cases[0][1].shape if cases else (1090, 1936)
        for kind in ("flat", "gradient", "alternating-extremes", "uniform-noise",
                     "flat-with-noisy-patch", "noise-only-on-the-sampled-rows",
                     "noise-off-the-sampled-rows"):
            cases.append((kind, synthetic(kind, shape, rng)))

    rows = []
    for name, pixels in cases:
        padded, _, _ = tilegeom.pad_image(pixels, tw, th)
        got = precheck.predict(padded, tw, th)
        real = actual_payload(padded, tw, th)
        # predicted_file_bytes, not predicted_payload_bytes: the actual figure
        # includes each tile's own JPEG header, and the payload estimate is
        # entropy-coded bytes only. Comparing the two was my error and it
        # manufactured a systematic under-estimate of about 12 x 81 bytes.
        error = got["predicted_file_bytes"] - real
        rows.append({"case": name, "actual": real,
                     "predicted": got["predicted_file_bytes"],
                     "error": error,
                     "error_percent": round(100 * error / real, 2),
                     "score": got["score_bits_per_sample"],
                     "mean_category": got["mean_category"],
                     "fraction_zero": got["fraction_zero"],
                     "fraction_ge_10": got["fraction_ge_10"]})

    print(f"{'case':26s} {'actual':>10s} {'predicted':>10s} {'error':>9s} {'err%':>7s} "
          f"{'score':>7s} {'meanK':>6s} {'P(0)':>6s} {'P(>=10)':>8s}")
    for r in rows:
        print(f"{r['case']:26s} {r['actual']:10d} {r['predicted']:10d} {r['error']:+9d} "
              f"{r['error_percent']:+7.2f} {r['score']:7.3f} {r['mean_category']:6.3f} "
              f"{r['fraction_zero']:6.3f} {r['fraction_ge_10']:8.3f}")
    under = [r for r in rows if r["error"] < 0]
    print()
    print(f"cases                : {len(rows)}")
    print(f"UNDER-estimates      : {len(under)}  <- the dangerous direction")
    if under:
        worst = min(under, key=lambda r: r["error_percent"])
        print(f"worst under-estimate : {worst['error_percent']:+.2f}%  ({worst['case']})")
    else:
        print("worst under-estimate : none in this set")
    print("NOTE: a set this small is not a calibration. It is a first look, and "
          "no threshold follows from it.")
    if args.json:
        args.json.write_text(json.dumps(rows, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
