#!/usr/bin/env python3
"""Small JPEG previews of validator frames, for the simulator page (user 2026-10-23: link the frames we actually
captured). Superpixel demosaic (one RGB pixel per 2x2 Bayer cell), black = OB mean, grey-world balance, gamma 2.2,
resized to the crop's sensor aspect (merged readouts are anisotropic). A preview, not a colour reference.

    preview.py backfill DIR...     write preview.jpg next to every kept frame (frame.raw / .zst) under DIR
    preview.py classes             class-level previews from other experiments -> captures/class_shots/
    preview.py full DIR...         preview_full.jpg next to every kept lit frame: the readout's own pixel grid (no
                                   resize, no aspect fix), bilinear demosaic (user 2026-10-24: original-size previews)
"""
import json, pathlib, sys
import numpy as np

WIDTH = 480


def make(frame, top, out_h, aspect, path, ob=None):
    from PIL import Image
    a = frame[top:top + out_h, 16:-16].astype(np.float32)
    # Bayer phase: the two greens are the pair of diagonal sites that agree best; if that is (0,0)/(1,1) the frame
    # starts one column off (h3 / 2F frames do) -> drop a column. R/B order is assumed RGGB after that.
    t = a[:a.shape[0] // 2 * 2, :a.shape[1] // 2 * 2]
    if np.mean(np.abs(t[0::2, 0::2] - t[1::2, 1::2])) < np.mean(np.abs(t[0::2, 1::2] - t[1::2, 0::2])):
        a = a[:, 1:]
    a = a[:a.shape[0] // 2 * 2, :a.shape[1] // 2 * 2]
    blk = float(np.mean(ob)) if ob is not None and ob.size else float(np.percentile(a, 0.5))
    a = np.clip(a - blk, 0, None)
    r, g, b = a[0::2, 0::2], (a[0::2, 1::2] + a[1::2, 0::2]) / 2, a[1::2, 1::2]
    rgb = np.stack([r, g, b], -1)
    m = rgb.reshape(-1, 3).mean(0) + 1e-6
    rgb = rgb * (m[1] / m)                                   # grey world
    hi = float(np.percentile(rgb, 99.5)) or 1.0
    rgb = np.clip(rgb / hi, 0, 1) ** (1 / 2.2)
    im = Image.fromarray((rgb * 255 + .5).astype(np.uint8))
    h = max(1, round(WIDTH / aspect))
    im.resize((WIDTH, h), Image.BOX).save(path, quality=80)
    return path


def _box(a, k):
    """same-size 3x3 convolution, reflected edges (numpy only)"""
    P = np.pad(a, 1, mode='reflect'); o = np.zeros_like(a)
    for i in range(3):
        for j in range(3):
            if k[i][j]:
                o += k[i][j] * P[i:i + a.shape[0], j:j + a.shape[1]]
    return o


def make_full(frame, top, out_h, path, ob=None, quality=80):
    """one RGB pixel per output pixel (the frame as the sensor delivered it: a merged readout stays anisotropic),
    bilinear demosaic; same phase / black / grey-world / gamma as make()"""
    from PIL import Image
    a = frame[top:top + out_h].astype(np.float32)
    t = a[:a.shape[0] // 2 * 2, :a.shape[1] // 2 * 2]
    if np.mean(np.abs(t[0::2, 0::2] - t[1::2, 1::2])) < np.mean(np.abs(t[0::2, 1::2] - t[1::2, 0::2])):
        a = a[:, 1:]
    a = a[:a.shape[0] // 2 * 2, :a.shape[1] // 2 * 2]
    blk = float(np.mean(ob)) if ob is not None and ob.size else float(np.percentile(a, 0.5))
    a = np.clip(a - blk, 0, None)
    H, W = a.shape
    mr = np.zeros((H, W), np.float32); mr[0::2, 0::2] = 1
    mb = np.zeros((H, W), np.float32); mb[1::2, 1::2] = 1
    mg = 1 - mr - mb
    kg = [[0, .25, 0], [.25, 1, .25], [0, .25, 0]]
    kc = [[.25, .5, .25], [.5, 1, .5], [.25, .5, .25]]
    rgb = np.stack([_box(a * mr, kc), _box(a * mg, kg), _box(a * mb, kc)], -1)
    m = rgb[::4, ::4].reshape(-1, 3).mean(0) + 1e-6
    rgb *= m[1] / m
    hi = float(np.percentile(rgb[::4, ::4], 99.5)) or 1.0
    Image.fromarray((np.clip(rgb / hi, 0, 1) ** (1 / 2.2) * 255 + .5).astype(np.uint8)).save(path, quality=quality)
    return path


def full(dirs):
    """preview_full.jpg for every config under DIR whose lit pair f/ is kept (skips existing ones)"""
    import resweep as R
    n = 0
    for root in dirs:
        for res in sorted(pathlib.Path(root).glob('*/result.json')):
            d = res.parent; f = d / 'f'
            if (d / 'preview_full.jpg').exists() or not (f / 'frame.raw.zst').exists():
                continue
            if (f / 'frame.raw').exists():                    # a dark pass in flight: frame.raw is its dark frame and
                print('busy', d.name); continue               # decode() would read it before the lit .zst
            try:
                a = json.loads(res.read_text()).get('attrs', {})
                top = a.get('y0', 20); oh = a.get('rows') or a.get('height')
                fr, _ = R.decode(f)
                make_full(fr[0], top, oh, d / 'preview_full.jpg', ob=fr[0][4:max(top - 4 - a.get('y_skip', 0), 6), 16:-16]); n += 1
            except Exception as e:                            # noqa: BLE001
                print('skip', d.name, e)
    print(n, 'full-size previews')


def from_dir(d, top, out_h, aspect, path):
    import resweep as R
    fr, _ = R.decode(d)
    return make(fr[0], top, out_h, aspect, path, ob=fr[0][4:max(top - 4, 6), 16:-16])


def backfill(dirs):
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    n = 0
    for root in dirs:
        for res in pathlib.Path(root).rglob('result.json'):
            d = res.parent
            if (d / 'preview.jpg').exists():
                continue
            f = d / 'f'
            if not ((f / 'frame.raw').exists() or (f / 'frame.raw.zst').exists()):
                continue
            try:
                r = json.loads(res.read_text())
                a = r.get('attrs', {})
                top = a.get('y0', 20); oh = a.get('rows') or a.get('height')
                crop = [int(x) for x in d.name.split('_')[1].split('x')]   # KEY_CWxCH_OWxOH@FPS
                from_dir(f, top, oh, crop[0] / crop[1], d / 'preview.jpg'); n += 1
            except Exception as e:                            # noqa: BLE001
                print('skip', d, e)
    print(n, 'previews')




# ---- class-level frames from other experiments (user 2026-10-23: the validator's own frames were deleted; fill the
# page from runs that used the same generated classes). Only runs with KEEP_WINDOW and a lit scene:
#   rowrange/<key>/dark  (round 14 row-range search, lens open despite the folder name; meta lit=true)
#   fmtw/<key>/f         (rounds 21-22 width presets; the _hNNN HMAX-scan variants are left out)
EXTRA_SRC = (('rowrange', 'dark', '列範圍量測（第 14 輪）'), ('fmtw', 'f', '寬度預設量測（第 21 輪）'))


def class_shots(cap, out):
    import readout_cfg as C
    out.mkdir(parents=True, exist_ok=True)
    done = []
    for src, sub, label in EXTRA_SRC:
        for meta in sorted((cap / src).glob('*/meta.json')):
            d = meta.parent; key = d.name
            m = json.loads(meta.read_text())
            if key not in C.BY_KEY or '_h' in key or not m.get('ok') or m.get('lit') is False:
                continue
            r = C.BY_KEY[key]
            f = d / sub
            if not ((f / 'frame.raw').exists() or (f / 'frame.raw.zst').exists()):
                continue
            oh = m.get('planned') or m.get('out_h')
            jpg = out / f'{key}__{src}.jpg'
            try:
                if not jpg.exists():
                    from_dir(f, m['y0'], oh, max(r['fmt']) * r['mh'] / 4040, jpg)
                done.append(dict(key=key, src=src, label=label, file=jpg.name, rows=oh))
            except Exception as e:                            # noqa: BLE001
                print('skip', d, e)
    (out / 'index.json').write_text(json.dumps(done, indent=1, ensure_ascii=False))
    print(len(done), 'class shots')
    return done


if __name__ == '__main__':
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    if sys.argv[1] == 'backfill':
        backfill(sys.argv[2:])
    elif sys.argv[1] == 'full':
        full(sys.argv[2:])
    elif sys.argv[1] == 'classes':                     # preview.py classes -> captures/class_shots/
        here = pathlib.Path(__file__).resolve().parent
        class_shots(here / 'captures', here / 'captures' / 'class_shots')
