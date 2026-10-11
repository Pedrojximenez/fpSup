"""Load an NBR pack with TWO state machines through the stock interpreter (records 0x5000x run the
real builders, and the real FUN_c05de938 push_back onto app+0xF4), then call the real
FUN_c05ed028(app, cur, 0, req, &out, 0) -- the matcher FUN_c05dd448 uses -- and report the target.
Machine order in the pack = order on app+0xF4.  Run twice with the order swapped."""
import struct, sys
from pathlib import Path
ROOT = Path('/Users/dido/Developer.localized/SIGMAfp_re')
sys.path[:0] = [str(ROOT/'projects/open-gate/build'), str(ROOT/'research/ui/tools'), str(ROOT/'research/ui/tools/nbu_probe')]
import sl_pages as SL, nbr as NBR, nbu_probe as P

STOCK = ('StockLike', [('MainY5','MainB1','Menu01'), ('MainB1','MainY5','Menu13'), ('MainY5','MainY4','Menu12')])
PRIV  = ('Private',   [('MainY5','MainY6','Menu01'), ('MainB1','MainY6','Menu13'), ('MainY6','MainB1','Menu01'),
                       ('MainY6','MainY5','Menu13'), ('MainY5','MainY6','Menu14')])

def pack(machines):
    pool = bytearray(4); offs = {}
    def intern(s):
        if s not in offs:
            offs[s] = len(pool); pool.extend(s.encode()+b'\0'); pool.extend(bytes(-len(pool) % 4))
        return offs[s]
    intern(SL.INDEX_NAME)
    sm = struct.pack('>III', 0x50001, 12, len(machines))
    for name, trans in machines:
        states = []
        for a, b, _ in trans:
            for s in (a, b):
                if s not in states: states.append(s)
        for t in [name] + states + [e for *_, e in trans]: intern(t)
        sm += struct.pack('>II9I', 0x50002, 44, len(states), 0,0,0,0,0,0, len(trans), offs[name])
        for s in states: sm += struct.pack('>II3I', 0x50003, 20, offs[s], 0, 0)
        for a, b, e in trans: sm += struct.pack('>II4I', 0x50004, 24, offs[a], offs[b], offs[e], 0)
    # one dummy page row (as sl_pages.build_pack), so the index is the stock shape
    img = (ROOT/'out/MAIN_c0000000.bin').read_bytes()
    pname, page, _ = SL.test_pages(img)[0]; intern(pname)
    head = b'NBR\0' + struct.pack('>II', SL.VERSION, 0)
    pool_rec = struct.pack('>II', 1, 8+len(pool)) + pool
    index_len = 8 + 8 + 32
    at = len(head) + len(pool_rec) + index_len + len(sm) + len(SL.END)
    index = struct.pack('>IIII', 0x10001, index_len, offs[SL.INDEX_NAME], 1)
    index += struct.pack('>8I', NBR.fnv1a(pname), offs[pname], 1, at, *SL.ROW_TAIL)
    return head + pool_rec + index + sm + SL.END + page

def run(machines, queries):
    img = (ROOT/'out/MAIN_c0000000.bin').read_bytes()
    pr = P.NbuProbe(img[:P.SEG0_SIZE]); pr.install_arena(); pr.survey = True
    for lo, hi, what in SL.SM_CODE: pr.allow(lo, hi, what)
    pr.allow(0xC05DE928, 0xC05DE940, 'app+0xF4 accessors')     # FUN_c05de928/930/938
    pr.allow(0xC05D7470, 0xC05D7600, 'vector')                  # push_back / get / grow
    # app+0xF4 vector {allocator, count, cap, grow, data}
    pr.write_words(pr.APP + 0xF4, pr.ALLOCATOR, 0, 0, 4, 0)
    pr.open(blob=pack(machines), magic=False, cursor=12, version=SL.VERSION)
    tr = pr.records(64)
    assert tr[-1].token == 0xFFFFFFFF, [hex(t.token) for t in tr]
    n = pr.words(pr.APP + 0xF8)[0]; data = pr.words(pr.APP + 0x104)[0]
    order = [pr.string(pr.words(pr.words(data + 4*i)[0] + 8)[0]) for i in range(n)]
    sc = pr.HEAP + 0x60000; out = {}
    for cur, req in queries:
        pr.write(sc, cur.encode()+b'\0'); pr.write(sc+0x40, req.encode()+b'\0'); pr.write_words(sc+0x80, 0)
        # FUN_c05ed028(app, cur, 0, req, &out, depth=0): r0..r3 + 2 stack args
        pr.write_words(pr.STACK, sc+0x80, 0)          # 5th/6th args on the stack (_call sets SP=STACK)
        pr._call(0xC05ED028, pr.APP, sc, 0, sc+0x40)
        st = pr.words(sc+0x80)[0]
        out[(cur, req)] = pr.string(pr.words(st+4)[0]) if st else None
    return order, out

if __name__ == '__main__':
    Q = [('MainY5','Menu01'), ('MainB1','Menu13'), ('MainY5','Menu12'), ('MainY5','Menu14'), ('MainY6','Menu01'), ('MainY6','Menu13')]
    for ms in ([STOCK, PRIV], [PRIV, STOCK]):
        order, out = run(ms, Q)
        print('app+0xF4 order:', order)
        for k, v in out.items(): print('   ', k, '->', v)
