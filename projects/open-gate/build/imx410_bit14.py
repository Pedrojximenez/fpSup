"""14-bit through a RAM marker, the way 239.76 fps is done (imx410_rate_native).

The stock bit-depth setting is persisted and read at boot before any loader, so
it never holds 14-bit (eRawBitType 1).  The bit-depth row 3 ("14 bit") hands
stock 12-bit (value 0) through our copy of the row<->value pair table; the
choice lives only in BIT14 (zero every boot), set by sl_excl ROLE 14 from the
committed row.  The stock getter C005BF28 then reports 14-bit under CUSTOM +
CinemaDNG (imx410_bit14.S), so the picker, the MODE list and the recording
pipeline all see 14 while the setting stays 12.

Pair table: stock C2E401CC = (4,0) (3,1) (0,2) (1,3), value -> row lookups take
the first match.  Ours has (0,2) and (0,3); ROLE 14 orders those two so the
chosen row comes first (as imx410_rate_native ROLE 6/7 do for (7,8) / (7,9)).
"""
from pathlib import Path
import struct
from armasm import assemble

B = 0xC0000000
FLAG, FMTLATCH = 0xC0731C08, 0xC0731C20
BIT14 = 0xC0731C88                  # RAM marker: 1 = row 3 (14 bit) chosen
BIT_PAIR = 0xC0731C8C               # 4 x {value, row} = 32 B
GET_CODE = 0xC07312A0               # getter hook payload (free 0xC07312A0..0xC0731310)
NOTIFY_CODE = 0xC0731F64            # ROLE 2 (off, WITH_NOTIFY): not placed
PENDING = 0xC0731CAC                # sl_excl ROLE 14: BIT14 changed, notify after stock
GET_SITE, GET_STOCK = 0xC005BF28, 0xE92D4030   # push {r4, r5, lr}
STOCK_PAIR = 0xC2E401CC
STOCK_PAIRS = ((4, 0), (3, 1), (0, 2), (1, 3))
PAIR_SITES = ((0xC06BD7CC, 0xE30021CC, 'bit pair table low'),
              (0xC06BD7D0, 0xE34C22E4, 'bit pair table high'))
ROW14 = 3
BLACK_CODE = 0xC07323A0             # ROLE 3, DNG BlackLevel bit depth (free 0xC07323A0..0xC0732400)
BLACK_SITES = ((0xC02CA1C0, 0xEB0041AA), (0xC02CA21C, 0xEB004193))   # bl FUN_c02da870 in FUN_c02ca190
# Replay stock's change notification when BIT14 flips (ROLE 2).  Camera r89
# 2026-10-05: the picker still saw 12 afterwards and MV_DNGQuality read row 0;
# off -- imx410_fmt writes the picker config's eRawBitType instead.
WITH_NOTIFY = False


def pairs(img):
    got = tuple(struct.unpack_from('<2I', img, STOCK_PAIR - B + 8 * i) for i in range(4))
    if got != STOCK_PAIRS:
        raise ValueError(f'bit pair table differs: {got}')
    return struct.pack('<8I', 4, 0, 3, 1, 0, 2, 0, ROW14)


def payloads():
    src = str(Path(__file__).with_suffix('.S'))
    return [('imx410_bit14_1', src, GET_CODE), ('imx410_bit14_3', src, BLACK_CODE)] + ([('imx410_bit14_2', src, NOTIFY_CODE)] if WITH_NOTIFY else [])


def defines():
    common = [f'BIT14={BIT14:#x}', f'FLAG={FLAG:#x}', f'FMTLATCH={FMTLATCH:#x}']
    return {f'imx410_bit14_{r}': [f'ROLE={r}'] + common for r in (1, 2, 3)}


def blobs():
    out = {name: assemble(src, defines=defines()[name]) for name, src, _ in payloads()}
    if len(out['imx410_bit14_1']) > 0x70 or len(out.get('imx410_bit14_2', b'')) > 0x100:
        raise ValueError('imx410_bit14 overflows its slot')
    return out


def regions():
    return [(BIT14, BIT14 + 4, 'BIT14 記號(只在記憶體)'),
            (BIT_PAIR, BIT_PAIR + 32, 'BIT_PAIR 位深 enum<->列 配對表'),
            (PENDING, PENDING + 4, 'BIT14 改變待通知')]


def _mov(rd, imm, high=False):
    return (0xE3400000 if high else 0xE3000000) | ((imm >> 12) & 15) << 16 | rd << 12 | (imm & 0xFFF)


def patches(img):
    """The pair-table pointer (before any hook); validates every site."""
    for a, stock, note in PAIR_SITES:
        if struct.unpack_from('<I', img, a - B)[0] != stock:
            raise ValueError(f'{note}: stock word differs at {a:#x}')
    for a, stock in BLACK_SITES:
        if struct.unpack_from('<I', img, a - B)[0] != stock:
            raise ValueError(f'BlackLevel bit-depth call {a:#x} is not the stock bl')
    if struct.unpack_from('<I', img, GET_SITE - B)[0] != GET_STOCK:
        raise ValueError('bit-depth getter C005BF28 is not the stock push')
    return [(PAIR_SITES[0][0], _mov(2, BIT_PAIR & 0xFFFF), f'bit pair table -> {BIT_PAIR:#x}'),
            (PAIR_SITES[1][0], _mov(2, BIT_PAIR >> 16, True), 'bit pair table high')]
