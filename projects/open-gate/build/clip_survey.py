#!/usr/bin/env python3
"""掃過一張卡/SSD 上的所有 CinemaDNG 片子,列出每段的實際格式。

直接讀檔(卡掛在主機上時),不經過 USB shell。
"""
import struct, sys, os, glob

def tags(path, head=200000):
    d = open(path, 'rb').read(head)
    bo = '<' if d[:2] == b'II' else '>'
    out = {}
    def walk(off, into):
        n = struct.unpack_from(bo + 'H', d, off)[0]
        for i in range(n):
            e = off + 2 + i * 12
            tag, typ, cnt = struct.unpack_from(bo + 'HHI', d, e)
            size = {1:1,2:1,3:2,4:4,5:8,7:1,9:4,10:8,11:4,12:8}.get(typ,1)*cnt
            vo = e + 8 if size <= 4 else struct.unpack_from(bo+'I', d, e+8)[0]
            if typ in (3, 4):
                into[tag] = struct.unpack_from(bo + ('H' if typ==3 else 'I'), d, vo)[0]
            elif typ in (5, 10):
                a, b = struct.unpack_from(bo + ('II' if typ==5 else 'ii'), d, vo)
                into[tag] = (a, b)
            if tag == 34665:
                walk(struct.unpack_from(bo+'I', d, e+8)[0], into)
    walk(struct.unpack_from(bo + 'I', d, 4)[0], out)
    return out

def rat(v):
    return f"{v[0]}/{v[1]}" if isinstance(v, tuple) else str(v)

roots = sys.argv[1:] or ['/Volumes/fpSup/CINEMA']
print(f"{'clip':<12}{'幀數':>5}{'總計':>8}  {'光柵':>10} {'bit':>4} {'每幀':>10} "
      f"{'容器fps':>9} {'快門':>9} {'ISO':>5}  {'MB/s@容器':>10}")
for root in roots:
    for d in sorted(glob.glob(os.path.join(root, 'A*'))):
        if not os.path.isdir(d): continue
        fr = sorted(f for f in glob.glob(os.path.join(d, '*.DNG')) if '-1' not in f)
        total = sum(os.path.getsize(f) for f in fr)
        if not fr:
            print(f"{os.path.basename(d):<12}{0:>5}{'0':>8}   (沒有影格)")
            continue
        try: t = tags(fr[0])
        except Exception as ex:
            print(f"{os.path.basename(d):<12}{len(fr):>5}  解析失敗 {ex}"); continue
        W, H, B = t.get(256), t.get(257), t.get(258)
        strip = t.get(279, 0)
        fps = t.get(51044); fpsv = fps[0]/fps[1] if isinstance(fps, tuple) and fps[1] else 0
        exp = t.get(33434); iso = t.get(34855)
        per = os.path.getsize(fr[0])
        rate = per * fpsv / 1e6 if fpsv else 0
        print(f"{os.path.basename(d):<12}{len(fr):>5}{total/1e6:>7.0f}M  {W:>5}x{H:<4} {B:>4} "
              f"{per:>10,} {fpsv:>9.3f} {rat(exp):>9} {str(iso):>5}  {rate:>10.1f}")
