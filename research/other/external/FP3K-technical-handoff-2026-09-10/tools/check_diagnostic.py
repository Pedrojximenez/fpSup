"""Validate copied FPD001 output and summarize live sensor modes.
Usage: python3 tools/check_diagnostic.py samples/diagnostics/FPD001
No camera access. Source bytes never changed.
"""
from pathlib import Path
import argparse,json,struct,hashlib,sys
ROOT=Path(__file__).resolve().parents[1]
def check(folder, manifest=None):
 m=json.loads((manifest or ROOT/'diagnostics/fp-state-v001/manifest.json').read_text());main=(ROOT/'analysis/firmware/MAIN_c0000000.bin').read_bytes();modes={x['mode_id']:x for x in json.loads((ROOT/'analysis/firmware/sensor-modes.json').read_text())}
 files={p.name.upper():p for p in folder.iterdir() if p.is_file()};errors=[];read={};hashes={}
 for f in m['expected_files']:
  p=files.get(f['name'])
  if p is None:errors.append('Missing '+f['name']);continue
  b=p.read_bytes()
  if len(b)!=f['size']:errors.append(f'{p.name}: expected {f["size"]} bytes, got {len(b)}');continue
  read[f['name']]=b;hashes[f['name']]=hashlib.sha256(b).hexdigest()
 # Stock startup at C0000630 loads the literal at C000076C, then
 # C000063C stores it to C0000020. Check the exact runtime value; do not
 # mask arbitrary vector changes. GEOM remains an immutable fingerprint.
 runtime_prefix=bytearray(main[:64])
 if main[0x630:0x640] != bytes.fromhex('34019fe5000050e30000000a24060fe5'):
  raise ValueError('Unrecognized startup vector initialization')
 runtime_prefix[0x20:0x24]=main[0x76c:0x770]
 expected={'GEOM.BIN':main[0xb59dc0:0xb59dc0+7000], 'DONE.BIN':bytes(runtime_prefix)}
 for fn,want in expected.items():
  if fn in read and read[fn]!=want:errors.append(fn+': stock runtime firmware fingerprint mismatch')
 rows=[]
 for i in range(m['sample_count']):
  s=read.get(f'S{i:03d}.BIN');c=read.get(f'C{i:03d}.BIN');g=read.get(f'G{i:03d}.BIN')
  if s is None:continue
  descriptor,mode,secondary,timing_idx,other_idx=struct.unpack_from('<5I',s)
  if descriptor!=0xC2F1E654:errors.append(f'S{i:03d}: unexpected sensor descriptor 0x{descriptor:08X}')
  r={'sample':i,'sensor_mode':mode,'secondary_mode':secondary,'timing_index':timing_idx,'other_index':other_idx,'sensor_vtable':hex(struct.unpack_from('<I',s,0xd0)[0])}
  r['known_raster']=modes.get(mode,{}).get('raster');r['known_crop']=modes.get(mode,{}).get('output_crop')
  if c:r['record_setting_words_first8']=list(struct.unpack_from('<8I',c))
  if g:r['scratch_geometry']=list(struct.unpack_from('<3I',g))
  rows.append(r)
 return dict(status='PASS' if not errors else 'INCOMPLETE_OR_MISMATCH',errors=errors,samples=rows,file_sha256=hashes,note='Snapshots are sequential, not atomic. Timing is nominal; file writes add latency. A successful diagnostic validates data collection, not open-gate feasibility.')
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('folder',type=Path);ap.add_argument('--output',type=Path);ap.add_argument('--manifest',type=Path);a=ap.parse_args();r=check(a.folder,a.manifest)
 if a.output:a.output.write_text(json.dumps(r,indent=2)+'\n')
 print(r['status'])
 for e in r['errors']:print(e)
 for s in r['samples']:print(f"{s['sample']:02}: mode={s['sensor_mode']} raster={s['known_raster']} crop={s['known_crop']} timing_index={s['timing_index']}")
 sys.exit(bool(r['errors']))
