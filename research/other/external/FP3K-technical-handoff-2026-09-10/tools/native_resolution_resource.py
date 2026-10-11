"""Exact-size native B2_5_4 resolution-list candidate. Does not install."""
from pathlib import Path
import struct,hashlib,json
ROOT=Path(__file__).resolve().parents[1]
RESOURCE=0xc0f8e7ec
DESCRIPTOR=0xc0d4ddfc
SIZE=89
CSV=b'\xef\xbb\xbfNO,TEXT,IMAGE,Enabled,Enabled2\r\n1,0313,blank,1,2\n2,0314,blank,1,2\n3,3K 3000x2000,,1,2\n'
assert len(CSV)==SIZE

def stock():
 b=(ROOT/'analysis/firmware/MAIN_c0000000.bin').read_bytes()
 assert hashlib.sha256(b).hexdigest()=='aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622'
 key,name,offset,size=struct.unpack_from('>4I',b,DESCRIPTOR-0xc0000000)
 assert (key,name,offset,size)==(0x0780ae3b,0xe3c,0x26c3ec,SIZE)
 filename=b[0xd22414+name:].split(b'\0',1)[0]
 assert filename==b'../MenuB12/data/ListB12/B2_5_4.cvm'
 old=b[RESOURCE-0xc0000000:RESOURCE-0xc0000000+SIZE]
 assert old==b'\xef\xbb\xbfNO,TEXT,Popup,IMAGE,Enabled,Enabled2\r\n1,0313,Popup,blank,1,2\r\n2,0314,Popup,blank,1,2\r\n'
 return b,old
if __name__=='__main__':
 b,old=stock();out=ROOT/'prototype/development/native-menu';out.mkdir(parents=True,exist_ok=True)
 (out/'B2_5_4.cvm').write_bytes(CSV)
 (out/'resource-plan.json').write_text(json.dumps(dict(status='Integrated offline candidate; selection hook built; camera rendering and operation pending',address=hex(RESOURCE),bytes=SIZE,old_sha256=hashlib.sha256(old).hexdigest(),new_sha256=hashlib.sha256(CSV).hexdigest(),change='Keep UHD and FHD localization keys. Add third row 3K 3000x2000. Omit unused Popup column; use compact separators and an empty image field on the literal 3K row.'),indent=2)+'\n')
 print('Exact-size 89-byte native resolution-list candidate written.')
