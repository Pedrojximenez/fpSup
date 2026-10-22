"""Standby-only inventory and exact-byte backups of the loaded optional sups.

Uses maintained, tagged file reads. Does not change module settings or hooks.
The bounded header-owner read is independent of the optional-sup inventory.
"""
import fcntl, hashlib, importlib, json, re, sys
import camera as C
import native_rec_trace as N

def main():
    dest=C.HERE/'optional-modules-inspection'
    dest.mkdir()
    with open('/tmp/fp-af-fusion.lock') as lease:
        fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
        N.idle(dest)
        report={'files':{},'header_owner':C.live.putfile.mem_get(0xC358DB98,5,tries=1),
                'header_call_word':hex(C.live.putfile.mem_get(0xC038C77C,tries=1)[0])}
        listing=C.live.checked_sh('dir \\fpSup')
        report['listing']=listing
        getter=importlib.import_module('getfile')
        getter.read_direct=lambda a,n:C.live.putfile.read_bulk(a,n,'tagged')
        for name in ('LOAD.LOG','10LOSS.BIN','20GYR2.BIN','LOADER.BIN'):
            m=re.search(r'(\d+)\s+'+re.escape(name)+r'\s*$',listing,re.M)
            assert m,name
            size=int(m[1]);assert 0<size<=100000
            assert C.recording()==0
            local=dest/name
            sys.argv=['getfile.py','\\fpSup\\'+name,str(local),'--size',str(size)]
            assert getter.main()==0
            data=local.read_bytes();assert len(data)==size
            report['files'][name]={'bytes':size,'sha256':hashlib.sha256(data).hexdigest()}
            (dest/'inspection.json').write_text(json.dumps(report,indent=2)+'\n')
        assert C.recording()==0
        print(json.dumps(report,indent=2),flush=True)

if __name__=='__main__':main()
