import sys, time, json
sys.path.insert(0, '/Users/dido/Developer.localized/SIGMAfp_re/fpSup/fp_usb_shell')
from putfile import sh, mem_get
out = {}
r = sh('status get is_recording'); out['is_recording'] = r.strip()
if 'is_recording -> 0' not in r and ' 0' not in r[-3:]:
    print('recording? abort', r); sys.exit(1)
out['chsel'] = mem_get(0xC31DF8D8, 2)
out['desc'] = [hex(x) if x is not None else None for x in mem_get(0xC30255B4, 32)]
regs = {'ch2': 0x301832E8, 'ch5': 0x301835E8, 'ch0': 0x301821E8, 'ch1': 0x301822E8, 'ch8': 0x301837E8}
seq = []
t0 = time.time()
for i in range(20):
    v = {k: mem_get(a)[0] for k, a in regs.items()}
    seq.append((round((time.time() - t0) * 1000), v))
    time.sleep(0.005)
out['slots'] = seq
p = mem_get(0xC358DCC0, 8); out['objs'] = [hex(x) for x in p]
o = {}
for a in p:
    if a and 0x40000000 <= (a & 0x7FFFFFFF | 0x40000000) and a >= 0x40000000:
        w = mem_get(a + 0x3C, 4)
        o[hex(a)] = {'+3C': hex(w[0]), '+48': hex(w[3])}
out['obj_bufs'] = o
print(json.dumps(out, indent=1))
