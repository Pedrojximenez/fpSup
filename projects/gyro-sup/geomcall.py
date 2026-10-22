#!/usr/bin/env python3
"""Call the compiled j_geom_dims on the camera, repeatedly.

    ./geomcall.py 0x4517C88C -n 40

The address is the one ring_task_deploy.py --gcsv --place prints for
`j_geom_dims`; it moves whenever the code is placed again, so it is an argument
rather than a constant.

What this covers that geomkind.py does not: the routine as gcsv_json.S actually
assembles it -- its stack handling, its two null checks and its unconditional
release -- and doing all that WHILE A TAKE IS RUNNING, which is when the query
allocates on a path that matters.  What it still does not cover: being called
from writer_openfile's context rather than the shell's.  Only a card does that.

r0 is the width; callfn returns one register, and the width alone is enough to
tell 1936 (FHD) from 3024 (OG3K) from 2016 (OG2K).
"""
import argparse
import sys
import pathlib

SHELL = pathlib.Path('/Users/dido/Developer.localized/SIGMAfp_re/fpSup/fp_usb_shell')
sys.path.insert(0, str(SHELL))

from callfn import call                                   # noqa: E402

MODE_NOW = 0xC032C720


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('addr', type=lambda s: int(s, 0))
    ap.add_argument('-n', type=int, default=40)
    a = ap.parse_args()

    last = None
    for i in range(a.n):
        ok, w = call(a.addr, verbose=False)
        _, mode = call(MODE_NOW, verbose=False)
        line = f'{i:3}  width {w if ok else "-"}   mode {mode}'
        if (ok, w) != last:
            line += '   <-- changed'
            last = (ok, w)
        print(line, flush=True)


if __name__ == '__main__':
    main()
