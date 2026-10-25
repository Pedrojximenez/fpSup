"""Encode the repository logo as native, tinted XCI image layers.

Native menu images use premultiplied ARGB4444. Six tinted masks keep the
artwork's own colours; no stock image is overwritten and the source logo
remains unchanged.
"""
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image

import xci

ROOT = Path(__file__).resolve().parents[3]
SOURCE = Path(__file__).with_name('logo2.png')   # the fpSup logo, kept beside this builder
WIDTH, HEIGHT = 64, 64


@lru_cache(maxsize=2)
def layers(legacy=False):
    """legacy: v3's 31 median-cut layers (its shared UI bytes must not change)."""
    if legacy:
        return legacy_layers()
    # The artwork's own colours -- outline, white, skin, yellow hair, red, cyan -- as
    # six layers: 31 median-cut layers cost ~17 ms a header redraw and muddied them
    # (camera, 2026-10-25: fpSup title <-> row 37 -> 23 ms). Each pixel takes the
    # colour that covers most of it; its opacity is the full-size coverage.
    src = Image.open(SOURCE).convert('RGBA')
    hsv = np.asarray(src.convert('RGB').convert('HSV')).astype(float)
    hue, sat, val = hsv[..., 0] * 360 / 255, hsv[..., 1] / 255, hsv[..., 2] / 255
    alpha = np.asarray(src.getchannel('A')).astype(float) / 255
    rgb = np.asarray(src.convert('RGB')).astype(float)
    lit = (val >= 0.3) & (sat >= 0.25)
    classes = (val < 0.3, (val >= 0.3) & (sat < 0.10), (val >= 0.3) & (sat >= 0.10) & (sat < 0.25),
               lit & (hue > 35) & (hue < 75), lit & ((hue < 35) | (hue > 300)), lit & (hue >= 75) & (hue <= 300))
    palette = []
    cover = []
    for m in classes:
        palette += [int(round(c)) for c in np.median(rgb[m & (alpha > 0.98)], 0)]
        im = Image.fromarray((m * alpha * 255).astype(np.uint8)).resize((WIDTH, HEIGHT), Image.Resampling.BOX)
        cover.append(np.asarray(im).astype(float))
    cover = np.stack(cover)
    pixels = cover.argmax(0)
    opacity = cover.sum(0).clip(0, 255).astype(np.uint8)
    out = []
    for k in sorted(np.unique(pixels)):
        k = int(k)
        rgb = palette[3 * k:3 * k + 3]
        color = (rgb[0] << 24) | (rgb[1] << 16) | (rgb[2] << 8) | 255
        mask = np.where(pixels == k, opacity, 0).astype(np.uint8)
        if not mask.any():
            continue
        # Native images use premultiplied ARGB4444. White at the quantized
        # alpha gives four equal nibbles, matching stock antialiased icons.
        native = (((mask.astype(np.uint16) * 15 + 127) // 255) * 17).astype(np.uint8)
        blob = xci.encode(native, native)
        w, h, lum, alpha = xci.decode(blob)
        assert (w, h) == (WIDTH, HEIGHT) and np.array_equal(lum, native) and np.array_equal(alpha, native)
        out.append((f'FT_LOGO64_C{k:02d}', color, blob))
    return tuple(out)


def legacy_layers():
    small = Image.open(SOURCE).convert('RGBA').resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
    indexed = small.convert('RGB').quantize(colors=32, method=Image.Quantize.MEDIANCUT,
                             dither=Image.Dither.NONE)
    pixels = np.asarray(indexed)
    opacity = np.asarray(small.getchannel('A'))
    palette = indexed.getpalette()
    out = []
    for k in sorted(np.unique(pixels)):
        k = int(k)
        rgb = palette[3 * k:3 * k + 3]
        color = (rgb[0] << 24) | (rgb[1] << 16) | (rgb[2] << 8) | 255
        mask = np.where(pixels == k, opacity, 0).astype(np.uint8)
        if not mask.any():
            continue
        native = (((mask.astype(np.uint16) * 15 + 127) // 255) * 17).astype(np.uint8)
        blob = xci.encode(native, native)
        w, h, lum, alpha = xci.decode(blob)
        assert (w, h) == (WIDTH, HEIGHT) and np.array_equal(lum, native) and np.array_equal(alpha, native)
        out.append((f'FT_LOGO64_C{k:02d}', color, blob))
    return tuple(out)


def preview():
    pixels = np.zeros((HEIGHT, WIDTH, 4), dtype=np.uint8)
    for _name, color, blob in layers():
        _w, _h, _l, alpha = xci.decode(blob)
        pixels[alpha != 0, :3] = [(color >> s) & 255 for s in (24, 16, 8)]
        pixels[alpha != 0, 3] = alpha[alpha != 0]
    return Image.fromarray(pixels)


@lru_cache(maxsize=2)
def images(legacy=False):
    """Keep stock number shapes and alpha, with the factory tab's grey paint.

    Inline image glyphs ignore drawText colour, so their dim variants carry
    the grey luminance themselves. The stock resources remain unchanged.
    """
    import nbr_stock
    nbr = nbr_stock.StockNbr((ROOT / 'out/seg0_c0000000.bin').read_bytes())
    out = list(layers(legacy))
    for k in range(1, 8):
        entries = [e for e in nbr.entries if e.path.endswith(f'/font_menu_MB_{k}.xci')]
        assert len(entries) == 1, f'stock page digit {k} missing or ambiguous'
        w, h, lum, alpha = xci.decode(nbr.read(entries[0].path))
        # Native menu images are ARGB4444. xci.decode exposes the low/high
        # bytes, despite naming them luminance/alpha. Scaling just the low
        # byte would leave the red nibble white and produce a pink digit.
        pixels = (alpha.astype(np.uint16) << 8) | lum.astype(np.uint16)
        grey = pixels & 0xF000
        for shift in (8, 4, 0):
            grey |= ((((pixels >> shift) & 15) * 8 + 7) // 15) << shift
        dim, native_high = (grey & 255).astype(np.uint8), (grey >> 8).astype(np.uint8)
        blob = xci.encode(dim, native_high)
        dw, dh, dl, da = xci.decode(blob)
        assert (dw, dh) == (w, h) and np.array_equal(dl, dim) and np.array_equal(da, native_high)
        assert np.array_equal(grey & 0xF000, pixels & 0xF000)
        assert np.array_equal((grey >> 8) & 15, (grey >> 4) & 15)
        assert np.array_equal((grey >> 4) & 15, grey & 15)
        out.append((f'FT_PAGE_DIM_{k}', 0x888888FF, blob))
    return tuple(out)
