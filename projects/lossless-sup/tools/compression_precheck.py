#!/usr/bin/env python3
"""Predict, from a small sample, whether a frame will compress.

Why this exists, precisely: copy-back decides AFTER the encode, from the size
table, so a wrong guess costs nothing. Zero-copy - letting the codec write over
the source in place - has no such moment: by the time the size is known the
source is gone. A predictor cannot make that safe, because a false "it will
compress" destroys the frame unrecoverably.

What a predictor CAN do is choose between two paths that are both correct:

    predicted to compress well  ->  zero-copy      (fast, unrecoverable)
    anything else               ->  copy-back      (slower, has a fallback)

So the two errors are not symmetric and must never be treated as if they were:

    false negative  ->  one unnecessary copy.            Harmless.
    false positive  ->  one destroyed frame.             Unacceptable.

Everything here is therefore reported as a margin against the ACTUAL size, and
the only number that matters is the worst false positive over the calibration
set. A threshold is not proposed here: §1 of COMPRESSION_PRECHECK says one
score and one threshold, and the threshold comes from calibration, not from
this file.

The sampling follows that note: the difference is against the pixel two columns
left, not one, because adjacent columns are different CFA components and would
give a different distribution entirely.

Offline only. Reads arrays, writes nothing, touches no camera.
"""
import argparse
import heapq
import json
import math
from pathlib import Path
import sys

sys.dont_write_bytecode = True

SAMPLE_BITS = 12
MAX_CATEGORY = 12          # floor(log2(4095)) + 1
TILE_MARKER_BYTES = 96     # per tile, the same figure output_bound.py uses
WINDOWS_PER_TILE = 4
ROWS_PER_WINDOW = 2
SAMPLES_PER_ROW = 128


def category(d):
    """The JPEG magnitude category of a difference: 0 for zero, else the
    number of bits needed for its magnitude."""
    return 0 if d == 0 else int(abs(d)).bit_length()


def huffman_lengths(counts):
    """Canonical code lengths for these 13 symbols, from the counts themselves.

    Deriving them beats a magic table: it is what a per-image encoder does, it
    needs no calibration of its own, and a symbol that never occurs costs
    nothing. A single used symbol still costs one bit, which is what a real
    encoder emits.
    """
    present = [(c, i) for i, c in enumerate(counts) if c > 0]
    if not present:
        return [0] * len(counts)
    if len(present) == 1:
        lengths = [0] * len(counts)
        lengths[present[0][1]] = 1
        return lengths
    heap = [(c, 0, {i}) for c, i in present]
    heapq.heapify(heap)
    depth = {i: 0 for _, i in present}
    while len(heap) > 1:
        c1, _, s1 = heapq.heappop(heap)
        c2, _, s2 = heapq.heappop(heap)
        for i in s1 | s2:
            depth[i] += 1
        heapq.heappush(heap, (c1 + c2, min(min(s1), min(s2)), s1 | s2))
    return [depth.get(i, 0) for i in range(len(counts))]


def bits_per_sample(counts):
    """Expected bits per sample for this histogram: the Huffman code for the
    category, plus the category's own magnitude bits."""
    total = sum(counts)
    if total == 0:
        return 0.0
    lengths = huffman_lengths(counts)
    return sum(c / total * (lengths[k] + k) for k, c in enumerate(counts) if c)


# The golden ratio conjugate. Adding it repeatedly and taking the fraction
# walks the interval without ever repeating a position, which is what a
# rotation has to do to be worth having.
GOLDEN = 0.6180339887498949


def window_origins(tile_w, tile_h, seq=0):
    """Four spread positions inside a tile, genuinely shifted by the frame
    number.

    The first version computed fy from ((i + seq) % 4), which as i runs 0..3
    covers the same four positions for EVERY seq: the rotation was a no-op and
    the sampler read identical rows on every frame. An adversarial frame found
    it - noise everywhere except those rows scored a perfect 1.000 bits per
    sample on all six seq values tried. The offset now moves the set.
    """
    out = []
    shift = (seq * GOLDEN) % 1.0
    for i in range(WINDOWS_PER_TILE):
        fx = ((i * 2 + 1) / (WINDOWS_PER_TILE * 2) + shift) % 1.0
        fy = ((i * 2 + 1) / (WINDOWS_PER_TILE * 2) + shift * GOLDEN) % 1.0
        x = int(fx * (tile_w - SAMPLES_PER_ROW - 2)) + 2
        y = int(fy * (tile_h - ROWS_PER_WINDOW))
        out.append((x, y))
    return out


def sample(pixels, tile_w=512, tile_h=368, seq=0):
    """One 13-bin histogram per CFA column component, over a few small windows
    in every tile. `pixels` is the padded image, so every window is inside it.
    """
    height, width = pixels.shape
    cols, rows = width // tile_w, height // tile_h
    counts = [[0] * (MAX_CATEGORY + 1), [0] * (MAX_CATEGORY + 1)]
    taken = 0
    for ty in range(rows):
        for tx in range(cols):
            for wx, wy in window_origins(tile_w, tile_h, seq):
                x0, y0 = tx * tile_w + wx, ty * tile_h + wy
                for dy in range(ROWS_PER_WINDOW):
                    row = pixels[y0 + dy]
                    for dx in range(SAMPLES_PER_ROW):
                        x = x0 + dx
                        d = int(row[x]) - int(row[x - 2])
                        counts[x & 1][category(d)] += 1
                        taken += 1
    return counts, taken


def predict(pixels, tile_w=512, tile_h=368, seq=0):
    """Estimated compressed payload bytes, and the score behind it."""
    height, width = pixels.shape
    cols, rows = width // tile_w, height // tile_h
    tiles = cols * rows
    counts, taken = sample(pixels, tile_w, tile_h, seq)
    merged = [a + b for a, b in zip(*counts)]
    per_component = [bits_per_sample(c) for c in counts]
    bits = sum(per_component) / 2
    samples = width * height
    payload = math.ceil(samples * bits / 8)
    return {
        "score_bits_per_sample": round(bits, 4),
        "score_per_component": [round(b, 4) for b in per_component],
        "mean_category": round(sum(k * c for k, c in enumerate(merged)) / max(sum(merged), 1), 4),
        "fraction_zero": round(merged[0] / max(sum(merged), 1), 4),
        "fraction_ge_10": round(sum(merged[10:]) / max(sum(merged), 1), 4),
        "samples_taken": taken,
        "sample_fraction": round(taken / samples, 5),
        "padded_samples": samples,
        "tiles": tiles,
        "predicted_payload_bytes": payload,
        "predicted_file_bytes": payload + tiles * TILE_MARKER_BYTES,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dng", type=Path, nargs="+")
    parser.add_argument("--tile", default="512x368")
    parser.add_argument("--seq", type=int, default=0)
    args = parser.parse_args()
    tw, th = (int(p) for p in args.tile.lower().split("x"))
    sys.path.insert(0, "/Users/dido/Developer.localized/SIGMAfp_re/research/slimRAW")
    import rawpy
    import tilegeom
    out = []
    for path in args.dng:
        with rawpy.imread(str(path)) as raw:
            pixels = raw.raw_image_visible.copy()
        padded, _, _ = tilegeom.pad_image(pixels, tw, th)
        result = predict(padded, tw, th, args.seq)
        result["path"] = str(path)
        out.append(result)
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
