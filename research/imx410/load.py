import rawpy, numpy as np
D="/Users/dido/Downloads/vs6000x3000/"
F={"fhd":"A001_001_20260916_000001.DNG","og2k":"A001_002_20260916_000001.DNG","still":"SDIM0317.DNG"}
def load(k):
    r=rawpy.imread(D+F[k])
    a=r.raw_image_visible.astype(np.float64)
    bl=np.array(r.black_level_per_channel,dtype=np.float64)
    return a, bl, r
if __name__=="__main__":
    for k in F:
        a,bl,r=load(k)
        print(f"{k:6} shape={a.shape} dtype raw={r.raw_image.shape} black={bl} white={r.white_level} "
              f"pattern={r.raw_pattern.tolist()} mean={a.mean():.1f} min={a.min():.0f} max={a.max():.0f}")
