#!/usr/bin/env python3
"""One geometry reading at a chosen `kind`, so the kinds can be told apart.

    ./geomkind.py 2

`geomprobe.py` is pinned to kind 3 because that is the only value proved safe.
This is the deliberate, one-shot version for trying another: a single call, no
loop, so a wedge costs one reading rather than a run.

kind is chosen by the caller, not free.  Real call sites:

    blk_c03:80450   kind 2   recMgr/StillCreate, capture type == 1
    blk_c03:80465   kind 4   capture type == 9
    blk_c03:80509   kind 3   otherwise
    blk_c06:133577  kind 3, or 2 when the DNG format object's +0x44 == 2

kind 3 answers 6064x4042 -- the stills full raster -- in standby and right
through a CINE take, so it is not the one the movie path uses.

⚠ kind 2 froze the camera once, on 2026-09-19, but with a NULL context: the
first version of this probe called FUN_c0021c40 with no argument, and
FUN_c0436b80's `param_1 == 2 && param_3[3] == 0` branch is the one kind 2 takes
and the one that dereferences it.  The context is fetched properly here.
"""
import sys
import pathlib

SHELL = pathlib.Path('/Users/dido/Developer.localized/SIGMAfp_re/fpSup/fp_usb_shell')
sys.path.insert(0, str(SHELL))

from callfn import call                                   # noqa: E402
from putfile import mem_get, mem_set                       # noqa: E402

GEOM_QUERY = 0xC0437140
CTX_OWNER  = 0xC0021C00
CTX_GET    = 0xC0021C40
RELEASE    = 0xC022EDB0
MODE_NOW   = 0xC032C720
OUT        = 0xC072F740


def main():
    kind = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    ok, owner = call(CTX_OWNER)
    if not ok:
        raise SystemExit('  no owner')
    ok, ctx = call(CTX_GET, r0=owner)
    print(f'  ctx     0x{ctx:08X}' if ctx else f'  ctx     {ctx}')
    if not ctx:
        raise SystemExit('  no context; not calling the query with a null')

    mem_set(OUT, 0)
    ok, _ = call(GEOM_QUERY, r0=OUT, r1=kind, r2=ctx, r3=3)
    p = ((mem_get(OUT, 1) or [None])[0]) or 0
    print(f'  kind {kind}  out 0x{p:08X}')
    if 0xC0000000 <= p < 0xC4000000:
        w = mem_get(p, 8)
        if w:
            print(f'           {w[0]} x {w[1]}     rest ' +
                  ' '.join(str(x) for x in w[2:]))
    # Unconditional: a skipped release leaks 0xC0 bytes per reading.
    call(RELEASE, r0=OUT, r1=2)
    _, mode = call(MODE_NOW)
    print(f'  mode    {mode}')


if __name__ == '__main__':
    main()
