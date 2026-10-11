"""Build a local-only fast-loader component; not the finished native-menu patch."""
from pathlib import Path
import hashlib,json,struct,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'research/fpSup/fp_usb_shell'))
from armasm import assemble
BASE=0xc072e264
DEST=ROOT/'prototype/development/file-loader'
def build():
    loader=assemble(ROOT/'tools/fp3k_file_loader.S')
    payload=(ROOT/'analysis/firmware/three-k-fullheight.bin').read_bytes()
    assert len(payload)==636 and hashlib.sha256(payload).hexdigest()=='0b36ea8f8e29337c5de10a6edb8bf9727e659bc7d14c1d6c5add62c727c7278e'
    main=(ROOT/'analysis/firmware/MAIN_c0000000.bin').read_bytes()
    assert hashlib.sha256(main).hexdigest()=='aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622'
    assert BASE+len(loader)<0xc072e800
    assert main[BASE-0xc0000000:BASE-0xc0000000+len(loader)]==bytes(len(loader))
    lines=['# Development component only: NOT a native-menu release. No timed sleep.']
    lines += [f'mem set 0x{BASE+4*i:08X} 0x{v:08X}' for i,v in enumerate(struct.unpack('<'+'I'*(len(loader)//4),loader))]
    lines += [f'mem set 0xC0BAC2F8 0x{BASE:08X}','echo','mem set 0xC0BAC2F8 0xC03D99A0']
    DEST.mkdir(parents=True,exist_ok=True)
    (DEST/'AutoRun.txt').write_bytes(('\r\n'.join(lines)+'\r\n').encode('ascii'))
    (DEST/'FP3K.BIN').write_bytes(payload)
    (DEST/'loader.bin').write_bytes(loader)
    m={'status':'OFFLINE DEVELOPMENT ONLY; not installed, no native resolution item yet','loader_bytes':len(loader),'commands':len(lines)-1,'explicit_sleep_ms':0,'loader_sha256':hashlib.sha256(loader).hexdigest(),'payload_sha256':hashlib.sha256(payload).hexdigest(),'limitations':['Camera boot latency and media readiness untested.','Old guarded payload can refuse if acquisition is not idle when the loader runs.','Checksum does not protect the bootstrap itself or provide cryptographic authentication.','Boot-time application is an interim test component, not menu-controlled activation.']}
    (DEST/'manifest.json').write_text(json.dumps(m,indent=2)+'\n')
    return loader,payload,m
if __name__=='__main__':print(json.dumps(build()[2],indent=2))
