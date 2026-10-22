import numpy as np, struct, heapq
from collections import Counter
from tiff import parse

def load_uncompressed(path):
    d,e,end,ifds=parse(path)
    t=ifds[0]
    W=t[256][2][0]; H=t[257][2][0]; bps=t[258][2][0]
    assert t[259][2][0]==1
    off=t[273][2][0]; n=t[279][2][0]
    raw=np.frombuffer(d,dtype=np.uint8,count=n,offset=off)
    assert bps==12 and n>=W*H*3//2, (bps,n,W*H*3//2)
    raw=raw[:W*H*3//2]
    b=raw.reshape(-1,3).astype(np.uint16)
    hi=(b[:,0]<<4)|(b[:,1]>>4)
    lo=((b[:,1]&0xF)<<8)|b[:,2]
    px=np.empty(W*H,dtype=np.uint16)
    px[0::2]=hi; px[1::2]=lo
    return px.reshape(H,W), W, H, bps

def ssss_map(diff):
    a=np.abs(diff).astype(np.int32)
    s=np.zeros_like(a)
    nz=a>0
    s[nz]=np.floor(np.log2(a[nz])).astype(np.int32)+1
    return s

def huff_bits(counts):
    """optimal huffman total bits for a symbol->count dict"""
    items=[(c,i,[s]) for i,(s,c) in enumerate(counts.items()) if c>0]
    if not items: return 0,{}
    lens={s:0 for s in counts}
    if len(items)==1:
        lens[items[0][2][0]]=1
        return sum(counts[s]*lens[s] for s in lens), lens
    h=list(items); heapq.heapify(h); nid=len(h)
    while len(h)>1:
        c1,_,s1=heapq.heappop(h); c2,_,s2=heapq.heappop(h)
        for s in s1+s2: lens[s]+=1
        heapq.heappush(h,(c1+c2,nid,s1+s2)); nid+=1
    return sum(counts[s]*lens[s] for s in lens), lens

def tile_cost(tile, P, predictor=1):
    """tile: 2-D uint16 array (tileH, tileW) of CFA samples. Returns bytes."""
    if predictor not in range(1, 8):
        raise ValueError("lossless JPEG predictor 必須是 1..7")
    th,tw=tile.shape
    total_bits=0
    for c in range(2):                      # deinterleave columns -> 2 components
        comp=tile[:,c::2].astype(np.int32)
        pred=np.empty_like(comp)
        pred[0,1:]=comp[0,:-1]              # 第一列一律用 Ra
        pred[1:,0]=comp[:-1,0]              # Rb at line start
        pred[0,0]=1<<(P-1)
        if comp.shape[0]>1 and comp.shape[1]>1:
            ra=comp[1:,:-1]; rb=comp[:-1,1:]; rc=comp[:-1,:-1]
            pred[1:,1:]={1:ra,2:rb,3:rc,4:ra+rb-rc,
                         5:ra+((rb-rc)>>1),6:rb+((ra-rc)>>1),
                         7:(ra+rb)>>1}[predictor]
        diff=comp-pred
        diff=((diff+0x8000)&0xFFFF)-0x8000
        s=ssss_map(diff)
        cnt=Counter(s.ravel().tolist())
        bits,_=huff_bits(cnt)
        extra=int(sum(k*v for k,v in cnt.items() if k!=16))
        total_bits+=bits+extra
    return 96 + (total_bits+7)//8           # ~96 B marker overhead per tile

def frame_cost(img, P, tw, th, predictor=1):
    H,W=img.shape
    tot=0; n=0
    for y in range(0,H,th):
        for x in range(0,W,tw):
            t=img[y:y+th, x:x+tw]
            if t.shape[1]%2: t=t[:,:-1]
            tot+=tile_cost(t,P,predictor); n+=1
    return tot,n
