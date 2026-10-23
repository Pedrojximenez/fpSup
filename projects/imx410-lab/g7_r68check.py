#!/usr/bin/env python3
# G7 check: run the firmware translation (offline/defect_tables) from the GENERATED R68 row and compare with the hot
# pixels in captures/g7/gen_<key> (g7_probe.py capture).  g7_r68check.py KEY...
# What the firmware would predict for a generated mode from its own R68 row (crop/types/offsets), vs measured.
import sys, json, pathlib, struct
sys.path.insert(0,'.'); sys.path.insert(0,'offline')
import numpy as np, resweep as R, defect_tables as D, g7_probe as G, readout_cfg as C, smc
buf = pathlib.Path('captures/defect/flashbuf.bin').read_bytes()
def cov(meas, pred, rng=60):
    P = np.zeros((max(y for _,y in pred)+400, max(x for x,_ in pred)+400), bool)
    for x,y in pred: P[y+150,x+150]=True
    M=np.array(sorted(meas)); res={}
    for dy in range(-rng,rng+1):
        yy=M[:,0]+dy+150; xx=M[:,1]+8+150
        ok=(yy>=0)&(yy<P.shape[0])&(xx>=0)&(xx<P.shape[1])
        res[dy]=float(P[yy[ok],xx[ok]].mean())
    b=max(res,key=res.get); return res[0], b, res[b]
for name in sys.argv[1:]:
    r=C.BY_KEY[name]; w=max(r['fmt'])
    p=C.plan(name, w*r['mh'] if r['mh']>1 else w, 4040, (w//16)*16, int(4040/r['mv'])//2*2)
    a,rows,how=smc.create(p)
    R68=bytes(rows['R68']); u=lambda o: struct.unpack_from('<I',R68,o)[0]
    tid,flag,crop,types,offs=u(4),u(8),(u(0x10),u(0x14),u(0x18),u(0x1C)),(u(0x20),u(0x24)),(u(0x28),u(0x2C))
    d=pathlib.Path('captures/g7')/('gen_'+name); m=json.loads((d/'meta.json').read_text())
    f2,_=R.decode(d/'dark'); top=m['top']
    meas=G.hot(f2[0][top:,8:-8])&G.hot(f2[1][top:,8:-8])
    src,_=D.table(buf,tid)
    st,_=D.translate(src,crop,types,offs,a['width']+64,a['height']+64)
    print(name,'tab',tid,'flag',flag,'crop',crop,'types',types,'offs',offs,'| cov at dy0, best dy, cov:',cov(meas,D.points(st)))
    # search: crop y and y offset that put the prediction on the measured set with no shift
    best=[]
    for cy in range(0, 160):
        for yo in range(0, 6):
            st,_=D.translate(src,(crop[0],cy,crop[2],crop[3]),types,(offs[0],yo),a['width']+64,a['height']+64)
            pts=D.points(st)
            if not pts: continue
            P=set(pts); hit=sum(((x+8-8, y) in P) for y,x in [(yy,xx+8) for yy,xx in meas])
            best.append((hit/len(meas),cy,yo))
    best.sort(reverse=True); print('  best (cov, crop_y, yo):', best[:6])
