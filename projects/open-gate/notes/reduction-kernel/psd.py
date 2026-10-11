import numpy as np
def psd1d(a):
    a=a-a.mean()
    h,w=a.shape
    wy=np.hanning(h)[:,None]; wx=np.hanning(w)[None,:]
    F=np.abs(np.fft.rfft2(a*wy*wx))**2
    # horizontal PSD: average over all ky
    ph=F.mean(axis=0)
    # vertical PSD: need full fft along y
    Fy=np.abs(np.fft.rfft(a*wy*wx,axis=0))**2
    pv=Fy.mean(axis=1)
    return ph/ph[1:].sum(), pv/pv[1:].sum()
def bands(p,nb=8):
    n=len(p)-1
    return [float(p[1+int(i*n/nb):1+int((i+1)*n/nb)].sum()) for i in range(nb)]
