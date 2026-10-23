#!/usr/bin/env python3
"""FCAP -- batch frame cap (guardrail, not an optimisation).  Loader v3 patch sup.

    python3 -B build.py        -> build/30FCAP.BIN

The stock CinemaDNG file layer releases frames only when a 64 MiB batch is
written, while the scarce resource is the 96-slot frame descriptor pool (94
usable).  Stock files are 2-8 MB, so a batch never holds more than ~30 frames;
compressed (LOSS) and small res-custom files break that assumption.  Stock
already flushes a batch at 128 frames -- C063F826 `cmp r2, #0x80` on
vol+0x4850 -- but 128 > 94 so it never fires.  FCAP lowers it to 40:

    in flight ~ k + k * (data rate / media rate) + reserve <= 94
    media keeping up => ratio <= 1 => k <= (94 - 14) / 2 = 40

independent of file size, compression, resolution and frame rate.  The compare
is `==`; vol+0x4850 is only ever incremented by 1, right after this compare,
and reset by C063F140 / C063F220, so every value is passed (WRITER_PLAN §3a).

Whole-word claim at 0xC063F824 (the second half of `ldr.w r2, [r8, r2]` and the
cmp), SL_EXCL; the loader journals the stock word and restores it at power-off.
"""
import pathlib, struct, sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
V3 = ROOT / 'fpSup' / 'fp_usb_shell' / 'v3'
sys.path.insert(0, str(V3))
sys.path.insert(0, str(V3.parent))
import build_v3 as B                        # noqa: E402  (read-only use)

SUP_ID = 'FCAP'
VERSION = 1
SITE = 0xC063F824
STOCK = bytes.fromhex('0220802a')            # ...ldr.w r2,[r8,r2] (tail) ; cmp r2, #0x80
CAP = 40
OUT = HERE / 'build' / '30FCAP.BIN'
SL_EXCL = 2


class BuildError(RuntimeError):
    pass


def patched_word(cap=CAP):
    if not 1 <= cap <= 0x7F:
        raise BuildError('cap must fit the 8-bit compare and stay below the 128-entry cookie array')
    return STOCK[:2] + bytes([cap, 0x2A])    # T1 cmp r2, #imm8 = 0x2A00 | imm8


def build(cap=CAP):
    if B.stock(SITE, 4) != STOCK:
        raise BuildError(f'reference image has {B.stock(SITE, 4).hex()} at {SITE:#x}, not {STOCK.hex()}')
    return B.patch_sup(SUP_ID, [(SITE, patched_word(cap), SL_EXCL)], version=VERSION)


def main():
    import hashlib
    data = build()
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_bytes(data)
    print(f'{OUT}  {len(data)} B  sha256 {hashlib.sha256(data).hexdigest()}')


if __name__ == '__main__':
    main()
