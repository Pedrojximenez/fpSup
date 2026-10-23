#!/usr/bin/env python3
"""Re-sweep of the sensor registers on virtual bases (notes/RESWEEP_DESIGN.md), class A (registers outside the
mode table, written directly).

    resweep.py OUT REG[,REG...] [--bases V1,V2,V3,V4] [--values 00,FF,...] [--refs]

Per register, in one boot (the camera is restarted with fastreboot afterwards: these registers have no known
power-on value and no mode switch rewrites them):
  for each base: vmode.apply(base rows) -> enter magnify (firmware SetImgMode_s) -> for each value:
    write, restart the sensor (0011 0->1), wait, grab a frame pair 'p', wait ~10 frames, grab 'f10',
    DCLP off ('imager dclp_off 1'), grab 'd', DCLP on.
  --refs: before any write, grab the same set with nothing written (the per-boot reference of every base).
Every grab is reduced to stats.npz (block means per CFA phase, temporal noise per block, OB/dark rows, row and
column profiles, high percentiles, receiver status). Raw frames are kept for references and for any point whose
stats differ from the latest reference beyond the noise floor (keep_raw rule); otherwise only stats are kept.
"""
import argparse, json, pathlib, sys, time
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import numpy as np
import bufa_probe as B                                                # noqa: E402
import vmode                                                          # noqa: E402

BASES = {'V1': (10, 0, 12), 'V2': (6, 0, 14), 'V3': (98, 0, 12), 'V4': (8, 0, 12)}   # donor, yend, bits
VALUES = ['00', '01', '02', '04', '08', '10', '20', '40', '80', 'FF']
BLK = 32


def decode(d):
    from decode12 import decode12
    from decode14 import decode14
    m = json.loads((d / 'frame.json').read_text())
    dec = decode14 if m.get('bits') == 14 else decode12
    out = []
    for n in ('frame.raw', 'frame2.raw'):
        raw = None
        if (d / n).exists():
            raw = (d / n).read_bytes()
        elif (d / (n + '.zst')).exists():         # 2026-10-22: old captures were zstd -19 compressed to free disk
            import subprocess
            raw = subprocess.run(['zstd', '-dcq', str(d / (n + '.zst'))], capture_output=True, check=True).stdout
        if raw is not None:
            out.append(dec(raw, m['height'], m['line_words']).astype(np.float32) / (4 if m.get('bits') == 14 else 1))
    return out, m


def first_image_row(a):
    r = a[:, 60:-60].mean(1)
    return int(np.argmax(r > np.median(r[1:4]) + 25))


def stats(d, live=True):
    fr, m = decode(d)
    a = fr[0]
    top = (m.get('window', 0) >> 16) or first_image_row(a)      # the receiver's first image row: fixed per base,
    top -= top % 2                                              # never from the data (a black shift moved it)
    ob, img = a[1:max(top - 1, 2)], a[top:]
    h, w = img.shape[0] // (2 * BLK) * 2 * BLK, img.shape[1] // (2 * BLK) * 2 * BLK
    s = dict(top=top, shape=np.array(img.shape), rowprof=a[:, 40:-40].mean(1), t=time.time())
    pair_ok = False
    if len(fr) > 1:                     # a repeated or torn second frame gives a false temporal noise: reject it
        same = (fr[0][top:] == fr[1][top:]).mean(1)
        content = fr[0][top:].std(1) > 0                # blank rows past the delivered image are equal anyway
        s['pair_same'] = float((same[content] > 0.5).mean()) if content.any() else 1.0
        s['content_rows'] = int(content.sum())
        pair_ok = s['pair_same'] < 0.01
    for i in (0, 1):
        for j in (0, 1):
            p = img[i:h:2, j:w:2]
            s[f'blk{i}{j}'] = p.reshape(p.shape[0] // BLK, BLK, p.shape[1] // BLK, BLK).mean((1, 3))
            s[f'col{i}{j}'] = img[i::2, j::2].mean(0)
            if ob.shape[0] >= 4:
                o = ob[i::2, j::2][:, 20:-20]
                s[f'ob{i}{j}'] = np.array([o.mean(), np.std(np.diff(o, axis=1)) / np.sqrt(2), o.mean(1).std(), o.mean(0).std()])
            if len(fr) > 1 and pair_ok:
                dd = (fr[0][top:][i:h:2, j:w:2] - fr[1][top:][i:h:2, j:w:2]) / np.sqrt(2)
                s[f'tn{i}{j}'] = dd.reshape(dd.shape[0] // BLK, BLK, dd.shape[1] // BLK, BLK).std((1, 3))
    s['p999'] = np.percentile(img, [99, 99.9, 99.99])
    if live:
        s['status'] = np.array([B.P().mem_get(0x301005D8)[0] or 0, B.P().mem_get(0x30100588)[0] or 0])
    elif (d / 'stats.npz').exists():
        s['status'] = np.load(d / 'stats.npz')['status']
    else:
        s['status'] = np.array([0, 0])
    np.savez_compressed(d / 'stats.npz', **s)
    return s


def differs(s, r):
    """quick keep-raw test against the reference of the same base: mean level, OB, noise, geometry."""
    if tuple(s['shape']) != tuple(r['shape']):
        return True
    for k in ('blk00', 'blk01', 'blk10', 'blk11'):
        a, b = s[k], r[k]
        if np.nanmax(np.abs(a - b) / (np.abs(b) + 20)) > 0.04:
            return True
    if ('ob00' in s) != ('ob00' in r):
        return True
    for k in ('ob00', 'ob11'):
        if k in s and k in r and (abs(s[k][0] - r[k][0]) > 3 or abs(s[k][1] - r[k][1]) > 0.15 * r[k][1] + 0.1):
            return True
    if 'tn01' in s and 'tn01' in r and abs(np.median(s['tn01'] / np.maximum(r['tn01'], 1e-3)) - 1) > 0.04:
        return True
    return bool(s['status'][1] != r['status'][1])


class Base:
    def __init__(self, out, name, rows=None, ctx=()):
        import fastsweep as F, l7
        donor, yend, bits = BASES[name]
        self.name, self.bits = name, bits
        vmode.apply(rows or vmode.donor_rows(donor), 10, f'resweep {name} donor {donor}')
        try:
            self.s = F.Session(out, yend, True, 10, min_alloc=48 << 20)
            if bits == 14:
                l7.rewindow(self.s, 1)
            for r, v in ctx:                        # context registers (interaction rounds): written once, they
                self.s.write(r, v)                  # survive the sensor restarts (outside the mode table)
            if ctx:
                self.restart()
        except BaseException:
            vmode.restore(); raise

    def grab_set(self, d):
        s = self.s
        def one(sub, pair):
            s.pair = pair
            ok = s.grab(d / sub)
            if ok and self.bits == 14:
                m = json.loads((d / sub / 'frame.json').read_text()); m['bits'] = 14
                (d / sub / 'frame.json').write_text(json.dumps(m))
            return ok
        if not one('p', False):                         # two separate grabs a frame apart, not s.pair: in the
            return False                                # fast bases the paired grab repeated or tore frame 2
        time.sleep(0.04)
        if one('p2', False):
            (d / 'p2' / 'frame.raw').rename(d / 'p' / 'frame2.raw')
            for q in (d / 'p2').iterdir():
                q.unlink()
            (d / 'p2').rmdir()
        time.sleep(0.15)
        one('f10', False)
        B.P().sh('imager dclp_off 1'); time.sleep(0.12)
        one('d', False)
        B.P().sh('imager dclp_off 0'); time.sleep(0.08)
        return True

    def restart(self):
        self.s.write(0x0011, 0); time.sleep(0.03); self.s.write(0x0011, 1); time.sleep(0.12)

    def close(self):
        try:
            B.P().sh('imager dclp_off 0')
            self.s.close()
        finally:
            vmode.restore()


def drop_raw(d):
    for sub in ('p', 'f10', 'd'):
        for n in ('frame.raw', 'frame2.raw'):
            q = d / sub / n
            if q.exists():
                q.unlink()


def run(out, regs, bases, values, refs, ctx=()):
    import fastsweep as F
    F.cached_assemble()
    log = open(out / 'run.log', 'a')
    say = lambda t: (print(t, flush=True), log.write(t + '\n'), log.flush())
    B.not_recording()
    if ',0008,' not in B.P().sh('imager mode_now'):
        raise SystemExit('start from live view (mode 8)')
    tag = ''.join(f'+{r:04X}={v:02X}' for r, v in ctx)
    for bname in bases:
        bdir = out / (bname + tag)
        bdir.mkdir(parents=True, exist_ok=True)
        todo = [(r, v) for r in regs for v in values if not (bdir / f'{r:04X}' / v / 'p' / 'stats.npz').exists()
                and not (bdir / f'{r:04X}' / v / 'nofail').exists()]
        if not todo and not refs:
            continue
        b = Base(out, bname, ctx=ctx)
        try:
            if refs:
                rd = bdir / f'ref_{time.strftime("%H%M%S")}'
                b.restart()
                if b.grab_set(rd):
                    for sub in ('p', 'f10', 'd'):
                        stats(rd / sub)
                    say(f'{bname} ref {rd.name}')
            refsd = sorted(bdir.glob('ref_*'))
            ref = np.load(refsd[-1] / 'p' / 'stats.npz') if refsd else None
            for r, v in todo:
                d = bdir / f'{r:04X}' / v
                b.s.write(r, int(v, 16)); b.restart(); time.sleep(0.05)
                if not b.grab_set(d):
                    d.mkdir(parents=True, exist_ok=True); (d / 'nofail').write_text('no frame\n')
                    say(f'{bname} {r:04X}={v} NO FRAME'); break
                st = {sub: stats(d / sub) for sub in ('p', 'f10', 'd') if (d / sub / 'frame.json').exists()}
                ch = ref is not None and any(differs(x, ref) for x in st.values())
                if not ch:
                    drop_raw(d)
                say(f'{bname} {r:04X}={v} {"CHANGED" if ch else "."}')
        finally:
            b.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out'); ap.add_argument('regs')
    ap.add_argument('--bases', default='V1,V2,V3,V4'); ap.add_argument('--values', default=','.join(VALUES))
    ap.add_argument('--refs', action='store_true')
    ap.add_argument('--with', dest='ctx', default='', help='context REG=VAL,... written once per base (interactions)')
    a = ap.parse_args()
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    regs = [int(x, 16) for x in a.regs.split(',') if x]
    ctx = [tuple(int(x, 16) for x in e.split('=')) for e in a.ctx.split(',') if e]
    run(out, regs, a.bases.split(','), a.values.split(','), a.refs, ctx)


if __name__ == '__main__':
    main()
