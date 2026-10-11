import struct

class Bits:
    def __init__(self, d, p):
        self.d=d; self.p=p; self.b=0; self.n=0
    def get(self, k):
        v=0
        for _ in range(k):
            if self.n==0:
                c=self.d[self.p]; self.p+=1
                if c==0xFF:
                    nx=self.d[self.p]
                    if nx==0x00: self.p+=1
                    else: c=0xFF  # marker; caller should stop
                self.b=c; self.n=8
            v=(v<<1)|((self.b>>7)&1)
            self.b=(self.b<<1)&0xFF; self.n-=1
        return v

def build_huff(counts, symbols):
    code=0; k=0; lut={}
    for l in range(1,17):
        for _ in range(counts[l-1]):
            lut[(l,code)]=symbols[k]; k+=1; code+=1
        code<<=1
    return lut

def decode_tile(blob):
    i=2; huff={}; sof=None; sos=None
    while i < len(blob)-1:
        m=blob[i+1]; L=struct.unpack_from('>H',blob,i+2)[0]; seg=blob[i+4:i+2+L]
        if m==0xC3: sof=seg
        elif m==0xC4:
            p=0
            while p<len(seg):
                tcth=seg[p]; counts=list(seg[p+1:p+17]); ns=sum(counts)
                syms=list(seg[p+17:p+17+ns])
                huff[tcth&15]=build_huff(counts,syms)
                p+=17+ns
        elif m==0xDA:
            sos=seg; i=i+2+L; break
        i+=2+L
    P=sof[0]; Y,X=struct.unpack_from('>HH',sof,1); Nf=sof[5]
    Ns=sos[0]; tsel=[(sos[1+2*c], sos[2+2*c]>>4) for c in range(Ns)]
    Ss=sos[1+2*Ns]
    br=Bits(blob,i)
    out=[[0]*(X*Nf) for _ in range(Y)]
    prev=None
    for y in range(Y):
        row=out[y]
        for x in range(X):
            for c in range(Nf):
                tbl=huff[tsel[c][1]]
                code=0; l=0; s=None
                while l<16:
                    code=(code<<1)|br.get(1); l+=1
                    if (l,code) in tbl: s=tbl[(l,code)]; break
                if s is None: raise ValueError("bad huff")
                if s==0: diff=0
                elif s==16: diff=32768
                else:
                    v=br.get(s)
                    diff = v if v >= (1<<(s-1)) else v-(1<<s)+1
                if y==0 and x==0:
                    pred=1<<(P-1)
                elif y==0:
                    pred=row[(x-1)*Nf+c]
                elif x==0:
                    pred=out[y-1][c]
                else:
                    ra=row[(x-1)*Nf+c]
                    rb=out[y-1][x*Nf+c]
                    rc=out[y-1][(x-1)*Nf+c]
                    pred={1:ra, 2:rb, 3:rc, 4:ra+rb-rc,
                          5:ra+((rb-rc)>>1), 6:rb+((ra-rc)>>1),
                          7:(ra+rb)>>1}[Ss]
                row[x*Nf+c]=(pred+diff)&0xFFFF
    return P,X,Y,Nf,out
