"""Validate and summarize FPD003 RAM captures; never accesses the camera."""
import argparse
import hashlib
import json
import struct
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def analyze(raw, profiles):
    if len(raw)!=99904:raise ValueError(f'Expected 99904 bytes, got {len(raw)}')
    header=struct.unpack_from('<16I',raw)
    if header[:4]!=(0x33525046,3,832,120):raise ValueError('Wrong capture header or incomplete sample count')
    if header[7]!=1 or header[8]!=len(raw):raise ValueError('Capture not finalized or length mismatch')
    if not (0x40000000<=header[4]<=0x4ffe0000 and header[5]>=131072):raise ValueError('Invalid allocation descriptor')
    by_id={pid:r for r in profiles['rows'] for pid in r['profile_ids']}
    records=[]
    for i in range(120):
        start=64+i*832
        words=struct.unpack_from('<208I',raw,start)
        if words[0]!=i:raise ValueError(f'Sample {i} sequence mismatch')
        record={'sample':i,'mode_before':words[1],'mode_after':words[2],
                'source_pointer':words[3],'source_pointer_after':words[4],
                'parameter_pointer':words[5],'flags':words[6],
                'recording_flags':list(raw[start+0x30c:start+0x30e])}
        if words[6]&1:
            pid=words[0x1a0//4];param=words[0x200//4:0x30c//4]
            record.update(profile_id=pid,raw_dimensions=[param[0xdc//4] or param[0],param[0xe4//4] or param[1]],
                          crop=[param[0x24//4],param[0x2c//4]],zoom=[param[0x64//4],param[0xd4//4]])
            if pid in by_id:
                stock=by_id[pid]['words']+[6064,4042]
                record['stock_differences']=[{'offset':hex(j*4),'stock':a,'live':v} for j,(a,v) in enumerate(zip(stock,param)) if a!=v]
            else:record['unknown_profile']=True
        records.append(record)
    return {'sha256':hashlib.sha256(raw).hexdigest(),'count':120,'nominal_interval_ms':header[6],
            'sensor_modes':sorted({r['mode_before'] for r in records}),
            'profile_ids':sorted({r['profile_id'] for r in records if 'profile_id' in r}),
            'copied_profiles':sum(bool(r['flags']&1) for r in records),
            'changed_state_records':sum(bool(r['flags']&6) for r in records),
            'records':records,'limitations':'RAM snapshots are not atomic. Nominal spacing excludes execution and scheduler delay.'}

def analyze_folder(folder, profiles, expected):
    # Numbering is per basename: after an incomplete boot, equal suffixes do
    # not establish that files belong to the same run. Require clean media.
    names = [p.name for p in folder.iterdir() if p.is_file() and
             re.fullmatch(r'(STATE|POOL|LOADED)\d*\.BIN', p.name, re.I)]
    required = {'STATE.BIN', 'POOL.BIN', 'LOADED.BIN'}
    if set(names) != required:
        raise ValueError('Incomplete or ambiguous run: expected only STATE.BIN, POOL.BIN, '
                         'LOADED.BIN. Numbered files cannot safely be paired after an '
                         f'incomplete run. Found: {sorted(names)}')
    raw = (folder/'STATE.BIN').read_bytes()
    pool = (folder/'POOL.BIN').read_bytes()
    if len(pool) != 12:
        raise ValueError('Allocation readback must contain 12 bytes')
    report = analyze(raw, profiles)
    if struct.unpack('<3I', pool) != (*struct.unpack_from('<2I', raw, 16), 0):
        raise ValueError('Allocation readback does not match capture header/type')
    if (folder/'LOADED.BIN').read_bytes() != expected:
        raise ValueError('Loaded code differs from the locally verified payload')
    report['loaded_code_exact_match'] = True
    report['allocation_readback_matches'] = True
    report['provenance_note'] = 'File contents do not prove boot identity; use empty output folders for each run.'
    return report

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('folder',type=Path);ap.add_argument('--output',type=Path);args=ap.parse_args()
    profiles=json.loads((ROOT/'analysis/firmware/raw-profiles.json').read_text())
    expected=(ROOT/'analysis/firmware/raw-capture.bin').read_bytes()
    report=analyze_folder(args.folder,profiles,expected)
    if args.output:args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='records'},indent=2))
