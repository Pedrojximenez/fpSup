import sys,json,subprocess,pathlib
import numpy as np
from PIL import Image,ImageDraw
p=pathlib.Path(sys.argv[1]); n=1024*576*3
proc=subprocess.Popen(['ffmpeg','-v','error','-i',str(p/'hdmi.mkv'),'-fps_mode','passthrough','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],stdout=subprocess.PIPE)
rows=[]; previous=None; still_start=0; runs=[]; images={};old_state=None
while True:
 b=proc.stdout.read(n)
 if not b:break
 assert len(b)==n
 f=np.frombuffer(b,np.uint8).reshape(576,1024,3);i=len(rows)
 r=f[:40,440:650].astype(np.int16)
 red=int(((r[:,:,0]>110)&(r[:,:,1]<85)&(r[:,:,2]<85)).sum())
 green=int(((r[:,:,1]>110)&(r[:,:,0]<85)&(r[:,:,2]<85)).sum())
 state='REC' if red>10 and green<=10 else 'STBY' if green>10 and red<=10 else 'other'
 scene=f[45:520,90:934].copy()
 if previous is not None and not np.array_equal(scene,previous):
  if i-still_start>3:runs.append([still_start,i-1,i-still_start])
  still_start=i
 if state!=old_state or i%150==0:images[i]=Image.fromarray(f.copy())
 rows.append({'frame':i,'state':state,'red':red,'green':green});previous=scene;old_state=state
assert proc.wait()==0
if len(rows)-still_start>3:runs.append([still_start,len(rows)-1,len(rows)-still_start])
spans=[]
for row in rows:
 if not spans or row['state']!=spans[-1]['state']:spans.append({'state':row['state'],'first':row['frame'],'last':row['frame']})
 else:spans[-1]['last']=row['frame']
result={'frames':len(rows),'overlay_spans':spans,'identical_scene_runs':sorted(runs,key=lambda r:r[2],reverse=True),'limitation':'Host HDMI observations only; approximate times use 30 Hz, no native log or SSD readback.'}
(p/'hdmi-review.json').write_text(json.dumps(result,indent=2)+'\n')
sheet=Image.new('RGB',(4*384,((len(images)+3)//4)*240),'#202020');draw=ImageDraw.Draw(sheet)
for k,(i,im) in enumerate(images.items()):
 x=k%4*384;y=k//4*240;sheet.paste(im.resize((384,216)),(x,y));draw.text((x+5,y+218),f'{i} {i/30:.2f}s',fill='white')
 im.save(p/f'frame-{i:04d}.jpg')
sheet.save(p/'contact.jpg');print(json.dumps(result,indent=2))
