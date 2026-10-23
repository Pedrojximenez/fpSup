"""Offline helpers for the QS footer RE (Ver.5.02). Read-only on out/seg0_c0000000.bin."""
import struct, sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[6]
sys.path.insert(0, str(ROOT / 'research/ui/tools/nbu_probe'))
import nbu_format as NF
IMG = (ROOT / 'out/seg0_c0000000.bin').read_bytes()
BASE = 0xC0000000
POOL_BASE, POOL_LEN = 0xC18C0474, 176152
POOL = IMG[POOL_BASE - BASE:POOL_BASE - BASE + POOL_LEN]
SETS = {'QS_CINE': (0xC2278C02, 0xC239C5FB), 'QS_Common': (0xC239C5FB, 0xC23E1F9C),
        'QS_STILL': (0xC23E1F9C, 0xC24D1DC8), 'QS_STILLlike': (0xC24D1DC8, 0xC261066B)}

def u32(d, o): return struct.unpack_from('>I', d, o)[0]
def s(off): return NF.string_at(POOL, off)
def soff(name):
    i = POOL.find(b'\0' + name.encode() + b'\0')
    return None if i < 0 else i + 1
def records(setname):
    a, b = SETS[setname]
    return a, NF.split(IMG[a - BASE:b - BASE])
def objects(recs):
    out = {}
    for r in recs:
        if r.tag == 0x10003:
            a, b, c, d, parent, name, e = struct.unpack('>7I', r.body)
            out[d] = dict(a=a, b=b, c=c, id=d, parent=parent, name=s(name), e=e, rec=r)
    return out

def clip(r):
    """0x1000A animationClip -> (owner, clip id, [(prop, dim, kind, [(t, v)])])."""
    rec = r.to_bytes()
    cur, props = 28, []
    for _ in range(u32(rec, 12)):
        count, kind, _c, name, dim = struct.unpack_from('>5I', rec, cur)
        keys = []
        for i in range(count):
            t = u32(rec, cur + 22 + 10 * i)
            raw = u32(rec, cur + 26 + 10 * i)
            v = s(raw) if kind == 2 else struct.unpack('>f', struct.pack('>I', raw))[0] if kind == 1 else raw
            keys.append((t, v))
        props.append((s(name), dim, kind, keys))
        cur += 20 + count * 10
    return u32(rec, 20), u32(rec, 24), props, cur

def subtree(ob, root):
    ids = {root}; grew = True
    while grew:
        grew = False
        for k, v in ob.items():
            if v['parent'] in ids and k not in ids: ids.add(k); grew = True
    return ids

def at(keys, t):
    """step value at time t."""
    v = None
    for kt, kv in keys:
        if kt <= t: v = kv
    return v
