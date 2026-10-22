import struct, sys

TYPESZ={1:1,2:1,3:2,4:4,5:8,6:1,7:1,8:2,9:4,10:8,11:4,12:8}

def read_ifd(d, off, end):
    n = end('H', d, off)[0]; off += 2
    tags = {}
    for i in range(n):
        tag, typ, cnt = end('HHI', d, off)[:3]
        vo = off + 8
        sz = TYPESZ.get(typ,1)*cnt
        if sz > 4:
            vo = end('I', d, off+8)[0]
        vals = []
        fmt = {1:'B',2:'B',3:'H',4:'I',6:'b',7:'B',8:'h',9:'i',11:'f',12:'d'}.get(typ)
        if typ == 5 or typ == 10:
            for k in range(cnt):
                a,b = end('II' if typ==5 else 'ii', d, vo+8*k)
                vals.append((a,b))
        elif fmt:
            for k in range(cnt):
                vals.append(end(fmt, d, vo+TYPESZ[typ]*k)[0])
        tags[tag] = (typ, cnt, vals, vo)
        off += 12
    nxt = end('I', d, off)[0]
    return tags, nxt

def parse(path):
    d = open(path,'rb').read()
    bo = d[:2]
    e = '<' if bo == b'II' else '>'
    def end(fmt, buf, off):
        return struct.unpack_from(e+fmt, buf, off)
    magic, off0 = end('HI', d, 2)
    ifds = []
    off = off0
    while off:
        t, off = read_ifd(d, off, end)
        ifds.append(t)
    return d, e, end, ifds
