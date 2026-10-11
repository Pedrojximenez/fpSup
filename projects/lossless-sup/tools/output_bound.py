#!/usr/bin/env python3
"""Conservative worst-case output bound for the FHD lossless-JPEG arena.

Lossless JPEG cannot be assumed to shrink. Each sample costs a Huffman-coded
magnitude category plus that many extra bits, so an adversarial or simply noisy
frame EXPANDS. The scratch arena must therefore be sized from a bound, not from
the packed raster size, and the size tables must live above that bound.

The bound uses optimal-Huffman semantics (average code length <= entropy + 1),
maximised numerically over category distributions. If the camera's encoder uses
a fixed rather than per-image table its average can exceed the optimal one, so
this is a bound for the modelled contract, not a proof about the hardware.

Offline only: no camera, no card, no deployment.
"""
import argparse
import json
import math

SAMPLE_BITS = 12
MAX_CATEGORY = 12          # floor(log2(4095)) + 1 for 12-bit samples
TILE_MARKER_BYTES = 96     # per-tile marker overhead in the host cost model

# The integer bits/sample the bound is actually computed with. The numerical
# search below maximises a real-valued expression and returns 13.999823...;
# 14 is the smallest integer above it, and using the integer removes every
# rounding decision from the arithmetic. It matters which way those decisions
# went: the probe used to inline the search's value rounded DOWN to 13.9998
# and then TRUNCATE the product, so its "bound" came out 7 bytes BELOW this
# module's, and a bound below the true worst case is not a bound. With
# BOUND_BITS the formula is exact integer arithmetic and the two agree by
# construction rather than by matching two roundings.
BOUND_BITS = 14


def max_bits_per_sample(max_category=MAX_CATEGORY, steps=2000):
    """max over category distributions of E[SSSS] + H(p) + 1."""
    best = 0.0
    for ratio_step in range(1, steps + 1):
        a = ratio_step / steps
        weights = [a ** (max_category - i) for i in range(max_category + 1)]
        total = sum(weights)
        p = [w / total for w in weights]
        expected = sum(i * pi for i, pi in enumerate(p))
        entropy = -sum(pi * math.log2(pi) for pi in p if pi > 0)
        best = max(best, expected + entropy + 1.0)
    return best


def exact_bound_bytes(padded_samples, tiles):
    """THE bound, as one integer formula. Every caller uses this one.

    padded_samples * 14 is a whole number of bits and, for every tile
    geometry used here, a whole number of bytes, so there is no rounding to
    get wrong. The ceiling is kept for geometries where it would not divide.
    """
    return -(-padded_samples * BOUND_BITS // 8) + tiles * TILE_MARKER_BYTES


def geometry(width, height, tile_w, tile_h):
    cols = -(-width // tile_w)
    rows = -(-height // tile_h)
    return {"tiles": cols * rows, "cols": cols, "rows": rows,
            "padded_width": cols * tile_w, "padded_height": rows * tile_h,
            "padded_samples": cols * tile_w * rows * tile_h,
            "active_samples": width * height}


def bound(width, height, tile_w, tile_h, bits_per_sample=None):
    geo = geometry(width, height, tile_w, tile_h)
    bits = BOUND_BITS if bits_per_sample is None else bits_per_sample
    # Padding samples are forced to diff 0 by the engine's edge behaviour, but
    # they are bounded at full cost here: the padding contract is decoded, not
    # proven, and a bound must not rest on the cheaper reading.
    if bits_per_sample is None:
        total = exact_bound_bytes(geo["padded_samples"], geo["tiles"])
        payload = total - geo["tiles"] * TILE_MARKER_BYTES
    else:
        payload = -(-int(math.ceil(geo["padded_samples"] * bits)) // 8)
        total = payload + geo["tiles"] * TILE_MARKER_BYTES
    geo.update({"bits_per_sample": bits,
                "payload_bytes": payload,
                "marker_bytes": geo["tiles"] * TILE_MARKER_BYTES,
                "bound_bytes": total,
                "packed_raster_bytes": width * height * SAMPLE_BITS // 8})
    geo["expansion_vs_raster"] = round(total / geo["packed_raster_bytes"], 4)
    return geo


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--width", type=int, default=1936)
    parser.add_argument("--height", type=int, default=1090)
    parser.add_argument("--tile", default="512x368",
                        help="one or more WxH, comma separated")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    results = {}
    for spec in args.tile.split(","):
        tw, th = (int(part) for part in spec.lower().split("x"))
        results[spec] = bound(args.width, args.height, tw, th)
    if args.json:
        print(json.dumps(results, indent=2))
        return 0
    for spec, r in results.items():
        print(f"tile {spec}: {r['cols']}x{r['rows']} = {r['tiles']} tiles, "
              f"padded {r['padded_width']}x{r['padded_height']}")
        print(f"  bits/sample bound   {r['bits_per_sample']}")
        print(f"  packed raster       {r['packed_raster_bytes']:,} B")
        print(f"  WORST-CASE OUTPUT   {r['bound_bytes']:,} B "
              f"({r['expansion_vs_raster']}x the raster)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
