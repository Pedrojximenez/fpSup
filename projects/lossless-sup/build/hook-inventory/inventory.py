"""Read-only inventory: what every sup writes into the firmware image, and
where two products touch the same bytes or the same firmware function.
Sources: the newest release of each catalogue product (VBIN sections) and the
lossless test card. Runtime writes to heap objects are not visible here."""
import bisect, json, pickle, struct, sys, pathlib
sys.path.insert(0, 'fpSup/tools/card-composer')
import build_catalogue as C
seg = open('out/seg0_c0000000.bin', 'rb').read()
B = 0xC0000000
starts = pickle.load(open('/tmp/claude-501/fnstarts.pkl', 'rb'))
addrs = [a for a, _ in starts]
def fn(a):
    i = bisect.bisect_right(addrs, a) - 1
    return starts[i] if i >= 0 else (0, '?')
def region(a, n):
    if a == 0: return 'launcher(dest0)'
    if a < C.POOL_SIZE: return 'pool-offset'
    if 0xC072D000 <= a < 0xC0735000: return 'cave'
    if 0xC0730000 <= a < 0xC0800000: return 'fw-free/cave-ext'
    if 0xC18C0460 <= a < 0xC2D8CEF8: return 'NBU(UI records)'
    if 0xC0D22400 <= a < 0xC18C0460: return 'NBR(UI resources)'
    if a < 0xC0A00000: return 'code' if n <= 16 else 'code-block'
    if a < 0xC2F30800: return 'data/tables'
    return 'bss'
products = {}
for spec in C.discover():
    blob = C.payload(spec["dir"]).read_bytes()
    entry, recs = C.parse(blob)
    products[spec['id'] + ' ' + spec['version']] = recs
card = pathlib.Path('projects/lossless-sup/build/testcard-20260930-q/fpSup.BIN').read_bytes()[:0xF000]
products['lossless q'] = C.parse(card)[1]
rows = []
for p, recs in products.items():
    for dst, data in recs:
        r = region(dst, len(data))
        stock = seg[dst - B:dst - B + len(data)] if B <= dst < B + len(seg) else b''
        f = fn(dst) if r in ('code', 'code-block') else (0, '')
        rows.append(dict(product=p, dst=dst, len=len(data), region=r,
                         func=f[1], func_at=f[0], same_as_stock=(stock == data)))
json.dump(rows, open('projects/lossless-sup/build/hook-inventory/sections.json', 'w'), indent=0)
# summary per product
from collections import Counter, defaultdict
for p in products:
    c = Counter(r['region'] for r in rows if r['product'] == p)
    print(f'{p:22s}', dict(c))
# overlaps between products
print('\n== byte-range overlaps between different products ==')
spans = sorted((r['dst'], r['dst'] + r['len'], r['product'], r['region']) for r in rows if r['dst'] >= B)
for i, (a0, a1, p, rg) in enumerate(spans):
    for b0, b1, q, rg2 in spans[i + 1:]:
        if b0 >= a1: break
        if q.split()[0] != p.split()[0]:
            print(f'  {a0:#x}+{a1-a0} {p} [{rg}]  <->  {b0:#x}+{b1-b0} {q} [{rg2}]')
print('\n== code patches landing in the same firmware function (different products) ==')
byf = defaultdict(set)
for r in rows:
    if r['region'] in ('code', 'code-block'):
        byf[(r['func_at'], r['func'])].add((r['product'].split()[0], r['dst']))
for (fa, name), s in sorted(byf.items()):
    prods = {p for p, _ in s}
    if len(prods) > 1:
        print(f'  {name} @ {fa:#x}: ' + ', '.join(f'{p}@{d:#x}' for p, d in sorted(s)))
