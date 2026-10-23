#!/usr/bin/env python3
"""Build an M12 239.76p development card through the maintained shared builder."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE/'res-custom')]
import build_v3_rescustom as RC
import rcd


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--debug', action='store_true', help='include the existing USB shell')
    a = ap.parse_args()
    out = a.out.resolve()
    cmd = [sys.executable, '-B', str(HERE/'build_v3_reslab.py'),
           '--virtual-rcd', '--card', '--out', str(out)]
    if not a.debug:
        cmd.append('--no-shell')
    subprocess.run(cmd, check=True)
    with tempfile.TemporaryDirectory(prefix='m12240-') as d:
        row = RC.row_data('m12-240', Path(d))
        blob = rcd.encode(row, row['pack'])
        decoded = rcd.decode(blob, RC.img(), {RC.word(RC.TT+32*i) for i in range(70)})
    target = out/'fpSup/RESCUS/M12240.RCD'
    target.write_bytes(blob)
    meta = json.loads((out/'build.json').read_text())
    meta.update(product='M12 239.76p Virtual RCD development card',
                mode=dict(label='M12240', raw=[1008,672], active=[992,662],
                          bit_depths=[12], menu_fps='240000/1001',
                          sensor_fps=72000000/(330*910), profile=13,
                          entries=decoded['entries'], provenance=row['provenance']),
                hardware_verified=False, deployed=False)
    meta['source_sha256'].update({str(p.relative_to(HERE.parents[2])):
                                 hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in (Path(__file__).resolve(), HERE/'res-custom/m12_240.py')})
    (out/'build.json').write_text(json.dumps(meta, indent=2)+'\n')
    (out/'README.txt').write_text(
        'M12240 development mode: M12 / p13, 992x662 active, 1008x672 RAW, 12-bit.\n'
        'Enable M12240.RCD in RES-CUSTOM More Settings, restart, then select M12240\n'
        'in Resolution and 239.76p in Frame Rate. Select CinemaDNG 12-bit.\n'
        'This RCD declares a real 239.76p entry; do not use the old H2S240 29.97p mapping.\n'
        'Lower listed rates have their own sensor timing. 279.72p is not provided.\n'
        'The current shared loader and RES-Lab are included; this is an offline candidate.\n'
        'Sustained recording, RAW integrity, preview/FOV and repeated start/stop need camera validation.\n'
        'Prior successful clip A001_193 supports the predecessor family; its exact build is unknown.\n'
    )
    (out/'MANIFEST.sha256').write_text(''.join(
        f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(out)}\n'
        for p in sorted(out.rglob('*')) if p.is_file() and p.name != 'MANIFEST.sha256'))
    print(f'M12240.RCD: {len(blob)} bytes; shared consumer v{RC.VERSION}; offline candidate')


if __name__ == '__main__':
    main()
