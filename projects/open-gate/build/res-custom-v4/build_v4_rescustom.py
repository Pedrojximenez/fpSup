#!/usr/bin/env python3
"""res-custom for Loader v4: \\fpSup\\RESCUS.BIN and its format data files.

    python3 -B build_v4_rescustom.py --out /absolute/new/directory [--formats og3k,og2k]

The released v0.1.4test (projects/open-gate/archive/res-custom-before-generalize-
20261019, the user 2026-10-22: the 10-19 refactor does not ship) with, under
OGC_V4 / build_core(v4=True) and nothing else:

  * FSB4's 48-byte header, SL_F_CACHED_OK, min_svc 6; the settings record at 48;
    the display name "RES-Custom" before the layout image (S's body stays zero);
  * the block runs at the cached alias: the file object and its scratch are at
    the uncached alias, and the D-cache is cleaned and invalidated around the
    reads of the .RCD files and the write of the record;
  * the menu through fpsup-ui: fpui_stock_apply (private strings are address
    ids, borrowed; the core's string hooks resolve them) -- no string site is
    claimed, the file-redirect site C05E5BEC stays SHARED_UI;
  * the file list (v3: svc->button + uishare strings) is an FT4S page,
    FT_RCFILES (rc_files_page.ft4), installed with fpsup_ui.c behind a JUMP row
    "RES-Custom" on the fpSup page; MENU goes back to FT_Y6.

The .RCD files are the same bytes as v3's, in \fpSup\RESCUS\ (found next to
its own file, whatever that is called).  The file is RES-Custom_v0.1.4.BIN
(fpSup/loader-v4/names_v4.py, the user 2026-10-25).  Tests: test_v4_rescustom.py.
"""
import argparse, hashlib, json, pathlib, sys, tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_v3_rescustom as B                          # noqa: E402
sys.path.insert(0, str(HERE.parents[3] / 'fpSup' / 'loader-v4'))
import names_v4 as N                                    # noqa: E402

CORE_NAME = N.file_name('RCUS')                         # RES-Custom_v0.1.4.BIN
assert B.V4_DISPLAY == N.display('RCUS') and B.CORE_ID == 'RCUS'


def build(out, formats=B.FORMATS):
    out = out.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f'{out} is not empty: this never overwrites a build')
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='ogc4-') as t:
        tmp = pathlib.Path(t)
        data, facts, tpl = B.build_core(tmp, v4=True)
        rcds, rows = B.build_rcd(formats, tmp)
    (out / CORE_NAME).write_bytes(data)
    (out / B.RCD_DIR).mkdir()
    for n, d in rcds.items():
        (out / B.RCD_DIR / n).write_bytes(d)
    facts['file'] = CORE_NAME
    facts['formats'] = list(formats)
    facts['rows'] = [{k: (list(v) if isinstance(v, tuple) else v) for k, v in r.items()} for r in rows]
    files = {CORE_NAME: (data, facts)}
    files.update({f'{B.RCD_DIR}/{n}': (d, {'label': r['label'], 'target': r['target']})
                  for (n, d), r in zip(rcds.items(), rows)})
    (out / 'build.json').write_text(json.dumps({
        'product': 'fpSup res-custom, the multi-format OpenGate core and its data files (Loader v4)',
        'card': {'\\\\fpSup\\\\' + CORE_NAME: CORE_NAME,
                 **{'\\\\fpSup\\\\RESCUS\\\\' + n: f'{B.RCD_DIR}/{n}' for n in rcds}},
        'files': {n: {'sha256': hashlib.sha256(d).hexdigest(), 'bytes': len(d), 'facts': f}
                  for n, (d, f) in files.items()}}, indent=1) + '\n')
    return files


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--out', type=pathlib.Path, required=True)
    ap.add_argument('--formats', default=','.join(B.FORMATS))
    a = ap.parse_args()
    files = build(a.out, tuple(f.strip() for f in a.formats.split(',') if f.strip()))
    for n, (d, _) in files.items():
        print(f'{n}: {len(d):,} B  {hashlib.sha256(d).hexdigest()[:16]}')


if __name__ == '__main__':
    main()
