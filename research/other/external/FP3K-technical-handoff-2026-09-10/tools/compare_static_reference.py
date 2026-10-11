"""Exploratory scene registration, not a calibrated field-of-view certification."""
from pathlib import Path
import sys,json,argparse
sys.path.insert(0,'/tmp/fp-f1-vision')
import cv2,numpy as np,rawpy
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--still',default='SDIM0166.DNG');args=p.parse_args()
DATA=ROOT/'diagnostics/three-k-static-return';OUT=DATA/('registration-'+Path(args.still).stem);OUT.mkdir(exist_ok=True)
rows=json.loads((DATA/'frame-metadata.json').read_text())
with rawpy.imread(str(DATA/'reference-still'/args.still)) as decoded:
 a=np.maximum(decoded.raw_image.astype(np.float32)[21:4021,32:6032]-1024,0)
 # The odd crop origin swaps the Bayer row phase: these are the two greens.
 green=(a[0::2,0::2]+a[1::2,1::2])/2
 sg=cv2.resize((np.clip(green/max(np.percentile(green,99.5),1),0,1)**(1/2.2)*255).astype(np.uint8),(1500,1000),interpolation=cv2.INTER_AREA)
still=cv2.cvtColor(sg,cv2.COLOR_GRAY2BGR)
sift=cv2.SIFT_create(nfeatures=5000);ks,ds=sift.detectAndCompute(sg,None);bf=cv2.BFMatcher();reports=[];best=None
for ix in range(0,len(rows),10):
 r=rows[ix];t=r['ifds'][0]['tags'];w=t['ImageWidth'][0];h=t['ImageLength'][0];a=t['StripOffsets'][0];b=Path(r['file']).read_bytes();p=np.frombuffer(b[a:a+w*h*3//2],np.uint8).reshape(-1,3).astype(np.uint16);raw=np.empty(w*h,np.uint16);raw[0::2]=(p[:,0]<<4)|(p[:,1]>>4);raw[1::2]=((p[:,1]&15)<<8)|p[:,2];raw=raw.reshape(h,w).astype(np.float32)[10:2010,16:3016];g=np.maximum((raw[0::2,1::2]+raw[1::2,0::2])/2-256,0);g=(np.clip(g/max(np.percentile(g,99.5),1),0,1)**(1/2.2)*255).astype(np.uint8)
 kv,dv=sift.detectAndCompute(g,None);pairs=bf.knnMatch(dv,ds,k=2);good=[m for m,n in pairs if m.distance<.7*n.distance]
 if len(good)<10:continue
 x=np.float32([kv[m.queryIdx].pt for m in good]);y=np.float32([ks[m.trainIdx].pt for m in good]);H,mask=cv2.findHomography(x,y,cv2.RANSAC,3)
 if H is None:continue
 keep=mask.ravel().astype(bool);pred=cv2.perspectiveTransform(x[:,None,:],H)[:,0];err=np.linalg.norm(pred-y,axis=1)
 # Local scale at the median actual matched point, not extrapolated center.
 pt=np.median(x[keep],axis=0);tri=np.float32([pt,pt+[1,0],pt+[0,1]])
 q=cv2.perspectiveTransform(tri[:,None,:],H)[:,0];J=np.stack([q[1]-q[0],q[2]-q[0]],axis=1);scales=np.linalg.svd(J,compute_uv=False)
 rec=dict(frame=ix+1,matches=len(good),inliers=int(keep.sum()),median_error=float(np.median(err[keep])),matched_video_points=x[keep].tolist(),matched_still_points=y[keep].tolist(),local_scales=scales.tolist(),H_video_to_still=H.tolist(),inlier_video_bounds=[x[keep].min(0).tolist(),x[keep].max(0).tolist()]);reports.append(rec)
 if best is None or rec['inliers']>best[0]['inliers']:best=(rec,g,x,y,keep)
(OUT/'registration.json').write_text(json.dumps(dict(method='SIFT/RANSAC homography on independently scaled1500x1000 full visible crops; actual RAW green planes for still and video',limitation='Handheld pose, camera translation, parallax and focus breathing can affect apparent scale. A homography is not proof of sensor coverage.',frames=reports),indent=2)+'\n')
rec,g,x,y,keep=best;print(json.dumps(rec,indent=2));panel=Image.new('RGB',(1500,530),'#151515');panel.paste(Image.fromarray(cv2.cvtColor(still,cv2.COLOR_BGR2RGB)).resize((750,500)),(0,30));panel.paste(Image.fromarray(g).convert('RGB').resize((750,500)),(750,30));d=ImageDraw.Draw(panel);d.text((10,8),'Stock still: full image (RAW green plane)',fill='white');d.text((760,8),f'F1 video: full image, frame {rec["frame"]} (RAW green plane)',fill='white');panel.save(OUT/'comparison.jpg');Image.fromarray(g).save(OUT/'video-green.png');Image.fromarray(sg).save(OUT/'still-green.png')
