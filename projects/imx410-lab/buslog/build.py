#!/usr/bin/env python3
"""IMXB -- the IMX410 bus logger as a loader v4 sup (buslog.S).

    python3 -B build.py [--out DIR] -> build/IMXB.BIN, build/build.json
"""
import hashlib, json, pathlib, struct, sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SHELL = ROOT / 'fpSup' / 'fp_usb_shell'
sys.path[:0] = [str(SHELL.parent / 'loader-v4'), str(SHELL / 'v3'), str(SHELL)]
import build_v4 as B4                          # noqa: E402
import build_v3 as B3                          # noqa: E402
from armasm import assemble                    # noqa: E402

SUP_ID, VERSION, NAME = 'IMXB', 3, 'IMX410 Bus Log'
OUT = HERE / 'build' / 'IMXB.BIN'
SITE, STOCK = 0xC0322C70, (0xE92D4130, 0xE24DD004)
CAP = 1 << 15                                  # entries (512 KiB of ring)
STATE_HEAD = 64
CAPT = STATE_HEAD + 16 * CAP                 # capture block, from the state
CAPT_LOG = 64                                  # completions recorded
CAPT_BYTES = 0x50 + 8 * CAPT_LOG


def build(defines=()):
    img = B3.IMAGE.read_bytes()
    if struct.unpack_from('<2I', img, SITE - 0xC0000000) != STOCK:
        raise SystemExit('C0322C70 is not the stock prologue in the reference image')
    src = HERE / 'buslog.S'
    defs = lambda so: [f'STATE_OFF={so}', f'CAP={CAP}', f'CAPT={CAPT}', f'CAPT_LOG={CAPT_LOG}', *defines]
    body = assemble(src, defs(0))
    probe = B4.make_sup(body, B4.SL4_HEADER_LEN, SUP_ID, version=VERSION, flags=B4.SL_F_CACHED_OK,
                        min_svc=B4.SL4_SVC_VERSION, name=NAME)
    state_off = (len(probe) + 63) & ~63
    body = assemble(src, defs(state_off))
    block = state_off + CAPT + CAPT_BYTES
    sup = B4.make_sup(body, B4.SL4_HEADER_LEN, SUP_ID, version=VERSION, flags=B4.SL_F_CACHED_OK,
                      min_svc=B4.SL4_SVC_VERSION, name=NAME, block_size=block)
    if len(sup) != len(probe):
        raise SystemExit('layout moved between passes')
    info = dict(file_len=len(sup), block_size=block, state_off=state_off, cap=CAP, capt=CAPT, capt_log=CAPT_LOG,
                sha256=hashlib.sha256(sup).hexdigest())
    return sup, info


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=pathlib.Path)
    a = ap.parse_args()
    out = (a.out / OUT.name) if a.out else OUT
    sup, info = build()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(sup)
    (out.parent / 'build.json').write_text(json.dumps(info, indent=1))
    print(f'{out.name}: {info["file_len"]} B, block {info["block_size"]} B, state +{info["state_off"]}, '
          f'sha256 {info["sha256"][:16]}')


if __name__ == '__main__':
    main()
