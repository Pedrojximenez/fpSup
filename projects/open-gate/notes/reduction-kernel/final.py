exec(open('cand.py').read())
import numpy as np
REG=[('weave',(560,1560,900,2100),48),('edges',(470,640,950,2050),16),
     ('frame',(60,440,720,1130),32),('chair',(1040,1420,60,660),32),
     ('wood',(1500,1990,450,2550),48)]
def nef(fn,reps=6):
    rng=np.random.default_rng(0); v=[]
    for r in range(reps):
        A=rng.standard_normal((300,300)); X,_,_=fn(A,0); v.append(np.var(X[8:-8,8:-8]))
    return 1/np.mean(v)
def run(lbl,fn,rat):
    row=[]
    for nm,(y0,y1,x0,x1),n in REG:
        sub=I[y0:y1,x0:x1]; v=[]
        for ph in range(6):
            X,cy,cx=fn(sub,ph); Rf=samp(sub,cy,cx,lambda x:lanczos(x,3,rat),3*rat+2); m=2
            d=decompose(Rf[m:-m,m:-m],X[m:-m,m:-m],n=n,step=max(n//2,8))
            v.append(100*d['incoh']/d['sig'])
        row.append(np.median(v))
    ne=nef(fn); ordn=np.mean(row[1:])
    print(f'{lbl:24s}{row[0]:7.1f}{ordn:8.1f}   |'+''.join(f'{a:7.1f}' for a in row[1:])
          +f'  | {ne:6.2f}  x{1/np.sqrt(ne):.2f}')
    return row,ne
R=25/16.
ROUTES=[('OG3K sensor /2',bin2,2.0),('  ideal 2x2',idbox(2),2.0),
   ('OG4K full+RWZM 3/2',direct(1.5),1.5),('UHD full+RWZM 25/16',direct(R),R),
   ('3K full+RWZM 2',direct(2.0),2.0),('2K /2+RWZM 3/2',after2(1.5),3.0),
   ('FHD /2+RWZM 25/16',after2(R),2*R),('OG2K sensor /3',bin3,3.0),
   ('  ideal 3x3',idbox(3),3.0),('2K full+RWZM 3',direct(3.0),3.0)]
