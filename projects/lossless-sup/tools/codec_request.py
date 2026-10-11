#!/usr/bin/env python3
"""The 0x300D encoder's request ABI, transcribed from the firmware.

WHY THIS EXISTS

The target architecture compresses a hijacked frame while later frames pass
through the writer untouched. F_ENC (0xC05A6890's neighbour, 0xC05A6920) blocks
for 13.7 ms, so the question was whether that is inherent. It is not: the
hardware raises a completion event and the firmware's driver simply waits for
it. Driving the engine ourselves and NOT waiting is therefore possible without
a new task, and this module is the arithmetic that requires.

THE CHAIN, ALL [C] - STATIC READING ONLY, NOTHING HERE HAS RUN

    F_ENC 0xC05A6920   ARM. Copies the caller's encStruct into a 0x14-byte
                       frame, maps encStruct[8] through C03D9668, and calls
    0xC062F6F8         THUMB. The driver. Computes the bands, builds a 0x30-byte
                       request, installs the firmware's completion callback
                       0xC062FCB1 at request+0x2C, and loops once per band:
                         clr_flg(FLG, 0)
                         C062FE98(&request) -> C062FFF8(&request)   the submit
                         twai_flg(FLG, 5, 1, &pattern, timeout)     the wait
                         clr_flg(FLG, 0)
                       E_TMOUT is -50 and the loop retries on it. Pattern bit 0
                       is done and bit 2 is error, which is what the callback
                       0xC062FCB0 sets through set_flg.
    0xC062FFF8         THUMB. Writes the engine's registers at 0x300D0040 and
                       memcpies the request to 0xC37CF884. Nothing above it
                       touches hardware, so calling THIS is enough.

STATIC READING HAS MISLED THIS PROJECT TWICE - the writer vtable was read eight
bytes off, and earlier in this same session C00169C8 was read as a wait when it
is clr_flg. Every number here needs live confirmation before anything drives the
engine with it.

Offline only: no camera, no card.
"""

# The engine's parameter block, filled by F_INIT from the caller's initStruct.
# MEASURED on the camera 2026-09-29 by PHASE 11 stage one, at 1536x736 with
# 512x368 tiles and depth code 0, F_INIT returning 1:
#   +0x00  0x85177000   the source, TRANSLATED to the uncached alias (+0x40000000)
#   +0x04  0x0019E000   the SOURCE LENGTH, 12 * 1536 * 736 / 8 = 1,695,744
#   +0x08  0x85317000   the destination, also translated
#   +0x0C  0x0019E000   the declared length, round_up(source, 1024)
#   +0x10  0x45568000   the size table, NOT translated - still the cached address
#   +0x14  0x00000018   the size table length, 6 tiles * 4 bytes
# Two things that were guesses and are now facts: +0x04 is the source length,
# and F_INIT translates the two DATA pointers to the uncached view while leaving
# the table pointer alone.
ENGINE = 0xC302CDD4
ENG_SOURCE = 0x00           # initStruct[0x14], uncached-translated
ENG_SOURCE_LEN = 0x04       # measured: the source length
ENG_DEST = 0x08             # initStruct[0x18], uncached-translated
ENG_DEST_LEN = 0x0C         # the DECLARED LENGTH. Read live as 0x305000 at FHD.
ENG_SIZE_TABLE = 0x10       # initStruct[0x1C], NOT translated
ENG_SIZE_TABLE_LEN = 0x14   # measured: tiles * 4
TILE_COUNT_AT = 0xC302CDEC  # the driver writes the tile count here
FLAG_ID_AT = 0xC2F2E60C     # [this] is the event flag id - BUT SEE BELOW
# MEASURED 2026-09-29: after F_INIT alone, [0xC2F2E60C] reads 0xFFFFFFD6 = -42,
# which is E_NOEXS. The flag does not exist yet. F_INIT does not create it, so
# something on the driver's own path does - C062F440 at the top of C062F6F8 is
# the candidate, or the first F_ENC. An asynchronous submit that waits on this
# id before it has been created would wait on nothing, so stage two has to
# establish who creates it and when.
FLAG_ID_UNINITIALISED = 0xFFFFFFD6

# WHO CREATES IT, found statically after the measurement above [C]:
#
#   C062F440()   Thumb, so call it as 0xC062F441. IDEMPOTENT:
#                  r0 = [0xC2F2E60C]
#                  if r0 >= 0: return r0                  already created
#                  copy the 5-word template at 0xC2E32CAC to the stack
#                  r0 = C00169EC(&template)               veneer id 0x80200100,
#                                                         one argument: acre_flg
#                  [0xC2F2E60C] = r0
#                  return [0xC2F2E60C]
#
# The driver calls it first thing and refuses if the result is negative. So an
# asynchronous submit does NOT need a full F_ENC to open the session: one call to
# C062F441 is enough, and calling it when the flag exists costs a compare.
FLAG_CREATE = 0xC062F441
FLAG_CREATE_TEMPLATE = 0xC2E32CAC
ACRE_FLG_VENEER = 0xC00169EC

# A second driver variant at 0xC062FB.. waits on pattern 2 rather than 5 on the
# same flag, so the flag carries more than one operation's completion. Anything
# of ours that clears it has to assume the engine is otherwise idle - which a
# recording guarantees, since a still cannot be taken while recording and
# CinemaDNG recording does not compress.
OTHER_WAIT_PATTERN = 2
REQUEST_COPY_AT = 0xC37CF884
HW_BASE = 0x300D0000
SUBMIT = 0xC062FFF8         # Thumb; call with the low bit set: 0xC062FFF9
CALLBACK = 0xC062FCB1       # the firmware's own, installed at request+0x2C
TWAI_FLG = 0xC0016C08       # (flgid, waiptn, wfmode, &pattern, timeout)
CLR_FLG = 0xC00169C8        # (flgid, clrptn)
WAIT_PATTERN = 5            # bit 0 = done, bit 2 = error
WAIT_MODE = 1               # TWF_ORW
E_TMOUT = -50
DONE_BIT, ERROR_BIT = 1, 4

# The request, 0x30 bytes. Offsets are the driver's stack frame at sp+0x3C.
REQ_BYTES = 0x30
R_WIDTH = 0x00
R_BAND_HEIGHT = 0x04        # the BAND's height, not the frame's
R_DEPTH = 0x08              # the code below, after C03D9668
R_TILE_W = 0x0C
R_TILE_H = 0x10
R_SOURCE = 0x14             # advanced per band
R_BAND_CAPACITY = 0x18      # round_up(bits * width * band_height / 8, 1024)
R_DEST = 0x1C               # advanced per band to the previous band's end
R_DEST_REMAINING = 0x20     # ENG_DEST_LEN, decremented per band
R_SIZE_SCRATCH = 0x24       # ENG_SIZE_TABLE + round_up(ENG_SIZE_TABLE_LEN, 1024)
R_SIZE_SCRATCH_LEN = 0x28   # ENG_SIZE_TABLE_LEN
R_CALLBACK = 0x2C

# C062FE40: the depth code the engine wants, and what it means.
DEPTH_BITS = {0: 12, 1: 14, 2: 16, 3: 10}
PASS_BUDGET = 0x4000000     # 64 MiB, the cap in C062F478


class Refused(Exception):
    """The firmware would refuse this geometry outright."""


def depth_bits(code):
    if code not in DEPTH_BITS:
        raise Refused(f"depth code {code} maps to 0 bits, which C062FE40 "
                      "returns for anything outside 0..3")
    return DEPTH_BITS[code]


def tile_grid(width, height, tile_w, tile_h):
    return -(-width // tile_w), -(-height // tile_h)


def rows_per_pass(width, height, tile_w, tile_h, depth_code):
    """C062F478. min(how many tile rows fit in 64 MiB, how many there are)."""
    bits = depth_bits(depth_code)
    row_band_bytes = (width * bits * tile_h) >> 3
    if row_band_bytes > PASS_BUDGET:
        raise Refused(
            f"one tile row needs {row_band_bytes:,} bytes, above the "
            f"{PASS_BUDGET:,} budget; C062F478 returns -1 and the driver stops")
    _, tile_rows = tile_grid(width, height, tile_w, tile_h)
    return min(PASS_BUDGET // row_band_bytes, tile_rows)


def bands(width, height, tile_w, tile_h, depth_code):
    """(tile_rows - 1) / rows_per_pass + 1, exactly as the driver computes it.

    For every geometry this camera records - FHD and UHD alike - this is ONE.
    The 64 MiB budget only bites on a frame larger than 64 MiB, so the driver
    submits the whole frame in a single request and waits once. That is what
    makes the asynchronous plan simple: submit, return, poll, done. No band
    state machine is needed.
    """
    _, tile_rows = tile_grid(width, height, tile_w, tile_h)
    per = rows_per_pass(width, height, tile_w, tile_h, depth_code)
    return (tile_rows - 1) // per + 1


def band_shape(i, width, height, tile_w, tile_h, depth_code):
    """One band's height and tile count, as the loop recomputes them."""
    cols, tile_rows = tile_grid(width, height, tile_w, tile_h)
    per = rows_per_pass(width, height, tile_w, tile_h, depth_code)
    total = (tile_rows - 1) // per + 1
    if not 0 <= i < total:
        raise Refused(f"band {i} of {total}")
    if i == total - 1:
        rows = (tile_rows - 1) % per + 1
        band_h = height % (per * tile_h) or per * tile_h
    else:
        rows = per
        band_h = per * tile_h
    return {"band_height": band_h, "tiles": rows * cols, "tile_rows": rows}


def source_advance(width, tile_h, depth_code, per=None, **geometry):
    """How far the source pointer moves between bands.

    bits * width * tile_h / 8 * rows_per_pass, and the driver REFUSES unless it
    is a multiple of 1024: it tests (step << 22) != 0 and returns 1.
    """
    bits = depth_bits(depth_code)
    if per is None:
        per = rows_per_pass(width=width, tile_h=tile_h, depth_code=depth_code,
                            **geometry)
    step = (bits * width * tile_h) >> 3
    step *= per
    if step & 0x3FF:
        raise Refused(f"a source step of {step:,} is not 1024-aligned; the "
                      "driver tests (step << 22) and returns 1")
    return step


def band_capacity(width, band_height, depth_code):
    """request+0x18: round_up(bits * width * band_height / 8, 1024)."""
    bits = depth_bits(depth_code)
    raw = (bits * width * band_height) >> 3
    return (raw + 0x3FF) & ~0x3FF


def plan(width, height, tile_w, tile_h, depth_code):
    """Everything a caller needs to build the requests for one frame."""
    cols, tile_rows = tile_grid(width, height, tile_w, tile_h)
    per = rows_per_pass(width, height, tile_w, tile_h, depth_code)
    total = (tile_rows - 1) // per + 1
    out = {"width": width, "height": height, "tile_w": tile_w,
           "tile_h": tile_h, "depth_code": depth_code,
           "bits_per_sample": depth_bits(depth_code),
           "tile_cols": cols, "tile_rows": tile_rows, "tiles": cols * tile_rows,
           "rows_per_pass": per, "bands": total, "band": []}
    for i in range(total):
        shape = band_shape(i, width, height, tile_w, tile_h, depth_code)
        shape["capacity"] = band_capacity(width, shape["band_height"], depth_code)
        out["band"].append(shape)
    if total > 1:
        out["source_step"] = source_advance(
            width=width, height=height, tile_w=tile_w, tile_h=tile_h,
            depth_code=depth_code, per=per)
    return out


def main():
    import argparse
    import json
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--width", type=int, default=1936)
    ap.add_argument("--height", type=int, default=1090)
    ap.add_argument("--tile", default="512x368")
    ap.add_argument("--depth", type=int, default=0)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    tw, th = (int(p) for p in a.tile.lower().split("x"))
    out = plan(a.width, a.height, tw, th, a.depth)
    if a.json:
        print(json.dumps(out, indent=2))
        return 0
    print(f"{a.width}x{a.height}  tiles {tw}x{th}  "
          f"depth code {a.depth} = {out['bits_per_sample']} bits")
    print(f"  grid            {out['tile_cols']}x{out['tile_rows']} "
          f"= {out['tiles']} tiles")
    print(f"  rows per pass   {out['rows_per_pass']}")
    print(f"  BANDS           {out['bands']}")
    for i, b in enumerate(out["band"]):
        print(f"    band {i}: height {b['band_height']}, {b['tiles']} tiles, "
              f"capacity {b['capacity']:,} B")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
