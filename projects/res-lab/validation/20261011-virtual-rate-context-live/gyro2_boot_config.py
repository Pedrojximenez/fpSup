"""Temporary Gyro2 next-boot setting using the existing SupManager FSDS record.

Only its documented disabled-list data changes. Full loader program/envelope
bytes stay exact, as do existing disabled ids. No sup rename, deletion or hook
replacement. Requires native and HDMI standby; full file readbacks both ways.
"""
import fcntl, hashlib, importlib, json, re, struct, sys
import camera as C
import native_rec_trace as N

BACKUP=C.HERE/'optional-modules-inspection/LOADER.BIN'
EXPECTED='7b78041d80ddf9a74f751c4d38366a5ae8fa4184ff5d41494f2f345d7d25d95b'

def blobs():
    old=BACKUP.read_bytes()
    assert hashlib.sha256(old).hexdigest()==EXPECTED and len(old)==29276
    off=len(old)-128
    assert struct.unpack_from('<II',old,off)==(0x53445346,1)
    assert old[off+8:off+12]==b'LOSS' and old[off+12:]==bytes(116)
    new=bytearray(old)
    struct.pack_into('<I',new,off+4,2)
    new[off+12:off+16]=b'GYR2'
    assert new[:off+4]==old[:off+4] and new[off+16:]==old[off+16:]
    return old,bytes(new)

def main():
    action=sys.argv[1];assert action in ('disable','restore')
    tag=sys.argv[2] if len(sys.argv)>2 else action
    assert tag.startswith(action) and all(c.islower() or c.isdigit() or c=='-' for c in tag)
    dest=C.HERE/('gyro2-config-'+tag);dest.mkdir()
    old,new=blobs();expected,want=(old,new) if action=='disable' else (new,old)
    proof={'action':action,'phase':'preflight','program_bytes_changed':False,
           'original_sha256':EXPECTED,'target_sha256':hashlib.sha256(want).hexdigest()}
    def save():(dest/'config.json').write_text(json.dumps(proof,indent=2)+'\n')
    with open('/tmp/fp-af-fusion.lock') as lease:
        fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
        N.idle(dest)
        getter=importlib.import_module('getfile')
        getter.read_direct=lambda a,n:C.live.putfile.read_bulk(a,n,'tagged')
        def fetch(name):
            assert C.recording()==0
            path=dest/name;assert not path.exists()
            listing=C.live.checked_sh('dir \\fpSup')
            assert re.search(r'\b29276\s+LOADER\.BIN\s*$',listing,re.M)
            sys.argv=['getfile.py','\\fpSup\\LOADER.BIN',str(path),'--size','29276']
            assert getter.main()==0
            return path.read_bytes()
        got=fetch('before-LOADER.BIN')
        assert got==expected,'Unknown module settings; stop without a write'
        prepared=dest/'prepared-LOADER.BIN';prepared.write_bytes(want)
        proof['phase']='exact_before_verified';save()
        assert C.recording()==0
        sys.argv=['putfile.py',str(prepared),'\\fpSup\\LOADER.BIN']
        assert importlib.import_module('putfile').main()==0
        proof['phase']='written';save()
        assert fetch('after-LOADER.BIN')==want
        proof['phase']='verified';save()
        print(json.dumps(proof,indent=2),flush=True)

if __name__=='__main__':main()
