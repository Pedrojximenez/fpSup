#!/usr/bin/env python3
"""What counts as touching the engine's declared output length - decided here,
before any run, so that a result cannot be read as a pass after the fact.

The probe hands the codec a destination and puts guard words at the declared
length. Five unchanged guards are then easy to over-read: they are equally
consistent with "the engine stopped where it was told" and with "the output
was nowhere near the limit, so nothing was ever tested". The difference is
whether the INPUT demanded more than the limit, and that is a host question -
answered by encoding the probe's own generated pattern with the project's
lossless-JPEG encoder and seeing what it costs.

So a bound PASS needs two independent things:

  * demand: the same bytes the camera generates, encoded here, need MORE than
    the declared length. Without this the run says nothing about the bound.
  * behaviour: the codec accepted the work, reported sizes that add up, and
    produced an output that actually reached the limit, with the guards intact.

And these are explicitly NOT a pass, each of which would otherwise look like
one: a refused init, encode or size call; a size table that does not sum to the
reported total, or has a zero in it; an output far below the declared length;
five unchanged guards on their own.

Offline only: no camera, no card. Nothing here decides whether to run anything
on a camera; it decides what a run would have to show.
"""
import argparse
import hashlib
import json
import pathlib
import sys

# The probe's own constants, named here so a change on one side shows up as a
# mismatch rather than as a silently different criterion.
LCG_SEED = 0x12345679
LCG_MUL = 1664525
LCG_ADD = 1013904223
SOURCE_BYTES = 0x304CB0            # PROBE_BYTES, what the engine reads
DECLARED = 0x305000                # PROBE_DECLARED = round_up(source, 1024)
WIDTH, HEIGHT = 1936, 1090
TILE_W, TILE_H = 512, 368
SAMPLE_BITS = 12
PREDICTOR = 1

# How far below the declared length an output may land and still be said to
# have reached it. The engine emits whole tiles, and the last one cannot be
# split, so an output that stops at the limit will fall short by up to one
# tile's worth. Anything further below means it finished early, on its own.
REACH_TOLERANCE = 1.0 / 12         # one tile of twelve


class Undecidable(Exception):
    """The evidence does not support any verdict, which is itself the result."""


def generate_source(n_bytes=SOURCE_BYTES, seed=LCG_SEED):
    """Byte for byte what the probe's fill loop writes.

    The ARM is three instructions: x = x * 1664525 + 1013904223; word =
    x ^ (x >> 16); store. Stored little-endian, four bytes at a time, which is
    why the words are packed with "<I" here rather than being treated as
    samples: the engine reads BYTES and unpacks them as 12-bit samples itself.
    """
    if n_bytes % 4:
        raise ValueError("the fill loop writes whole words")
    import struct
    out = bytearray()
    x = seed
    for _ in range(n_bytes // 4):
        x = (x * LCG_MUL + LCG_ADD) & 0xFFFFFFFF
        out += struct.pack("<I", x ^ (x >> 16))
    return bytes(out)


def generate_ramp(n_bytes=SOURCE_BYTES):
    """The PROBE_RAMP fill, byte for byte.

    The ARM is one register plus a constant addend: start at 0x03020100, add
    0x04040404 per word, store. That is a byte ramp 0,1,2,... wrapping at 256,
    and the bytes wrap on their own without masking.
    """
    if n_bytes % 4:
        raise ValueError("the fill loop writes whole words")
    import struct
    out = bytearray()
    word = 0x03020100
    for _ in range(n_bytes // 4):
        out += struct.pack("<I", word)
        word = (word + 0x04040404) & 0xFFFFFFFF
    return bytes(out)


def generate_flat(n_bytes=SOURCE_BYTES):
    """The PROBE_RAMP fill as it ended up: samples alternating 1024 and 3072.

    The first attempt was a ramp in BYTE space, and the host encoder measured it
    at 12.15 bits a sample - still over the declared length, so it would not
    have separated anything. The reason is that the engine sees 12-bit SAMPLES,
    three bytes carrying two of them, and a byte ramp that wraps every 256
    bytes keeps shifting phase against that packing, which produces large
    differences rather than small ones. Designed in sample space instead: each
    component sees one constant, so predictor 1 leaves differences of zero.
    Measured here at 1.0 bits a sample, 8.4% of the declared length.

    Three bytes carry the pair, and 12 bytes is the first whole number of words
    that holds a whole number of pairs, so the fill is three constants in a
    loop - which is what the ARM does.
    """
    if n_bytes % 12:
        raise ValueError("the fill loop writes whole 12-byte groups")
    pattern = bytes([0x40, 0x0C, 0x00])          # samples 1024, 3072
    return (pattern * (n_bytes // 3))[:n_bytes]


# Which host-side generator reproduces which camera-side variant. The copy
# variant's source is the camera's own frame, which the host cannot reproduce -
# recorded as such rather than hashed against a pattern it is not.
SOURCE_GENERATORS = {
    "bound-probe-two": generate_source,
    "bound-probe": generate_source,
    "bound-probe-two-ramp": generate_flat,
    "bound-probe-two-copy": None,
    "bound-probe-frame": None,
}


def unpack12(data, width=WIDTH, height=HEIGHT):
    """The project's own 12-bit unpacking, as ljcost.load_uncompressed does it:
    three bytes carry two samples, high sample first."""
    import numpy as np
    need = width * height * 3 // 2
    if len(data) < need:
        raise ValueError(f"{len(data)} bytes is short of {need}")
    raw = np.frombuffer(data[:need], dtype=np.uint8).reshape(-1, 3).astype(np.uint16)
    hi = (raw[:, 0] << 4) | (raw[:, 1] >> 4)
    lo = ((raw[:, 1] & 0xF) << 8) | raw[:, 2]
    px = np.empty(width * height, dtype=np.uint16)
    px[0::2] = hi
    px[1::2] = lo
    return px.reshape(height, width)


def load_encoder(encoder_dir=None):
    """The project's lossless-JPEG encoder, from research/slimRAW.

    Imported rather than reimplemented: a second encoder written to confirm the
    first would agree with my own misunderstanding of the format, and this one
    has a decoder next to it that the round-trip test uses.
    """
    if encoder_dir is None:
        encoder_dir = (pathlib.Path(__file__).resolve().parents[3]
                       / "research" / "slimRAW")
    encoder_dir = pathlib.Path(encoder_dir)
    if str(encoder_dir) not in sys.path:
        sys.path.insert(0, str(encoder_dir))
    import ljcost
    import ljenc
    import ljpeg
    return ljenc, ljcost, ljpeg


def tile_grid(width=WIDTH, height=HEIGHT, tile_w=TILE_W, tile_h=TILE_H):
    """Every tile, CLIPPED to the active area, in raster order.

    1936x1090 over 512x368 tiles is twelve tiles of which only six are whole:
    the right column is 400 wide and the bottom row 354 tall. Counting only the
    whole ones covers 53.6% of the frame and understates the cost by about
    half, which is how a first version of this refused a pattern that plainly
    does demand more than the limit.

    Clipping instead gives a LOWER BOUND on the demand, and that is the useful
    direction: the engine pads the partial tiles to full size and pays
    something for every padded sample, whatever the padding rule turns out to
    be, so its output cannot be smaller than the clipped encoding. A demand
    established this way does not rest on a padding contract that is decoded
    rather than proven.
    """
    boxes, whole = [], 0
    for y in range(0, height, tile_h):
        for x in range(0, width, tile_w):
            box = (x, y, min(x + tile_w, width), min(y + tile_h, height))
            boxes.append(box)
            if box[2] - box[0] == tile_w and box[3] - box[1] == tile_h:
                whole += 1
    return boxes, whole


def host_demand(*, encoder_dir=None, exact=True, source=None):
    """What this pattern costs, encoded here.

    `exact` runs the real encoder and measures the bitstreams it produces.
    Without it the cost model in ljcost is used instead, which is faster and
    is what the earlier sizing work used; the two are reported together so a
    disagreement is visible rather than averaged.
    """
    ljenc, ljcost, _ = load_encoder(encoder_dir)
    data = generate_source() if source is None else source
    image = unpack12(data)
    boxes, whole = tile_grid()
    tiles, modelled = [], []
    for x0, y0, x1, y1 in boxes:
        tile = image[y0:y1, x0:x1]
        modelled.append(ljcost.tile_cost(tile, SAMPLE_BITS, PREDICTOR))
        if exact:
            tiles.append(len(ljenc.encode_tile(tile, SAMPLE_BITS, PREDICTOR)))
    measured = sum(tiles) if exact else None
    counted = sum((y1 - y0) * (x1 - x0) for x0, y0, x1, y1 in boxes)
    total = measured if exact else sum(modelled)
    padded = TILE_W * TILE_H * len(boxes)
    return {
        "source_bytes": len(data),
        "source_sha256": hashlib.sha256(data).hexdigest(),
        "tiles": len(boxes),
        "whole_tiles": whole,
        "partial_tiles": len(boxes) - whole,
        "samples_counted": counted,
        "samples_if_padded": padded,
        "tile_bytes": tiles,
        "encoded_bytes": measured,
        "modelled_bytes": sum(modelled),
        "modelled_tile_bytes": modelled,
        "declared_length": DECLARED,
        # A lower bound: the partial tiles are encoded clipped, and the engine
        # pays something for the padding it adds to them.
        "demand_exceeds_declared": total > DECLARED,
        "demand_margin_bytes": total - DECLARED,
        "bits_per_sample": round(8.0 * total / counted, 4),
        "padded_at_this_rate": int(padded * 8.0 * total / counted / 8),
    }


def verdict(measurement, demand, *, declared=DECLARED, guard_magic=0xA55AA55A):
    """The verdict, and the reasons for it. Never a bare boolean.

    `measurement` is what the probe left behind: the three return codes, the
    error word, the tile sizes, the reported total and the five guard words.
    `demand` is what host_demand returned for the same pattern.
    """
    refusals = []
    for name in ("init_ret", "enc_ret", "size_ret", "error", "tile_sizes",
                 "compressed_size", "guards", "variant", "source_sha256",
                 "image_sha256"):
        if name not in measurement:
            refusals.append(f"the record has no {name}")
    if refusals:
        raise Undecidable("; ".join(refusals))

    guards = list(measurement["guards"])
    intact = [g == guard_magic for g in guards]
    total = measurement["compressed_size"]

    if measurement["error"]:
        refusals.append(f"the probe reported error {measurement['error']}")
    for call in ("init_ret", "enc_ret", "size_ret"):
        if measurement[call] != 1:
            refusals.append(f"{call} was {measurement[call]}, not 1")
    if len(guards) != 5:
        refusals.append(f"{len(guards)} guard words, not 5")
    if not demand.get("demand_exceeds_declared"):
        refusals.append(
            "the host encoder does not need more than the declared length for "
            "this pattern, so the run did not put the limit under any pressure")
    if measurement["source_sha256"] != demand["source_sha256"]:
        refusals.append("the pattern the host encoded is not the pattern the "
                        "camera generated")
    sizes = list(measurement["tile_sizes"])
    if any(size <= 0 for size in sizes):
        refusals.append("a tile size is zero or negative")
    if sum(sizes) != total:
        refusals.append(f"the tile sizes sum to {sum(sizes):,} against a "
                        f"reported {total:,}: an accounting discrepancy, not a "
                        "measurement")
    reached = total >= declared * (1 - REACH_TOLERANCE)
    if all(intact) and not reached:
        refusals.append(
            f"the output stopped at {total:,} bytes, {100 * (1 - total / declared):.1f}% "
            "below the declared length: the guards are unchanged because "
            "nothing reached them")

    if refusals:
        return {"verdict": "refused", "reasons": refusals, "guards": guards,
                "reported_total": total, "declared": declared,
                "demand": demand.get("encoded_bytes") or demand.get("modelled_bytes")}
    if not all(intact):
        return {"verdict": "bound_exceeded",
                "reasons": [f"guard {i} reads 0x{g:08X}, not the magic"
                            for i, (g, ok) in enumerate(zip(guards, intact))
                            if not ok],
                "guards": guards, "reported_total": total, "declared": declared,
                "note": "the engine wrote past the length it was handed; the "
                        "destination must therefore be sized from a bound, not "
                        "from the declared length"}
    return {"verdict": "bound_enforced",
            "reasons": [f"the host encoder needs {demand['encoded_bytes']:,} B "
                        f"for this pattern, above the declared {declared:,} B",
                        f"the codec accepted the work and reported {total:,} B, "
                        "which reached the limit",
                        "all five guards hold the magic"],
            "guards": guards, "reported_total": total, "declared": declared,
            "note": "established for THIS geometry, THIS pattern and THIS "
                    "firmware, on the runs recorded. It is not a proof about "
                    "the hardware, and it does not authorise encoding in "
                    "place over a frame's RAW"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--encoder-dir", type=pathlib.Path)
    parser.add_argument("--model-only", action="store_true",
                        help="use the cost model rather than the real encoder")
    parser.add_argument("--measurement", type=pathlib.Path,
                        help="a JSON record from a probe run, to judge")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    demand = host_demand(encoder_dir=args.encoder_dir, exact=not args.model_only)
    out = {"demand": demand}
    if args.measurement:
        out["verdict"] = verdict(json.loads(args.measurement.read_text()), demand)
    if args.json:
        print(json.dumps(out, indent=2))
        return 0
    print(f"source            {demand['source_bytes']:,} B  "
          f"sha256 {demand['source_sha256'][:16]}")
    print(f"tiles             {demand['tiles']} "
          f"({demand['whole_tiles']} whole, {demand['partial_tiles']} clipped)")
    print(f"samples counted   {demand['samples_counted']:,} "
          f"(padded would be {demand['samples_if_padded']:,})")
    if demand["encoded_bytes"] is not None:
        print(f"ENCODED HERE      {demand['encoded_bytes']:,} B")
    print(f"cost model        {demand['modelled_bytes']:,} B")
    print(f"declared length   {demand['declared_length']:,} B")
    print(f"bits/sample       {demand['bits_per_sample']}")
    print(f"demands more      {demand['demand_exceeds_declared']}")
    if "verdict" in out:
        print(f"\nVERDICT           {out['verdict']['verdict']}")
        for reason in out["verdict"]["reasons"]:
            print(f"  - {reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
