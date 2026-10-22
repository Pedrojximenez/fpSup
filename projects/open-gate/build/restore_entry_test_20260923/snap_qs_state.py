#!/usr/bin/env python3
"""READ-ONLY snapshot for 'is Quick Set on screen?': the resource context tail
(ctx+0x800..+0x8B4), the UicCont singleton head, and the QS_CINE layout object.

    python3 snap_qs_state.py LABEL      -> qs_state_<LABEL>.json
"""
import json, signal, sys
from pathlib import Path
sys.path.insert(0, '/Users/dido/Developer.localized/SIGMAfp_re/fpSup/fp_usb_shell')
signal.alarm(120)
from putfile import mem_get


def words(a, n):
    out = []
    while n > 0:
        k = min(n, 16)
        for _ in range(6):
            g = mem_get(a, k)
            if not any(x is None for x in g):
                break
        else:
            raise SystemExit(f'read fail {a:#x}')
        out += g; a += 4 * k; n -= k
    return out


ctx = words(0xC37B7048, 1)[0]
vec = words(ctx + 0x7C, 5)
ptrs = words(vec[4], vec[1])
qs = None
for p in ptrs:
    if words(p + 8, 1)[0] == 0xC18DF064:        # name ptr of "QS_CINE"
        qs = p
        break
snap = dict(ctx=ctx, uiccont=words(0xC37B7048, 16),
            ctx_tail=words(ctx + 0x800, (0x8B4 - 0x800) // 4),
            qs_cine=qs, qs_obj=words(qs, 16) if qs else None)
out = Path(__file__).with_name(f'qs_state_{sys.argv[1]}.json')
out.write_text(json.dumps(snap, indent=1))
print('saved', out.name, 'ctx', hex(ctx), 'QS_CINE', hex(qs) if qs else None)
