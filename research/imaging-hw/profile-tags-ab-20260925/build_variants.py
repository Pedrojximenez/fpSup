#!/usr/bin/env python3
"""從 A001_297(OFF)與 A001_298(Standard)各第 1 幀,就地換 DNG profile tag,產生 A–G 七個變體。

RAW strip 一個 byte 都不動(輸出時逐檔以 SHA-256 驗證)。
五個 tag 在兩支素材裡的 offset 與長度完全相同,所以是純 in-place 覆寫。
"""
import struct, os, hashlib, json, sys

SRC_OFF = '/Users/dido/Movies/fpSup/color area/A001_297/A001_297_20260924_000001.DNG'
SRC_STD = '/Users/dido/Movies/fpSup/color area/A001_298/A001_298_20260924_000001.DNG'
OUT     = '/Users/dido/Movies/fpSup/color area/looktag_ab'

TAGS = {50721: 'CM1', 50722: 'CM2', 50938: 'HSM1', 50939: 'HSM2', 50940: 'TC'}


def ifd0(path):
    d = open(path, 'rb').read()
    bo = '<' if d[:2] == b'II' else '>'
    off = struct.unpack(bo + 'I', d[4:8])[0]
    n = struct.unpack(bo + 'H', d[off:off + 2])[0]
    sz = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 7: 1, 9: 4, 10: 8, 11: 4, 12: 8}
    out = {}
    for i in range(n):
        e = off + 2 + i * 12
        t, ty, c = struct.unpack(bo + 'HHI', d[e:e + 8])
        nb = c * sz.get(ty, 1)
        vo = struct.unpack(bo + 'I', d[e + 8:e + 12])[0] if nb > 4 else e + 8
        out[t] = (vo, nb)
    return d, bo, out


def raw_strip_sha(d, bo='<'):
    off = struct.unpack(bo + 'I', d[4:8])[0]
    n = struct.unpack(bo + 'H', d[off:off + 2])[0]
    so = sc = None
    for i in range(n):
        e = off + 2 + i * 12
        t, ty, c = struct.unpack(bo + 'HHI', d[e:e + 8])
        if t == 273: so = struct.unpack(bo + 'I', d[e + 8:e + 12])[0]
        if t == 279: sc = struct.unpack(bo + 'I', d[e + 8:e + 12])[0]
    return hashlib.sha256(d[so:so + sc]).hexdigest(), so, sc


def main():
    off, bo, toff = ifd0(SRC_OFF)
    std, _,  tstd = ifd0(SRC_STD)
    for t, nm in TAGS.items():
        assert toff[t] == tstd[t], ('tag layout differs', nm, toff[t], tstd[t])
    T = {TAGS[t]: toff[t] for t in TAGS}

    def patch(base, donor, keys):
        b = bytearray(base)
        for k in keys:
            o, n = T[k]
            b[o:o + n] = donor[o:o + n]
        return bytes(b)

    plan = [
        ('A_stdOriginal',            std, off, [],                        'Standard 原檔(對照)'),
        ('B_stdNoToneCurve',         std, off, ['TC'],                    'Standard 換上 OFF 的 identity ToneCurve'),
        ('C_stdNoHueSatMap',         std, off, ['HSM1', 'HSM2'],          'Standard 換上 OFF 的 identity HueSatMap'),
        ('D_stdNoLook',              std, off, ['TC', 'HSM1', 'HSM2'],    'Standard 只留 normal 矩陣,look 全 identity'),
        ('E_offOriginal',            off, std, [],                        'OFF 原檔(對照)'),
        ('F_offNormalMatrix',        off, std, ['CM1', 'CM2'],            'OFF + normal 矩陣(= C_firmware_normal 配方)'),
        ('G_offFullStandardProfile', off, std, ['CM1', 'CM2', 'HSM1', 'HSM2', 'TC'], 'OFF + 完整 Standard profile'),
    ]
    src_raw = {id(std): raw_strip_sha(std, bo)[0], id(off): raw_strip_sha(off, bo)[0]}
    man = {}
    for name, base, donor, keys, desc in plan:
        data = patch(base, donor, keys)
        d = os.path.join(OUT, name)
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, name + '.DNG'), 'wb').write(data)
        h, so, sc = raw_strip_sha(data, bo)
        man[name] = {
            'description': desc,
            'base': 'A001_298 (Standard)' if base is std else 'A001_297 (OFF)',
            'tags_replaced': keys,
            'bytes_changed_vs_base': sum(1 for a, b in zip(data, base) if a != b),
            'sha256': hashlib.sha256(data).hexdigest(),
            'raw_strip': {'offset': so, 'bytes': sc, 'sha256': h,
                          'unchanged_vs_base': h == src_raw[id(base)]},
        }
        assert man[name]['raw_strip']['unchanged_vs_base'], name
    json.dump(man, open(os.path.join(OUT, 'manifest.json'), 'w'), indent=1, ensure_ascii=False)
    print(json.dumps(man, indent=1, ensure_ascii=False))


if __name__ == '__main__':
    main()
