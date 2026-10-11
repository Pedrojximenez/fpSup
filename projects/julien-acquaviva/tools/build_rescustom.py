#!/usr/bin/env python3
"""Encode the extracted R168 fixed geometries as ordinary res-custom RCD3.

The catalogue is an archive: select up to six files for the core's RESCUS
directory. The maintained core/UI/NBR/XCI builders supply all executable code
and assets; none of Julien's loader, hooks or resident code is installed.
"""
from functools import lru_cache
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys

from extract_r168 import PROJECT, ROOT, RC, IMAGE, sha

os.environ['OG_TARGET'] = 'og3k'
for name in ('OG_V3', 'OG_CHAIN', 'OG_V3_OGV', 'OG_UISHARE'):
    os.environ.pop(name, None)
sys.path.insert(0, str(RC.parent))
import rcd
import ogc_layout as L
import build_og3k_ui_candidate as B


@lru_cache(maxsize=None)
def tile(text, width, height, numeric=False):
    planes = B._hud_tile(text, width, height) if numeric else B.text_tile(text, width, height, cap=24)
    blob = B.encode_xci(*planes)
    w, h, lo, hi = B.decode_xci(blob)
    if (w, h) != (width, height) or lo.tobytes() != planes[0].tobytes() or hi.tobytes() != planes[1].tobytes():
        raise ValueError('XCI round trip failed')
    return blob


def pack(row, firmware):
    label, text = row['label'], row['tile_text']
    resources = [B.Resource(label + '_' + suffix, label + '_' + suffix + '.xci', tile(text, w, h))
                 for suffix, w, h in (('QS', 86, 49), ('SET', 86, 74), ('FONT', 150, 38))]
    for value in dict.fromkeys(row['act']):
        name = f'font_S_imageSize_{value}'
        if name.encode() + b'\0' not in firmware:
            resources.append(B.Resource(name, name + '.xci', tile(str(value), 88, 38, True)))
    blob = B.build_nbr(resources)
    inv = B.inspect_nbr(blob)
    if {r['name'] for r in inv['resources']} != {r.name for r in resources}:
        raise ValueError('NBR inventory mismatch')
    return blob


def default_labels(doc):
    # Four data targets at full 3:2 24p, plus FAST full 16:9 and 2:1 24p.
    indices = [(mi, 0, 0, 1) for mi in range(4)] + [(0, ri, 0, 1) for ri in (1, 2)]
    selected = []
    for mi, ri, ci, fi in indices:
        state = next(i for i, s in enumerate(doc['states']) if
                     (s['media_index'], s['ratio_index'], s['crop_index'] % 19, s['fps_index']) == (mi, ri, ci, fi))
        selected.append(next(f['row']['label'] for f in doc['formats'] if state in f['states']))
    return selected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=PROJECT / 'build/r168-rescustom')
    parser.add_argument('--select', help='comma-separated labels, one to six; default is the six 24p examples')
    args = parser.parse_args()
    doc = json.loads((PROJECT / 'extracted/r168.json').read_text())
    firmware = IMAGE.read_bytes()
    if sha(firmware) != doc['image_sha256']:
        raise ValueError('firmware image differs from extraction')
    formats = {f['row']['label']: f for f in doc['formats']}
    labels = args.select.split(',') if args.select else default_labels(doc)
    if not 1 <= len(labels) <= L.MAX_ROWS or len(set(labels)) != len(labels) or set(labels) - formats.keys():
        raise ValueError('choose one to six distinct catalogue labels')
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    # Keep a previous selection out of the next core's directory; never erase
    # an unknown user's file. Use a new output path if the selection changes.
    selected_dir = out / 'RESCUS'
    selected_dir.mkdir(exist_ok=True)
    if {p.stem for p in selected_dir.glob('*.RCD')} - set(labels):
        raise ValueError('output contains another selection; use a new --out directory')
    core_dir = out / 'core-build'
    subprocess.run([sys.executable, '-B', str(RC / 'build_v3_rescustom.py'), '--out', str(core_dir)], check=True)
    shutil.copy2(core_dir / '32RESCUS.BIN', out / '32RESCUS.BIN')
    ids = {int.from_bytes(firmware[0xB59500 + i * 32:0xB59504 + i * 32], 'little') for i in range(70)}
    hashes, index = {}, []
    hashes['32RESCUS.BIN'] = sha((out / '32RESCUS.BIN').read_bytes())
    for i, (label, info) in enumerate(formats.items()):
        row = info['row']
        data = rcd.encode(row, pack(row, firmware))
        decoded = rcd.decode(data, firmware, ids)
        if tuple(decoded['act']) != tuple(row['act']) or decoded['aspect'] != row['aspect']:
            raise ValueError('RCD decoded geometry differs')
        path = out / 'catalogue' / info['media'] / f'{label}.RCD'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        relative = path.relative_to(out).as_posix()
        hashes[relative] = sha(data)
        if label in labels:
            (selected_dir / path.name).write_bytes(data)
            hashes['RESCUS/' + path.name] = sha(data)
        index.append(dict(label=label, path=relative, bytes=len(data), sha256=sha(data),
                          media=info['media'], ratio=info['ratio'], crop=info['crop'], output=row['act'],
                          source_fps=info['source_fps'], extra_rate_ranks=info['extra_rate_ranks'],
                          donor=row['modes'][0][0], mincore=2 if row['aspect'] == 9 else 1))
        if (i + 1) % 100 == 0:
            print(f'encoded {i + 1}/{len(formats)}', flush=True)
    (out / 'index.json').write_text(json.dumps(dict(commit=doc['commit'], release='R168',
                                                  selected=labels, formats=index), indent=2) + '\n')
    (out / 'SHA256SUMS.txt').write_text(''.join(f'{hashes[p]}  {p}\n' for p in sorted(hashes)))
    print(f'{len(index)} RCD files; selected: {", ".join(labels)}\n{out}')


if __name__ == '__main__':
    main()
