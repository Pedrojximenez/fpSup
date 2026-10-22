import numpy as np
def blocks(A,n=96,step=64):
    out=[]
    for i in range(0,A.shape[0]-n+1,step):
        for j in range(0,A.shape[1]-n+1,step):
            out.append(A[i:i+n,j:j+n])
    return out
def decompose(REF,X,n=96,step=64):
    """Split X into the part linearly predictable from REF (signal, via a shift-invariant
    filter H(f)) and the incoherent remainder (aliasing + noise)."""
    br=blocks(REF,n,step); bx=blocks(X,n,step)
    w=np.hanning(n)[:,None]*np.hanning(n)[None,:]
    FR=np.stack([np.fft.fft2((b-b.mean())*w) for b in br])
    FX=np.stack([np.fft.fft2((b-b.mean())*w) for b in bx])
    Srr=(np.abs(FR)**2).mean(0); Sxr=(FX*np.conj(FR)).mean(0); Sxx=(np.abs(FX)**2).mean(0)
    H=Sxr/(Srr+1e-12)
    coh=np.abs(Sxr)**2/((Srr+1e-12)*(Sxx+1e-12))
    sig=(np.abs(H)**2*Srr).sum(); incoh=(Sxx*(1-coh)).sum()
    # MTF as a function of |f|
    fy=np.fft.fftfreq(n)[:,None]*np.ones((1,n)); fx=np.ones((n,1))*np.fft.fftfreq(n)[None,:]
    fr=np.sqrt(fy**2+fx**2)
    return dict(sig=float(sig),incoh=float(incoh),H=H,fr=fr,Srr=Srr,Sxx=Sxx,coh=coh)
def mtf_bins(d,edges):
    H=np.abs(d['H']); fr=d['fr']; out=[]
    for a,b in zip(edges[:-1],edges[1:]):
        m=(fr>=a)&(fr<b)
        out.append(float(np.average(H[m],weights=d['Srr'][m])))
    return out
