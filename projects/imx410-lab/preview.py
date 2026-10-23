#!/usr/bin/env python3
"""Small JPEG previews of validator frames, for the simulator page (user 2026-10-23: link the frames we actually
captured). Superpixel demosaic (one RGB pixel per 2x2 Bayer cell), black = OB mean, grey-world balance, gamma 2.2,
resized to the crop's sensor aspect (merged readouts are anisotropic). A preview, not a colour reference.

    preview.py backfill DIR...     write preview.jpg next to every kept frame (frame.raw / .zst) under DIR
    preview.py classes             class-level previews from other experiments -> captures/class_shots/
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
    elif sys.argv[1] == 'classes':                     # preview.py classes -> captures/class_shots/
        here = pathlib.Path(__file__).resolve().parent
        class_shots(here / 'captures', here / 'captures' / 'class_shots')
