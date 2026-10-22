"""Validate captured DNG structure and render sampled RAW green planes."""
from pathlib import Path
import sys,json,argparse,wave,hashlib
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'analysis'))
from inspect_dng import parse
import numpy as np
from PIL import Image,ImageDraw
p=argparse.ArgumentParser();p.add_argument('clip',type=Path);p.add_argument('output',type=Path);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
files=sorted(a.clip.glob('*.DNG'));assert files,'No DNG frames'
rows=[];errors=[];numbers=[]
expected={'ImageWidth':[3032],'ImageLength':[2020],'BitsPerSample':[12],'Compression':[1],'DefaultCropOrigin':[16,10],'DefaultCropSize':[3000,2000],'FrameRate':[24.0]}
for f in files:
 r=parse(f);t=r['ifds'][0]['tags'];rows.append(r);numbers.append(int(f.stem.rsplit('_',1)[1]))
 for k,v in expected.items():
  if t.get(k)!=v:errors.append(f'{f.name}: {k}={t.get(k)} expected {v}')
 for off,count in zip(t['StripOffsets'],t['StripByteCounts']):
  if off+count>r['size']:errors.append(f'{f.name}: truncated strip')
 if sum(t['StripByteCounts'])<3032*2020*12//8:errors.append(f'{f.name}: undersized RAW strip')
consecutive=numbers==list(range(1,len(files)+1))
if not consecutive:errors.append('Frame numbering is not consecutive from 1')
indices=sorted(set(round(i*(len(files)-1)/8) for i in range(9)))
panel=Image.new('RGB',(1500,1065),'#161616');draw=ImageDraw.Draw(panel);stats=[]
for j,i in enumerate(indices):
 r=rows[i];t=r['ifds'][0]['tags'];b=files[i].read_bytes();off=t['StripOffsets'][0];packed=np.frombuffer(b[off:off+3032*2020*3//2],np.uint8).reshape(-1,3).astype(np.uint16);raw=np.empty(3032*2020,np.uint16);raw[::2]=(packed[:,0]<<4)|(packed[:,1]>>4);raw[1::2]=((packed[:,1]&15)<<8)|packed[:,2];raw=raw.reshape(2020,3032)[10:2010,16:3016]
 g=np.maximum((raw[::2,1::2].astype(np.float32)+raw[1::2,::2])/2-256,0);g=(np.clip(g/max(float(np.percentile(g,99.5)),1),0,1)**(1/2.2)*255).astype(np.uint8)
 x=(j%3)*500;y=(j//3)*355;panel.paste(Image.fromarray(g).convert('RGB').resize((500,333)),(x,y+22));draw.text((x+8,y+5),f'Frame {i+1} / {i/24:.2f}s',fill='white');stats.append({'frame':i+1,'raw_min':int(raw.min()),'raw_max':int(raw.max()),'zero_fraction':float(np.mean(raw==0)),'raw_sha256':hashlib.sha256(raw.tobytes()).hexdigest()})
panel.save(a.output/'contact-sheet.jpg',quality=90)
audio=[]
for f in a.clip.glob('*.WAV'):
 with wave.open(str(f),'rb') as w:audio.append({'file':f.name,'seconds':w.getnframes()/w.getframerate(),'sample_rate':w.getframerate()})
report={'frames':len(files),'fps':24,'seconds_at_metadata_fps':len(files)/24,'consecutive_numbering':consecutive,'expected_format':expected,'errors':errors,'audio':audio,'sampled_raw_statistics':stats,'limitations':'Contiguous file numbering does not prove sensor cadence or exclude duplicated frames; metadata and sparse previews do not certify all-photosite sampling or image quality.'}
(a.output/'frame-metadata.json').write_text(json.dumps(rows,indent=2));(a.output/'clip-validation.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
