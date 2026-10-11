#!/usr/bin/env python3
"""Freeze current development Res tools as Merge inputs, without a release/tag.

Run in the research checkout; the catalogue subsequently needs only these
manifest-verified files, not the external product builders. Never overwrites
an existing snapshot or a frozen release.
"""
import argparse
import datetime
import hashlib
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BUILD = ROOT / 'projects/open-gate/build'


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--out', type=pathlib.Path, required=True)
    a = ap.parse_args()
    if a.out.exists():
        raise SystemExit('snapshot already exists; choose a new directory')
    with tempfile.TemporaryDirectory(prefix='merge-res-') as tmp:
        stage = pathlib.Path(tmp)
        for name, script, flags in (
            ('res-custom', BUILD / 'res-custom/build_v3_rescustom.py', []),
            ('res-custom-virtual', BUILD / 'res-custom/build_v3_rescustom.py', ['--virtual-rcd']),
            ('res-lab', BUILD / 'build_v3_reslab.py', ['--virtual-rcd']),
        ):
            subprocess.run([sys.executable, '-B', str(script), *flags, '--out', str(stage / name)],
                           check=True, cwd=ROOT)
        # The producer builder also emits its consumer. Keep one consumer
        # source, and prove it is the very same virtual-capable core.
        if (stage / 'res-lab/32RESCUS.BIN').read_bytes() != (stage / 'res-custom-virtual/32RESCUS.BIN').read_bytes():
            raise SystemExit('producer and consumer builds disagree')
        (stage / 'res-lab/32RESCUS.BIN').unlink()
        source = json.loads((stage / 'res-lab/build.json').read_text())['source_sha256']
        source['fpSup/tools/merge-v3/build_res_tools.py'] = hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()
        files = {}
        for p in sorted(stage.rglob('*')):
            if p.is_file():
                b = p.read_bytes()
                files[str(p.relative_to(stage))] = dict(size=len(b), sha256=hashlib.sha256(b).hexdigest())
        lab_files = list((stage / 'res-lab').glob('50*.BIN'))
        if len(lab_files) != 1:
            raise SystemExit('expected one RES-Lab Sup file')
        meta = dict(date=datetime.date.today().isoformat(), source_sha256=source, files=files,
                    products={
                        'res-custom': dict(file='res-custom/32RESCUS.BIN', virtual='res-custom-virtual/32RESCUS.BIN',
                                           data_files=[str(p.relative_to(stage)) for p in sorted((stage / 'res-custom/RESCUS').glob('*.RCD'))]),
                        'res-lab': dict(file=str(lab_files[0].relative_to(stage)), support_files=['res-lab/RESCUS/README.TXT']),
                    })
        (stage / 'manifest.json').write_text(json.dumps(meta, indent=2) + '\n')
        a.out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(stage, a.out)
    print('Merge development inputs:', a.out)


if __name__ == '__main__':
    main()
