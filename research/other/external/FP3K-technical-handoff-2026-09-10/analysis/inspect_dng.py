"""Read classic TIFF/DNG metadata without changing source files."""
from pathlib import Path
import struct,json
N={256:'ImageWidth',257:'ImageLength',258:'BitsPerSample',259:'Compression',262:'PhotometricInterpretation',271:'Make',272:'Model',273:'StripOffsets',277:'SamplesPerPixel',278:'RowsPerStrip',279:'StripByteCounts',330:'SubIFDs',33421:'CFARepeatPatternDim',33422:'CFAPattern',50706:'DNGVersion',50708:'UniqueCameraModel',50710:'CFAPlaneColor',50713:'BlackLevelRepeatDim',50714:'BlackLevel',50717:'WhiteLevel',50718:'DefaultScale',50719:'DefaultCropOrigin',50720:'DefaultCropSize',50829:'ActiveArea',51044:'FrameRate',305:'Software',33434:'ExposureTime',33437:'FNumber',34855:'ISO',37386:'FocalLength',34665:'ExifIFD',513:'JPEGOffset',514:'JPEGLength'}
S={1:1,2:1,3:2,4:4,5:8,6:1,7:1,8:2,9:4,10:8,11:4,12:8,13:4}
def parse(p):
 b=p.read_bytes(); en='<' if b[:2]==b'II' else '>'; u=lambda f,o:struct.unpack_from(en+f,b,o)
 assert u('H',2)[0]==42
 out=[]; seen=set()
 def walk(off):
  if not off or off in seen:return
  seen.add(off); tags={}; vals={}; n=u('H',off)[0]
  for i in range(n):
   pos=off+2+12*i; tag,t,c=u('HHI',pos); size=S.get(t,1)*c; start=pos+8 if size<=4 else u('I',pos+8)[0]; raw=b[start:start+size]
   if t==2:v=raw.rstrip(b'\0').decode('utf8','replace')
   elif t in (5,10):
    z=struct.unpack(en+('I' if t==5 else 'i')*(c*2),raw);v=[z[j]/z[j+1] if z[j+1] else None for j in range(0,len(z),2)]
   elif t in (1,3,4,6,8,9,11,12,13):v=list(struct.unpack(en+{1:'B',3:'H',4:'I',6:'b',8:'h',9:'i',11:'f',12:'d',13:'I'}[t]*c,raw))
   else:v=raw[:64].hex()
   vals[tag]=v
   if tag in N:tags[N[tag]]=v
  out.append({'offset':off,'tags':tags})
  if 513 in vals and 514 in vals:
   a=vals[513][0]; l=vals[514][0]; Path('analysis/previews/'+p.stem+'.jpg').write_bytes(b[a:a+l])
  for tag in (330,34665):
   for a in vals.get(tag,[]):walk(a)
  walk(u('I',off+2+12*n)[0])
 walk(u('I',4)[0]);return {'file':str(p),'size':len(b),'ifds':out}
if __name__=='__main__':
 files=sorted(Path('samples').rglob('*.DNG')); result=[parse(p) for p in files]
 Path('analysis/sample-metadata.json').write_text(json.dumps(result,indent=2))
 print('DNG files:',len(files))
 for r in (result[0],result[-1]): print(json.dumps(r,indent=2))
