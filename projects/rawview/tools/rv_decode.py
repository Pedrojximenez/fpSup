#!/usr/bin/env python3
"""rv_decode.py — 把 rv_snapshot 的 bin 解成可讀摘要(純離線)。

    python3 rv_decode.py ../captures/<label>            印摘要
    python3 rv_decode.py A B                            兩次快照逐字差異

欄位解讀依 research/liveview 各稽核;[?] 表示語意未證。
"""
import pathlib, struct, sys

SHADOW = 0x30210000


def load(d, prefix):
    f = next(pathlib.Path(d).glob(f'{prefix}_*.bin'))
    b = f.read_bytes()
    return struct.unpack(f'<{len(b)//4}I', b)


def s11(v):
    v &= 0x7FF
    return v - 0x800 if v & 0x400 else v


def summary(d):
    w = load(d, 'isp_shadow')
    at = lambda a, n=1: w[(a - SHADOW) // 4:(a - SHADOW) // 4 + n]
    out = []
    tb = at(0x302103C8, 2)
    out.append(f'TBLSD gain [?順序] {tb[0] & 0xFFFF} {tb[0] >> 16} {tb[1] & 0xFFFF} {tb[1] >> 16}'
               '  (預設 256/512/512/256)')
    wb = at(0x30210768, 2)
    out.append(f'SIG1 WB gain {wb[0] & 0xFFFF} {wb[0] >> 16} {wb[1] & 0xFFFF} {wb[1] >> 16}')
    out.append(f'ctl 30210014 = {at(0x30210014)[0]:08X}  (bit7 RWAPKNEE enable = {at(0x30210014)[0] >> 7 & 1})')
    ig = at(0x30210C70, 2)
    out.append(f'IGAMMA ctl {ig[0]:08X} {ig[1]:08X}')
    m = at(0x30210CB0, 14)
    # 每組 6 words = 12 個半字;欄位對到 3×3 的方式未證,照 packed 順序列出(÷512)
    c = [s11(h) for x in m[:12] for h in (x & 0xFFFF, x >> 16)]
    out.append('RGBLMAT set1 ' + ' '.join(f'{x/512:+.3f}' for x in c[:12]))
    out.append('RGBLMAT set2 ' + ' '.join(f'{x/512:+.3f}' for x in c[12:24]))
    out.append(f'RGBLMAT 30115130/34 = {m[12]:08X} {m[13]:08X}  (+34 = 係數除2旗標)')
    out.append(f'GAMDEC {at(0x30210D50)[0]:08X} {at(0x30210D54)[0]:08X}')
    out.append('YCMAT ' + ' '.join(f'{x:08X}' for x in at(0x30210E64, 8)))
    out.append('C_SAT_C ' + ' '.join(f'{x:08X}' for x in at(0x3021127C, 13)))
    for bank in ('disp_csc_bank0', 'disp_csc_bank1', 'disp_csc_bank2'):
        v = load(d, bank)
        k = [s11(x) / 256 for x in v[4:16]]
        out.append(f'{bank}: ' + ' | '.join(' '.join(f'{x:+.3f}' for x in k[i:i + 3])
                                             for i in (0, 4, 8)))
    g = bytes(b for x in load(d, 'disp_gamma_a') for b in x.to_bytes(4, 'little'))
    out.append('disp_gamma_a ' + ('identity 16..255' if g[:16] == bytes(range(16, 256, 16)) + b'\xff'
                                  else g.hex()))
    t = load(d, 'tone_sw_desc')
    out.append(f'tone sw desc counts {t[0]} {t[1]}  words ' + ' '.join(f'{x:08X}' for x in t[2:12]))
    return out


def diff(a, b):
    for f in sorted(pathlib.Path(a).glob('*.bin')):
        g = pathlib.Path(b) / f.name
        if not g.exists():
            g = next(pathlib.Path(b).glob(f.name.rsplit('_', 1)[0] + '_*.bin'), None)
        if g is None:
            continue
        x, y = f.read_bytes(), g.read_bytes()
        base = int(f.stem.rsplit('_', 1)[1], 16)
        for i in range(0, min(len(x), len(y)), 4):
            if x[i:i + 4] != y[i:i + 4]:
                print(f'{base + i:08X}  {x[i:i+4][::-1].hex()} -> {y[i:i+4][::-1].hex()}  ({f.stem})')


if __name__ == '__main__':
    if len(sys.argv) == 3:
        diff(*sys.argv[1:])
    else:
        print('\n'.join(summary(sys.argv[1])))
