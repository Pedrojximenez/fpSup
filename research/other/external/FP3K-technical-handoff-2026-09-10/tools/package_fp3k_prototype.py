"""Create a deterministic ZIP of the playable prototype; never access camera media."""
from pathlib import Path
import hashlib,json,zipfile
ROOT=Path(__file__).resolve().parents[1];folder=ROOT/'prototype/fp3k-0.1'
m=json.loads((folder/'manifest.json').read_text())
assert hashlib.sha256((folder/'card/AutoRun.txt').read_bytes()).hexdigest()==m['autorun_sha256']=='d2003f2a0af1d845394c5fc3747f1325f8c6b23977159034be4388430df75a59'
assert (folder/'card/AutoRun.txt').read_bytes()==(ROOT/'diagnostics/three-k-f1-no-overlay/card/AutoRun.txt').read_bytes()
files=sorted(p for p in folder.rglob('*') if p.is_file() and not any(x in ('backups','__pycache__') or x.startswith('.') for x in p.relative_to(folder).parts) and p.name!='SHA256SUMS.txt')
(folder/'SHA256SUMS.txt').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.relative_to(folder).as_posix()+'\n' for p in files))
files.append(folder/'SHA256SUMS.txt');dest=ROOT/'prototype/fp3k-0.1.zip'
with zipfile.ZipFile(dest,'w',compression=zipfile.ZIP_DEFLATED) as z:
 for p in sorted(files):
  info=zipfile.ZipInfo('fp3k-0.1/'+p.relative_to(folder).as_posix(),date_time=(2026,9,9,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.create_system=3;info.external_attr=(0o100755 if p.suffix=='.command' else 0o100644)<<16;z.writestr(info,p.read_bytes())
with zipfile.ZipFile(dest) as z:
 assert z.testzip() is None
 for p in files:assert z.read('fp3k-0.1/'+p.relative_to(folder).as_posix())==p.read_bytes()
print(dest);print(dest.stat().st_size,'bytes');print('SHA256',hashlib.sha256(dest.read_bytes()).hexdigest())
