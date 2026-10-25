#!/usr/bin/env python3
"""Build fpScreenFlip as a Loader v4 sup: \\fpSup\\FLIP.BIN.

    python3 -B screenflip/build_v4_flip.py --out /absolute/new/directory

build_v3_flip.py's sup with (the user 2026-10-22: the row stays on the stock
TOOLS page, Y2_5_1):
  - the 48-byte FSB4 header, SL_F_CACHED_OK, the display name after the
    FPUI block;
  - the row through fpsup-ui's fpui_stock.c: the same FPUI block, composed the
    same way, but its strings are ids = their own address (the v4 core's
    resolve rule), borrowed with svc->borrow -- no string-site claims;
  - the saved table at 48 + `settings`, written only while svc->file_is says
    the file is still this sup.
"""
import argparse, hashlib, json, pathlib, struct, sys

HERE = pathlib.Path(__file__).resolve().parent
FPSUP = HERE.parent
ROOT = FPSUP.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(FPSUP / 'loader-v4'))

import build_v3_flip as F3                               # noqa: E402
import build_v4 as B4                                    # noqa: E402
import names_v4 as N                                     # noqa: E402

NAME = N.file_name('FLIP')                               # ScreenFlip_v0.1.0.BIN (names_v4)
DISPLAY = N.display('FLIP')                              # "Screen Flip"



def sup_file():
    tail = DISPLAY.encode() + b'\0'
    blob, facts = F3.build_blob(v4=True, tail=tail)
    data = bytearray(B4.make_sup(blob, B4.SL4_HEADER_LEN, F3.SUP_ID, version=F3.VERSION,
                                 block_size=B4.SL4_HEADER_LEN + facts['block_bytes'],
                                 min_svc=6, flags=B4.SL_F_CACHED_OK))
    struct.pack_into('<I', data, 44, B4.SL4_HEADER_LEN + facts['tail_off'])          # name_off
    return bytes(data), facts


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--out', type=pathlib.Path, required=True)
    a = ap.parse_args(argv)
    out = a.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f'{out} is not empty: this never overwrites a build')
    out.mkdir(parents=True, exist_ok=True)
    data, facts = sup_file()
    (out / NAME).write_bytes(data)
    sources = [pathlib.Path(__file__), HERE / 'build_v3_flip.py', HERE / 'native' / 'entry.S',
               HERE / 'native' / 'flip.c', HERE / 'native' / 'flip.h',
               FPSUP / 'fpsup-ui' / 'fpui_stock.c', FPSUP / 'loader-v4' / 'sloader4.h',
               HERE / 'menu' / 'build_flip_page.py', HERE / 'menu' / 'build_flip_fpui.py']
    (out / 'build.json').write_text(json.dumps({
        'product': 'fpScreenFlip, Loader v4 sup', 'file': NAME, 'sup_id': F3.SUP_ID,
        'version': F3.VERSION,
        'blob': {k: v for k, v in facts.items() if k not in ('row', 'defines')},
        'row': facts['row'], 'sha256': hashlib.sha256(data).hexdigest(),
        'sources': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in sources},
        'written_to_card': False, 'camera_tested': False}, indent=1) + '\n')
    print(f'{NAME}: {len(data)} B, sha256 {hashlib.sha256(data).hexdigest()[:16]}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
