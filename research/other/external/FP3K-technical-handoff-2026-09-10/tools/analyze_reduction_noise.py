"""Exploratory temporal RAW statistics; natural scenes cannot certify a kernel."""
from pathlib import Path
import json, numpy as np
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'analysis/reduction-method';OUT.mkdir(exist_ok=True)
DATA=ROOT/'diagnostics/fullheight-preview-experiment3-return'
def decode(r):
 t=r['ifds'][0]['tags']; w=t['ImageWidth'][0];h=t['ImageLength'][0]
 assert t['Compression']==[1] and t['BitsPerSample']==[12]
 p=Path(r['file']);p=p if p.is_absolute() else ROOT/p
 b=p.read_bytes();a=t['StripOffsets'][0]
 packed=np.frombuffer(b[a:a+w*h*3//2],np.uint8).reshape(-1,3).astype(np.uint16)
 raw=np.empty(w*h,np.uint16);raw[0::2]=(packed[:,0]<<4)|(packed[:,1]>>4);raw[1::2]=((packed[:,1]&15)<<8)|packed[:,2]
 return raw.reshape(h,w)
reports=[]
for clip in ['A001_021','A001_022']:
 rows=json.loads((DATA/'validation'/clip/'frame-metadata.json').read_text())
 # Same even RAW coordinates within each clip, no spatial interpolation.
 frames=[decode(rows[i]) for i in range(10,50)]
 planes=[]
 for py,px in [(0,0),(0,1),(1,0),(1,1)]:
  a=np.stack([f[64+py:-64:2,64+px:-64:2] for f in frames]).astype(np.float32)
  mean=a.mean(0);d=(a[1::2]-a[0::2])/np.sqrt(2)
  tiles=[]
  for y in range(0,a.shape[1]-64,64):
   for x in range(0,a.shape[2]-64,64):
    m=mean[y:y+64,x:x+64];z=d[:,y:y+64,x:x+64]
    drift=z.mean((1,2));z=z-drift[:,None,None]
    var=np.mean(z*z);mx=float(m.mean()-256)
    tiles.append(dict(x=x,y=y,mean=mx,variance=float(var),relative_texture=float(m.std()/max(mx,1)),
      drift_std=float(drift.std()), horizontal_correlation=float(np.mean(z[:,:,:-1]*z[:,:,1:])/max(var,1e-8)),
      vertical_correlation=float(np.mean(z[:,:-1,:]*z[:,1:,:])/max(var,1e-8))))
  keep=[t for t in tiles if t['mean']>15 and t['relative_texture']<.08 and t['drift_std']<1]
  summary={k:float(np.median([t[k] for t in keep])) if keep else None for k in ['mean','variance','horizontal_correlation','vertical_correlation']}
  summary['tile_count']=len(keep)
  phase_sum=np.zeros((16,16),np.float64);phase_count=0
  for t in keep:
   y,x=t['y'],t['x'];z=d[:,y:y+64,x:x+64]
   z=z-z.mean((1,2))[:,None,None]
   var=(z*z).mean(0)/t['mean']
   phase_sum+=var.reshape(4,16,4,16).mean((0,2));phase_count+=1
  phase=phase_sum/max(phase_count,1)
  planes.append(dict(cfa_phase=[py,px],summary=summary,tiles=tiles,
    variance_over_signal_by_phase16=phase.tolist()))
  print(clip,py,px,summary,flush=True)
 reports.append(dict(clip=clip,frames=[11,50],exif=rows[0]['ifds'][1]['tags'],planes=planes))
report=dict(cases=reports,method='Within-clip adjacent-frame difference / sqrt(2), per-tile frame-mean removal; 64x64 same-CFA tiles, no warping or demosaic.',
 limitations=['Exploratory natural scenes, not calibrated flat fields','Motion, flicker and native processing can affect statistics','Does not identify a unique kernel or contributor count'])
(OUT/'existing-clip-noise.json').write_text(json.dumps(report,indent=2)+'\n')
