"""Read bounded stock XCI LZ4-block assets without changing firmware."""
import struct,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def block(data):
 out=bytearray();p=0
 while p<len(data):
  token=data[p];p+=1;lit=token>>4
  if lit==15:
   while True:
    x=data[p];p+=1;lit+=x
    if x!=255:break
  assert p+lit<=len(data);out+=data[p:p+lit];p+=lit
  if p==len(data):break
  offset=int.from_bytes(data[p:p+2],'little');p+=2;assert 0<offset<=len(out)
  n=(token&15)+4
  if token&15==15:
   while True:
    x=data[p];p+=1;n+=x
    if x!=255:break
  assert len(out)+n<10000000
  for _ in range(n):out.append(out[-offset])
 return bytes(out)
def decode(data):
 assert data[:4]==b'XC\0\0' and struct.unpack_from('<I',data,4)[0]+32==len(data)
 w,h=struct.unpack_from('<HH',data,8);assert data[32:36]==bytes.fromhex('04224d18')
 n=struct.unpack_from('<I',data,47)[0];assert 51+n+4==len(data) and data[-4:]==bytes(4)
 raw=block(data[51:51+n]);return w,h,raw
if __name__=='__main__':
 main=(ROOT/'analysis/firmware/MAIN_c0000000.bin').read_bytes();count=struct.unpack_from('>I',main,0xd4d9b8)[0];rows=[]
 for i in range(count):
  p=0xd4d9bc+i*16;_,name,offset,size=struct.unpack_from('>4I',main,p)
  q=0xd22414+name;end=main.index(0,q);name=main[q:end].decode()
  if any(s in name for s in ['qs_resolution','set_resolution','M_resolution','L_resolution','font_menu_MB_resolution']):
   a=0xd22400+offset;data=main[a:a+size]
   if data[:2]!=b"XC":continue
   w,h,raw=decode(data)
   stem=Path(name).stem;(ROOT/'analysis/firmware/ui-assets'/f'{stem}.raw').write_bytes(raw)
   rows.append(dict(name=name,address=hex(0xc0000000+a),descriptor=hex(0xc0000000+p),width=w,height=h,raw_bytes=len(raw),bytes_per_pixel=len(raw)/(w*h),header=data[:32].hex(),decoded_file=stem+'.raw'))
 (ROOT/'analysis/firmware/ui-assets/index.json').write_text(json.dumps(rows,indent=2)+'\n')
 print(json.dumps(rows,indent=2))
