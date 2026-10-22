#!/usr/bin/env python3
"""rv_snapshot.py — rawview 階段一：唯讀快照(來源 RAW + 監看路徑設定)。

不寫任何相機設定、不 hook。做的事:
  1. `imager mode_now` 文字(模式、gain_state、small_raw hvbin)
  2. ImgCtrl 幀描述 0xC3439404(bit depth / endian / raw_addr / small_raw_addr)
  3. 監看路徑的 shadow / descriptor 區段(research/liveview 各稽核列的最小快照清單)
  4. 可選 --raw:用 read_direct 讀 SIG 環形緩衝的每個槽(待機 LV RAW,8-bit Bayer)

注意 research/liveview 的限制:這些區段是**依序**讀的,不是同一幀的一致快照。
前後各讀一次幀描述與 mode_now,前後不一致就標 coherent=false,不拿來下結論。

用法:
  python3 rv_snapshot.py --out ../captures/<label>            # 只讀設定
  python3 rv_snapshot.py --out ../captures/<label> --raw      # 加讀 LV RAW 槽
"""
import argparse, json, pathlib, sys, time

REPO = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / 'fpSup' / 'fp_usb_shell'))
from putfile import sh, mem_get, read_direct  # noqa: E402

FRAME_DESC = 0xC3439404

# (名稱, 起點, bytes, 出處)
REGIONS = [
    ('frame_desc',      FRAME_DESC, 0x80,  'RAW_PUSH.md §1.1'),
    ('isp_shadow',      0x30210000, 0x2400, 'isp-path-audit §1 / raw-front-audit §1'),
    ('sigseq_lut_desc', 0x30200000, 0x200, 'isp-path-audit §8'),
    ('tone_sw_desc',    0xC31D7554, 0x98,  'isp-path-audit §8'),
    ('tone_cache',      0xC3414D28, 0x80,  'isp-path-audit §8'),
    ('tone_singleton',  0xC3414470, 0x1A0, 'isp-path-audit §3/§8'),
    ('native_gain',     0xC34143B8, 0xB8,  'matrix-gamma-audit §3'),
    ('disp_csc_bank1',  0x30190800, 0x40,  'display-route-audit'),
    ('disp_csc_bank0',  0x30190860, 0x40,  'display-route-audit'),
    ('disp_gamma_a',    0x30190940, 0x30,  'display-route-audit'),
    ('disp_csc_bank2',  0x30190C70, 0x40,  'display-route-audit'),
    ('disp_gamma_b',    0x30190CB0, 0x30,  'display-route-audit'),
]

BITDEPTH = {0: 12, 1: 14, 3: 10, 4: 8}


def words(addr, nbytes, chunk=0x100):
    # `mem get` 的回覆有長度上限,大區段要分段
    w = []
    for off in range(0, nbytes, chunk):
        w += mem_get(addr + off, min(chunk, nbytes - off) // 4)
    if any(x is None for x in w):
        raise SystemExit(f'read 0x{addr:08X}+{nbytes:#x}: {w.count(None)} words missing')
    return w


def blob(w):
    return b''.join(x.to_bytes(4, 'little') for x in w)


def parse_desc(w):
    b = lambda off: w[off // 4]
    return {
        'opcode': b(0x00), 'sens_mode': b(0x1C),
        'bitdepth_enum': b(0x20), 'bitdepth': BITDEPTH.get(b(0x20)),
        'ob': b(0x24), 'endian': b(0x28), 'pics': b(0x2C),
        'shutter0': b(0x30), 'gain0': b(0x34),
        'raw_addr0': f'0x{b(0x38):08X}', 'small_raw_addr0': f'0x{b(0x3C):08X}',
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--raw', action='store_true', help='also read the small_raw buffer')
    ap.add_argument('--raw-bytes', type=lambda s: int(s, 0), default=0,
                    help='override small_raw length (default: from mode_now geometry)')
    a = ap.parse_args()
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)

    meta = {'t0': time.time(), 'regions': {}}
    meta['mode_before'] = sh('imager mode_now')
    d0 = parse_desc(words(FRAME_DESC, 0x80))

    for name, addr, n, src in REGIONS:
        w = words(addr, n)
        (out / f'{name}_{addr:08X}.bin').write_bytes(blob(w))
        meta['regions'][name] = {'addr': f'0x{addr:08X}', 'bytes': n, 'source': src}
        print(f'  {name:16s} 0x{addr:08X} +{n:#x}', file=sys.stderr)

    if a.raw:
        # 待機 LV RAW 在 SIG 環形緩衝(README 階段 2);ImgCtrl 幀描述在待機是空的
        w, h, count, _, *handles = words(0xC31E0DD4, 0x20)
        n = a.raw_bytes or words(0xC31DF6AC, 4)[0]
        slots = []
        for i, hd in enumerate(handles[:count]):
            addr = (hd & 0x3FFFFFFF) * 4 + 0x40000000
            if not 0x40000000 <= addr < 0x60000000:
                raise SystemExit(f'slot {i} {addr:#x} outside DMA range; not reading')
            (out / f'sigring_slot{i}_{addr:08X}.bin').write_bytes(read_direct(addr, n, f'slot{i}'))
            slots.append(f'0x{addr:08X}')
        meta['sigring'] = {'w': w, 'h': h, 'slot_bytes': n, 'slots': slots,
                           'work_buf': f'0x{words(0xC375D928, 4)[0]:08X}'}

    d1 = parse_desc(words(FRAME_DESC, 0x80))
    meta['mode_after'] = sh('imager mode_now')
    meta['desc_before'], meta['desc_after'] = d0, d1
    same_fmt = all(d0[k] == d1[k] for k in ('sens_mode', 'bitdepth_enum', 'endian'))
    meta['coherent'] = same_fmt and meta['mode_before'].split('frame_count')[0] == \
        meta['mode_after'].split('frame_count')[0]
    meta['t1'] = time.time()
    (out / 'snapshot.json').write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    print(json.dumps({k: meta[k] for k in ('desc_before', 'coherent')}, indent=2))


if __name__ == '__main__':
    main()
