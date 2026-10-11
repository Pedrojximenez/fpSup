#!/usr/bin/env python3
"""Ask the camera what geometry it is recording, the way its own DNG writer does.

    ./geomprobe.py            one reading
    ./geomprobe.py -n 20      keep reading, so a take can be started underneath

The chain, all static (see notes/LENS_PROFILE_WRONG_SIZE_WITH_OG3K.md section 6):

    FUN_c0437140(&geom, kind, timestamp, 3)     the query the DNG writer makes
      -> FUN_c06a6418: FUN_c02e5b78(dngobj + 0x18, geom)
      -> FUN_c06A5290: tag 0x100 = [dngobj+0x18], tag 0x101 = [dngobj+0x1C]

so geom's first two words are the frame size the DNG header will claim.  What
this is checking is exactly that: that they are, and that they follow the mode
rather than the menu.

`geom` is a moved smart pointer -- FUN_c04386b0 writes one word and zeroes the
source -- so the out parameter is a single word holding a pointer to a 0xC0-byte
object from FUN_c0438980(0xc0).  It has to be released or every reading leaks
one, which is why RELEASE runs even when the read fails.
"""
import argparse
import sys
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
SHELL = pathlib.Path('/Users/dido/Developer.localized/SIGMAfp_re/fpSup/fp_usb_shell')
sys.path.insert(0, str(SHELL))

from callfn import call                                   # noqa: E402
from putfile import mem_get, mem_set                       # noqa: E402

GEOM_QUERY = 0xC0437140     # (out, kind, state, 3)
CTX_OWNER  = 0xC0021C00     # -> the singleton 0xC30751D4
CTX_GET    = 0xC0021C40     # (owner) -> *(owner + 0x5C), the live context POINTER
RELEASE    = 0xC022EDB0     # (&out, 2) -- the caller's own teardown
MODE_NOW   = 0xC032C720     # `imager mode_now`, for the mode the reading belongs to

# Inside the shell's parameter block, past callfn's own fields (which end at
# +0x24) and below the working template at 0xC072F800.
OUT = 0xC072F740


def one(kind, ts, verbose=False):
    """One query at `kind`.

    ⚠ kind is 3 and nothing else.  The DNG writer passes 2 only when its own
    format object says `*(this + 0x44) == 2`; that is a condition on the object,
    not a parameter anyone may choose.  Asking for 2 from here froze the camera
    on 2026-09-19 -- the shell stopped answering mid-reading and it took a
    battery pull.  kind 3 had been read cleanly a dozen times either side of it.
    """
    assert kind == 3, 'kind 2 froze the camera; see the docstring'
    mem_set(OUT, 0)
    ok, _ = call(GEOM_QUERY, r0=OUT, r1=kind, r2=ts, r3=3, verbose=verbose)
    if not ok:
        return None, None
    # A dropped read gives [None], not [0].  Releasing has to happen whatever
    # the read did, or a probe that runs for minutes leaks one 0xC0-byte object
    # per failure -- so it is unconditional and the reads around it are the
    # parts allowed to come back empty.
    p = ((mem_get(OUT, 1) or [None])[0]) or 0
    words = mem_get(p, 8) if 0xC0000000 <= p < 0xC4000000 else None
    call(RELEASE, r0=OUT, r1=2, verbose=verbose)
    return p, words


def reading(verbose=False):
    # FUN_c0021c40 takes the owner and returns *(owner + 0x5C).  Calling it with
    # r0 = 0 returns *(0x5C) -- which is what the first version of this probe
    # did, so FUN_c0436b80 walked a null pointer (param_3[0x16d], param_3[0xcd])
    # and every reading came back as the template FUN_c0439478 copies out of
    # DAT_c0bd0010: a constant 6064x4042 that tracked nothing.  That is also why
    # kind 2 froze -- FUN_c0436b80's `param_1 == 2 && param_3[3] == 0` branch
    # dereferences it.  open-gate's HDMI_RAW_PATH.md already had this: "context
    # pointer at 0xC30751D4 + 0x5C".
    ok, owner = call(CTX_OWNER, verbose=verbose)
    if not ok:
        return None
    ok, ts = call(CTX_GET, r0=owner, verbose=verbose)
    if not ok or not ts:
        return None
    out = {3: one(3, ts, verbose)}
    _, mode = call(MODE_NOW, verbose=verbose)
    return out, mode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('-n', type=int, default=1, help='how many readings')
    ap.add_argument('-v', action='store_true', help='show every call')
    a = ap.parse_args()

    last = None
    for i in range(a.n):
        r = reading(a.v)
        if r is None:
            print(f'{i:3}  the query did not return', flush=True)
            continue
        out, mode = r
        cells, key = [], []
        for k in (3,):
            p, words = out[k]
            if words is None:
                cells.append(f'kind{k} -')
                key.append(None)
            else:
                cells.append(f'kind{k} {words[0]}x{words[1]}')
                key.append((words[0], words[1]))
        line = f'{i:3}  ' + '   '.join(cells) + f'   mode {mode}'
        if key != last:
            line += '   <-- changed'
            last = key
        print(line, flush=True)


if __name__ == '__main__':
    main()
