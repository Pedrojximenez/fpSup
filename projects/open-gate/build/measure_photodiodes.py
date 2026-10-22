#!/usr/bin/env python3
"""每個輸出像素背後有幾顆感光點。

連續兩格相減消掉場景與固定圖案,取最平坦的區塊當雜訊(避開手持位移),
算 sigma^2 / signal。散粒雜訊主導時這個比值正比於 1/k,k 就是該像素
合併了幾顆感光點的光。比值與場景亮度無關,但 ISO 必須相同才能互比。

用法: python3 measure_photodiodes.py <clip 資料夾> [更多資料夾...]
第一個資料夾當作 1.00 的基準。
"""
import numpy as np, glob, subprocess, sys, os
def meta(f):
    o=subprocess.run(['exiftool','-q','-s','-s','-s','-ImageWidth','-ImageHeight','-StripOffsets','-BlackLevel','-ISO','-ExposureTime',f],capture_output=True,text=True).stdout.split('\n')
    return int(o[0]),int(o[1]),int(o[2]),float(o[3].split()[0]),o[4],o[5]
def unp(p,w,h,off):
    row=w*3//2
    b=np.fromfile(p,dtype=np.uint8,count=row*h,offset=off).reshape(h,row)
    b0=b[:,0::3].astype(np.uint16);b1=b[:,1::3].astype(np.uint16);b2=b[:,2::3].astype(np.uint16)
    o=np.empty((h,w),np.uint16);o[:,0::2]=(b0<<4)|(b1>>4);o[:,1::2]=((b1&0xF)<<8)|b2
    return o
print(f"{'clip':<22}{'WxH':>12}{'ISO':>6}{'exp':>7}{'sig':>7}{'noise':>7}{'var/sig':>9}{'photodiodes/px':>16}")
ref=None
for d in sys.argv[1:]:
    fs=sorted(glob.glob(f'{d}/*.DNG'))
    if not fs: continue
    k=len(fs)//2; ims=[]
    for f in (fs[k],fs[k+1]):
        w,h,off,blk,iso,exp=meta(f); ims.append(unp(f,w,h,off).astype(np.float32)-blk)
    ga,gb=ims[0][0::2,1::2],ims[1][0::2,1::2]
    df=gb-ga; B=48; H,W=df.shape; H-=H%B; W-=W%B
    T=lambda x:x[:H,:W].reshape(H//B,B,W//B,B).transpose(0,2,1,3).reshape(-1,B*B)
    bv,bm=T(df).var(1,ddof=1),T(ga).mean(1)
    i=np.argsort(bv)[:max(200,len(bv)//20)]
    S=float(bm[i].mean()); V=float(np.median(bv[i]))/2; sg=np.sqrt(V)
    ratio=V/S
    if ref is None: ref=ratio
    print(f"{os.path.basename(d):<22}{w}x{h:<7}{iso:>6}{exp:>7}{S:>7.2f}{sg:>7.3f}{ratio:>9.3f}{ref/ratio:>16.2f}")
