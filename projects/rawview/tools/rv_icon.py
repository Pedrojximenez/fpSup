#!/usr/bin/env python3
"""rv_icon.py — 產生 COLOR 選單第 17 列的「RAW」圖示(XCI),寫到 build/rv_raw_icon.xci。

規格取自原廠 set_common_1.xci(「OFF」,ROM 0xC14E4F98,86×74,墨水框 x 17..68、y 25..47,純白抗鋸齒 L == A):
字型 Arial Narrow(對原廠「OFF」逐像素比對,系統字型中誤差最小 3.1 %),字高 23 px、底線 y 47、水平置中,邊緣 lo 0.05 / hi 0.6。
XCI 編碼沿用 projects/open-gate/build/xci.py(OG3K 的工具)。卡片以 H1(stub_fv)在讀取 set_flash_1.xci
(0xC14EBAAC,533 B,原廠閃電圖示、Color 選單未使用)時換成本檔(2026-09-25 上機:與 OFF/MONO./DUO. 同風格)。

    python3 rv_icon.py            # 重新產生並比對與現有檔案是否相同
"""
import pathlib, sys
import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / 'projects' / 'open-gate' / 'build'))
import xci  # noqa: E402

ROM = REPO / 'out' / 'MAIN_c0000000.bin'
REF = 0xC14E4F98                     # set_common_1.xci(OFF)
FONT = '/System/Library/Fonts/Supplemental/Arial Narrow.ttf'
OUT = HERE.parent / 'build' / 'rv_raw_icon.xci'

# 右側框的字形(SA/GA):原廠 font_menu_LB(粗窄體,字高 41、底線 y 42);DIN Alternate Bold 對原廠「0」「1」誤差最小(6.6 %)。
# 框顯示 ±0 = 符號格 kigou_08(41×51)+ 數字格 LB_0(34×51);+1 = kigou_07 + LB_1。RAW 時換成 S+A / G+A。
GLYPH_FONT = '/System/Library/Fonts/Supplemental/DIN Alternate Bold.ttf'
GLYPHS = [  # (輸出檔, 字, 原廠位址(名稱), 寬, 高)
    ('rv_glyph_S.xci', 'S', 0xC1427874, 41, 51),   # font_menu_LB_kigou_08(±)
    ('rv_glyph_G.xci', 'G', 0xC1427788, 41, 51),   # font_menu_LB_kigou_07(+)
    ('rv_glyph_A0.xci', 'A', 0xC141E30C, 34, 51),  # font_menu_LB_0
    ('rv_glyph_A1.xci', 'A', 0xC141E5B4, 34, 51),  # font_menu_LB_1
]


def glyph(ch, W, H, cap=41, base=42, ss=8, lo=0.05, hi=0.6):
    from PIL import Image, ImageDraw, ImageFont
    for size in range(90, 10, -1):
        f = ImageFont.truetype(GLYPH_FONT, size * ss)
        big = Image.new('L', (W * ss, H * ss), 0)
        ImageDraw.Draw(big).text((W * ss // 2, H * ss // 2), ch, font=f, fill=255, anchor='mm')
        ys, xs = np.where(np.array(big) > 128)
        if (ys.max() - ys.min() + 1) / ss <= cap + 0.5:
            sm = np.array(big.resize((W, H), Image.LANCZOS)).astype(float) / 255
            ys, xs = np.where(sm > 0.1)
            sm = np.roll(np.roll(sm, base - ys.max(), 0), (W - 1) // 2 - (xs.min() + xs.max()) // 2, 1)
            sm = np.clip((np.clip(sm, 0, 1) - lo) / (hi - lo), 0, 1)
            return (sm * 255 + 0.5).astype(np.uint8)
    raise ValueError('排不下')


def render(text, W, H, cap=23, base=47, cx=42, ss=8, lo=0.05, hi=0.6):
    from PIL import Image, ImageDraw, ImageFont
    for size in range(60, 8, -1):
        f = ImageFont.truetype(FONT, size * ss)
        big = Image.new('L', (W * ss, H * ss), 0)
        ImageDraw.Draw(big).text((W * ss // 2, H * ss // 2), text, font=f, fill=255, anchor='mm')
        ys, xs = np.where(np.array(big) > 128)
        if (ys.max() - ys.min() + 1) / ss <= cap + 0.5:
            sm = np.array(big.resize((W, H), Image.LANCZOS)).astype(float) / 255
            ys, xs = np.where(sm > 0.1)
            sm = np.roll(np.roll(sm, base - ys.max(), 0), cx - (xs.min() + xs.max()) // 2, 1)
            sm = np.clip((np.clip(sm, 0, 1) - lo) / (hi - lo), 0, 1)   # 收緊邊緣(原廠只有薄薄一圈半透明)
            return (sm * 255 + 0.5).astype(np.uint8)
    raise ValueError('排不下')


def make():
    W, H, _, _ = xci.decode(ROM.read_bytes(), REF - 0xC0000000)
    t = render('RAW', W, H)
    return xci.encode(t, t)


def write(path, blob):
    old = path.read_bytes() if path.exists() else None
    path.write_bytes(blob)
    print(f'{path}  {len(blob)} B  {"與舊檔相同" if old == blob else "已更新"}')


if __name__ == '__main__':
    write(OUT, make())
    for name, ch, at, W, H in GLYPHS:
        t = glyph(ch, W, H)
        write(HERE.parent / 'build' / name, xci.encode(t, t))
