#!/usr/bin/env python3
"""Offline report for a pcsample capture.  No camera access.

    python3 -B analyze.py captures/LABEL            # reads LABEL.ring + LABEL.json
    python3 -B analyze.py captures/LABEL --top 40 --task CamSch --callers

PC -> function: there is no exported function table for the whole image, so
function starts are taken as every direct call target in the code (ARM BL/BLX,
Thumb BL/BLX), plus the vfunc symbols (out/symbols_vfunc.tsv) and names.tsv.
A sample belongs to the nearest start at or below it.  That is right for any
function somebody calls directly; a function only reached through a pointer
and never listed folds into its predecessor -- the report prints the distance
so a big one is visible.  Names: names.tsv (ours) > vfunc symbols > FUN_xxx.

Task names: tasks.tsv (tid -> name), written by `pcsample.py names` from the
firmware's own tskmon list; falls back to the ids seen in earlier captures.
"""
import argparse, bisect, collections, json, pathlib, struct, sys

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SEG0 = ROOT / 'out' / 'seg0_c0000000.bin'
BASE = 0xC0000000
CACHE = HERE / '.cache' / 'starts.npy'

# Seen in tskmon_top output on 2026-10-12..15 (projects/lossless-sup/validation).
KNOWN_TASKS = {0: '(idle)', 1: 'inittsk', 29: 'LensCycl', 39: 'DrawMgr', 44: 'CamSch',
               45: 'MRecMgr', 54: 'SRecRaw', 61: 'SRecFile', 63: 'FdTsk', 68: 'MANAGER',
               71: 'R2YHDIS', 92: 'AeDev', 94: 'ExtStrb', 124: '_VSHL', 125: 'FPLCODE'}
MODES = {0x10: 'usr', 0x11: 'fiq', 0x12: 'irq', 0x13: 'svc', 0x17: 'abt', 0x1B: 'und', 0x1F: 'sys'}


def call_targets():
    """Every direct call target in seg0, as a sorted uint32 array (cached)."""
    if CACHE.exists() and CACHE.stat().st_mtime > SEG0.stat().st_mtime:
        return np.load(CACHE)
    img = np.frombuffer(SEG0.read_bytes(), dtype=np.uint8)
    n4 = len(img) // 4
    w = img[:n4 * 4].view('<u4').astype(np.int64)
    addr = BASE + np.arange(n4, dtype=np.int64) * 4
    imm = w & 0xFFFFFF
    imm = np.where(imm & 0x800000, imm - 0x1000000, imm)
    bl = ((w & 0x0F000000) == 0x0B000000) & ((w >> 28) != 0xF)
    blx = (w & 0xFE000000) == 0xFA000000
    t_arm = addr[bl] + 8 + imm[bl] * 4
    t_blx = addr[blx] + 8 + imm[blx] * 4 + ((w[blx] >> 24) & 1) * 2
    h = img[:len(img) // 2 * 2].view('<u2').astype(np.int64)
    h1, h2 = h[:-1], h[1:]
    hit = ((h1 & 0xF800) == 0xF000) & ((h2 & 0xC000) == 0xC000)
    h1, h2 = h1[hit], h2[hit]
    pc = BASE + np.nonzero(hit)[0].astype(np.int64) * 2 + 4
    S = (h1 >> 10) & 1
    I1 = 1 - (((h2 >> 13) & 1) ^ S)
    I2 = 1 - (((h2 >> 11) & 1) ^ S)
    off = (S << 24) | (I1 << 23) | (I2 << 22) | ((h1 & 0x3FF) << 12) | ((h2 & 0x7FF) << 1)
    off = np.where(S == 1, off - (1 << 25), off)
    t_thumb = np.where(h2 & 0x1000, pc + off, (pc & ~3) + off)
    allt = np.concatenate([t_arm, t_blx, t_thumb])
    end = BASE + len(img)
    allt = allt[(allt >= BASE) & (allt < end)]
    # keep targets called at least twice, or once from ARM code: Thumb pairs
    # decoded at random data offsets are the noise source.
    u, cnt = np.unique(allt, return_counts=True)
    arm_set = np.unique(np.concatenate([t_arm, t_blx]))
    keep = (cnt >= 2) | np.isin(u, arm_set)
    out = u[keep].astype(np.uint32)
    CACHE.parent.mkdir(exist_ok=True)
    np.save(CACHE, out)
    return out


def load_names():
    names = {}
    vf = ROOT / 'out' / 'symbols_vfunc.tsv'
    if vf.exists():
        for line in vf.read_text().splitlines():
            p = line.split('\t')
            if len(p) >= 3:
                names.setdefault(int(p[0], 16), p[2])
    own = HERE / 'names.tsv'
    if own.exists():
        for line in own.read_text().splitlines():
            if line.strip() and not line.startswith('#'):
                a, n = line.split('\t', 1)
                names[int(a, 16) & ~1] = n.strip()
    return names


class Symbolizer:
    def __init__(self):
        self.names = load_names()
        starts = set(int(x) for x in call_targets()) | set(self.names)
        self.starts = sorted(a & ~1 for a in starts)

    def func(self, pc):
        if not (BASE <= pc < BASE + 0x2EF6E00):
            return None, 0
        i = bisect.bisect_right(self.starts, pc) - 1
        if i < 0:
            return None, 0
        s = self.starts[i]
        return s, pc - s

    def label(self, pc):
        if pc == 0:
            return '-'
        if 0xC072D000 <= pc < 0xC0730000:          # loader/worker/host-tool cave
            return f'cave:{pc:08X}'
        s, d = self.func(pc)
        if s is None:
            return f'outside:{pc:08X}'
        n = self.names.get(s, f'FUN_{s:08x}')
        return n + (f' (+0x{d:X}!)' if d > 0x4000 else '')


def load(stem):
    stem = pathlib.Path(stem)
    meta = json.loads(stem.with_suffix('.json').read_text())
    raw = stem.with_suffix('.ring').read_bytes()
    cap = meta['records']
    idx = meta['ctl']['idx']
    n = min(idx, cap)
    first = idx - n
    recs = []
    for k in range(first, idx):
        recs.append(struct.unpack_from('<4I', raw, (k % cap) * 16))
    return meta, recs


def task_names(meta):
    names = dict(KNOWN_TASKS)
    t = HERE / 'tasks.tsv'
    if t.exists():
        for line in t.read_text().splitlines():
            if line.strip() and not line.startswith('#'):
                a, n = line.split('\t', 1)
                names[int(a)] = n.strip()
    names.update({int(k): v for k, v in meta.get('tasks', {}).items()})
    return names


def pct(n, tot):
    return f'{100 * n / tot:5.1f}%'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('stem')
    ap.add_argument('--top', type=int, default=25)
    ap.add_argument('--task', help='only this task (name or id)')
    ap.add_argument('--callers', action='store_true', help='expand top functions by LR')
    ap.add_argument('--json', help='also write the tables here')
    a = ap.parse_args()

    meta, recs = load(a.stem)
    if not recs:
        sys.exit('no records')
    sym = Symbolizer()
    tnames = task_names(meta)
    tn = lambda t: tnames.get(t, f'tid{t}')

    tot = len(recs)
    times = [r[3] for r in recs]
    span = (times[-1] - times[0]) or 1
    print(f'{tot} samples, {span} ms of current_time, {1000 * tot / span:.0f} samples/s, '
          f'over={meta["ctl"]["over"]} calls={meta["ctl"]["calls"]} via={meta.get("via")}')

    modes = collections.Counter(MODES.get(r[2] & 0x1F, hex(r[2] & 0x1F)) for r in recs)
    thumb = sum(1 for r in recs if r[2] & 0x20)
    masked = sum(1 for r in recs if r[2] & 0x80)
    print('modes', dict(modes), f'thumb={pct(thumb, tot)} irq-masked-at-sample={pct(masked, tot)}')
    if modes.get('irq') or any(m not in ('svc', 'sys', 'usr') for m in modes):
        print('  !! samples outside svc/sys/usr: check C_FRAME (0xC42F1FBC) before trusting PCs')

    if a.task:
        want = int(a.task) if a.task.isdigit() else next(
            (k for k, v in tnames.items() if v == a.task), None)
        recs = [r for r in recs if r[2] >> 8 == want]
        print(f'task {a.task}: {len(recs)} samples ({pct(len(recs), tot)})')
        if not recs:
            return

    by_task = collections.Counter(r[2] >> 8 for r in recs)
    print('\nby task')
    for t, n in by_task.most_common(20):
        print(f'  {pct(n, len(recs))}  {n:7d}  {tn(t)}')

    by_fn = collections.Counter()
    fn_task = collections.defaultdict(collections.Counter)
    callers = collections.defaultdict(collections.Counter)
    for pc, lr, w2, _ in recs:
        f = sym.label(pc)
        by_fn[f] += 1
        fn_task[f][tn(w2 >> 8)] += 1
        if a.callers:
            callers[f][sym.label(lr)] += 1
    print(f'\ntop {a.top} functions')
    for f, n in by_fn.most_common(a.top):
        tasks = ', '.join(f'{k} {v}' for k, v in fn_task[f].most_common(3))
        print(f'  {pct(n, len(recs))}  {n:7d}  {f:48s}  [{tasks}]')
        if a.callers:
            for c, m in callers[f].most_common(4):
                print(f'           {m:7d}  <- {c}')

    if a.json:
        pathlib.Path(a.json).write_text(json.dumps({
            'samples': tot, 'by_task': {tn(t): n for t, n in by_task.items()},
            'by_function': dict(by_fn.most_common(200))}, indent=1))


if __name__ == '__main__':
    main()
