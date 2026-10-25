#!/usr/bin/env python3
"""Build the Loader v4 product snapshot the Merge v4 page reads.

    python3 -B tools/merge-v4/build_inputs_v4.py --out tools/merge-v4/inputs/v4-YYYYMMDD

Runs each product's own v4 builder (nothing is rebuilt by hand), copies the
outputs into a NEW directory and writes manifest.json in the format
build_catalogue_v4.input_products() checks (the same as merge-v3's snapshots):
every file's size and sha256, each product's sup and data files, and the
sha256 of every builder source.  Refuses to overwrite a snapshot.
"""
import argparse, datetime, hashlib, json, pathlib, shutil, subprocess, sys, tempfile

HERE = pathlib.Path(__file__).resolve().parent
FPSUP = HERE.parent.parent
ROOT = FPSUP.parent
sys.path.insert(0, str(FPSUP / 'loader-v4'))
import names_v4 as N                                     # noqa: E402  (file names, versions)

# product id -> (builder, its output relative to the builder's --out, extra args)
BUILDS = {
    'ports': ([FPSUP / 'loader-v4/ports.py'], 'fpSup'),
    'jose': ([FPSUP / 'loader-v4/ports_jose.py'], 'fpSup'),
    'loss': ([FPSUP / 'lossless/build_v4_lossless.py'], '.'),
    'flip': ([FPSUP / 'screenflip/build_v4_flip.py'], '.'),
    'rawv': ([ROOT / 'projects/rawview/build/build_v4_rawview.py'], '.'),
    'rescus': ([ROOT / 'projects/open-gate/build/res-custom-v4/build_v4_rescustom.py'], '.'),
}
# product id -> (build, sup_id, data dir or None); the file is names_v4's
# <base>_v<version>.BIN (the user 2026-10-25)
PRODUCTS = {
    'res-custom': ('rescus', 'RCUS', 'RESCUS'),
    'lossless': ('loss', 'LOSS', None),
    'fcap': ('ports', 'FCAP', None),
    'unlocked-writer': ('ports', 'ULWR', None),
    'stopfx': ('ports', 'STFX', None),
    'gyro2': ('ports', 'GYR2', None),
    'raw-view': ('rawv', 'RAWV', None),
    'screenflip': ('flip', 'FLIP', None),
    'desqueeze': ('jose', 'DSQZ', None),
    'tap-to-zoom': ('jose', 'TAPZ', None),
    'usbshell': ('ports', 'SHEL', None),
}
SOURCES = [
    'fpSup/loader-v4/ports.py', 'fpSup/loader-v4/ports_jose.py', 'fpSup/loader-v4/build_v4.py',
    'fpSup/loader-v4/names_v4.py',
    'fpSup/fpsup-ui/fpui_stock.c', 'fpSup/fpsup-ui/fpsup_ui.c', 'fpSup/fpsup-ui/build_stock_section.py',
    'fpSup/lossless/build_v4_lossless.py', 'fpSup/lossless/native/menu_row4.c',
    'fpSup/screenflip/build_v4_flip.py', 'fpSup/screenflip/native/flip.c',
    'projects/rawview/build/build_v4_rawview.py', 'projects/rawview/build/build_v3_rawview.py',
    'projects/open-gate/build/res-custom-v4/build_v4_rescustom.py',
    'projects/open-gate/build/res-custom-v4/build_v3_rescustom.py',
    'projects/open-gate/build/res-custom-v4/ogc.c', 'projects/open-gate/build/res-custom-v4/ogc_files.c',
]
VALIDATION = ('fpSup/loader-v4/README.md "已上線 sup 的 v4 第一次上機(2026-10-24)": all eleven load, '
              'menus and saving checked on the camera; recording (ULWR, Gyro2, Lossless compression) not yet.')


def sha(b):
    return hashlib.sha256(b).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=pathlib.Path, required=True)
    a = ap.parse_args()
    out = a.out.resolve()
    if out.exists():
        raise SystemExit(f'{out} exists: a snapshot is never overwritten')
    files, products = {}, {}
    with tempfile.TemporaryDirectory(prefix='mergev4-') as t:
        t = pathlib.Path(t)
        for key, (cmd, sub) in BUILDS.items():
            r = subprocess.run([sys.executable, '-B', *map(str, cmd), '--out', str(t / key)],
                               capture_output=True, text=True, cwd=FPSUP)
            if r.returncode:
                raise SystemExit(f'{key}: builder failed\n{r.stderr[-3000:]}')
        out.mkdir(parents=True)
        for pid, (build, sid, data) in PRODUCTS.items():
            name = N.file_name(sid)
            src = t / build / BUILDS[build][1]
            b = (src / name).read_bytes()
            (out / name).write_bytes(b)
            files[name] = dict(size=len(b), sha256=sha(b))
            entry = dict(file=name, version=N.version(sid), name=N.display(sid),
                         release=f'fpsup-{pid}-v{N.version(sid)}',
                         build_label=dict(en='Loader v4 test build', zh='Loader v4 測試版'))
            if data:
                (out / data).mkdir()
                entry['data_files'] = []
                for f in sorted((src / data).iterdir()):
                    rel = f'{data}/{f.name}'
                    (out / rel).write_bytes(f.read_bytes())
                    files[rel] = dict(size=f.stat().st_size, sha256=sha(f.read_bytes()))
                    entry['data_files'].append(rel)
            products[pid] = entry
    meta = dict(date=f'{datetime.date.today():%Y-%m-%d}',
                source_sha256={s: sha((ROOT / s).read_bytes()) for s in SOURCES},
                files=files, products=products, loader='v4', validation=VALIDATION)
    (out / 'manifest.json').write_text(json.dumps(meta, indent=1, ensure_ascii=False) + '\n')
    for name, f in files.items():
        print(f'{name:28s} {f["size"]:8,d} B  {f["sha256"][:12]}')


if __name__ == '__main__':
    main()
