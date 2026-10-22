#!/usr/bin/env python3
"""從韌體與反編譯抽出 fp 的 ISP 色彩硬體地圖。

輸出 isp-map.json:
  blocks   —— ROM 裡的 ISP 區塊名稱表(不推論像素處理順序)
  setters  —— 含 0x3021xxxx shadow bank 引用的函式與它碰的暫存器
  notes    —— 已指認的項目

2026-10-09 更正:SIGPRO 診斷 dumper 直接引用區塊名稱並列出 MMIO;
descriptor 建構另列出 MMIO ↔ shadow。兩者可離線交叉連接。
這仍不證明像素算式、active context、處理順序或即時 3D LUT 能力。
"""
import argparse, hashlib, json, os, re

ROOT = '/Users/dido/Developer.localized/SIGMAfp_re'
ROM = os.path.join(ROOT, 'out/MAIN_c0000000.bin')
DECOMP = os.path.join(ROOT, 'out/decomp/full/blk_c01.c')
NAME_LO, NAME_HI = 0xC07D3600, 0xC07D3D40
BASE = 0xC0000000

# 依 research/liveview/matrix-gamma-audit.md 的 descriptor 稽核(FUN_c019c810)
IDENTIFIED = {
    0x30210C70: 'IGAMMA 控制參數(shadow C70..CAC / MMIO 30115000..3C)',
    0x30210C78: 'IGAMMA 的 27 個分段值 — FUN_c0107250 打包 27 個值成 14 字,不是 3×3',
    0x30210CB0: 'RGBLMAT 第一組 3×3 — 9 個 11-bit 係數(shadow CB0..CE4 / MMIO 30115100..34)',
    0x30210CC8: 'RGBLMAT 第二組 3×3 — 同格式,取自結構 +0x24',
    0x30210CE0: 'RGBLMAT 共用欄位 / 尺度旗標',
    0x30210CF0: 'RGBLMAT 其餘欄位(shadow CEC..D14 / MMIO 3011513C..64),不是獨立矩陣',
}


def block_names(rom=ROM):
    d = open(rom, 'rb').read()
    seg = d[NAME_LO - BASE:NAME_HI - BASE]
    out, off = [], NAME_LO
    for part in seg.split(b'\x00'):
        s = part.decode('latin1').strip()
        if s and 2 < len(s) < 32 and re.fullmatch(r'[A-Za-z0-9_ ]+', s):
            out.append({'addr': hex(off), 'name': s})
        off += len(part) + 1
    return out


def functions(src):
    # Named vtable functions also delimit bodies; do not merge them into a FUN.
    parts = re.split(r'/\* ==== (\S+) @ (c[0-9a-f]+) ==== \*/', src)
    return [(parts[i], parts[i + 1], parts[i + 2]) for i in range(1, len(parts), 3)]


def setters(src=None):
    if src is None:
        src = open(DECOMP, encoding='utf-8', errors='replace').read()
    out = []
    for name, _, body in functions(src):
        regs = sorted({int(x, 16) for x in re.findall(r'0x(3021[0-9a-f]{3,4})', body)})
        if regs:
            out.append({'func': name, 'first': hex(regs[0]), 'last': hex(regs[-1]),
                        'count': len(regs), 'regs': [hex(r) for r in regs]})
    out.sort(key=lambda e: int(e['first'], 16))
    return out


def routes(src, rom):
    """Join explicit diagnostic name references to explicit descriptor mappings."""
    descriptors = []
    for fn, addr, body in functions(src):
        for m in re.finditer(
                r'FUN_c019df90\([^,]+,0x([0-9a-f]+),'
                r'(0x[0-9a-f]+|\d+),[^;]*?\+ 0x([0-9a-f]+)\);', body):
            mmio, words, shadow = int(m[1], 16), int(m[2], 0), int(m[3], 16)
            descriptors.append({'mmio': mmio, 'words': words, 'shadow': shadow,
                                'function': fn, 'address': '0x' + addr})
    out = []
    for fn, addr, body in functions(src):
        labels = list(re.finditer(
            r'FUN_c01f57f4\(0xc31d9c9c,s_[A-Za-z0-9_]+_c([0-9a-f]+)\);', body))
        for i, label in enumerate(labels):
            end = labels[i + 1].start() if i + 1 < len(labels) else len(body)
            regs = [int(v, 16) for v in re.findall(
                # Some decompiled calls have extra arguments (e.g. TMAP).
                # Only the first argument is established as the dump address.
                r'FUN_c015c1d8\((?:0x|&DAT_)([0-9a-f]+)(?=[,)])', body[label.end():end])]
            if not regs:
                continue
            name_addr = int('c' + label[1], 16)
            start = name_addr - BASE
            if start < 0 or start >= len(rom):
                raise ValueError('diagnostic name outside ROM')
            name = rom[start:rom.index(b'\x00', start)].decode('ascii').strip()
            mappings = []
            for reg in regs:
                match = [d for d in descriptors if d['mmio'] <= reg < d['mmio'] + d['words'] * 4]
                for d in match:
                    mappings.append({'diagnostic_mmio': hex(reg), 'mmio_start': hex(d['mmio']),
                                     'shadow_start': hex(d['shadow']), 'words': d['words'],
                                     'descriptor_function': d['function']})
            out.append({'name': name, 'name_addr': hex(name_addr), 'diagnostic_function': fn,
                        'diagnostic_address': '0x' + addr,
                        'diagnostic_mmio': [hex(r) for r in regs], 'mappings': mappings})
    return out


def extract(rom_path=ROM, decomp_path=DECOMP):
    rom = open(rom_path, 'rb').read()
    src_bytes = open(decomp_path, 'rb').read()
    src = src_bytes.decode('utf-8')
    data = {
        'source': {'rom': rom_path, 'decomp': decomp_path,
                   'rom_sha256': hashlib.sha256(rom).hexdigest(),
                   'decomp_sha256': hashlib.sha256(src_bytes).hexdigest()},
        'caveat': '診斷名稱引用與 descriptor 可確定 MMIO/shadow 地圖;不證明像素算式、順序、active context 或 3D LUT 能力。setters 保留歷史 key,實際列的是含 shadow 位址引用的函式。',
        'blocks': block_names(rom_path),
        'setters': setters(src),
        'routes': routes(src, rom),
        'identified': {hex(k): v for k, v in IDENTIFIED.items()},
    }
    return data


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root', default=ROOT)
    ap.add_argument('--output', default=os.path.join(os.path.dirname(__file__), 'isp-map.json'))
    args = ap.parse_args()
    data = extract(os.path.join(args.root, 'out/MAIN_c0000000.bin'),
                   os.path.join(args.root, 'out/decomp/full/blk_c01.c'))
    with open(args.output, 'w') as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
        f.write('\n')
    print('區塊名稱 %d 筆,shadow 引用 %d 支,具名診斷路由 %d 筆' % (
        len(data['blocks']), len(data['setters']), len(data['routes'])))


if __name__ == '__main__':
    main()
