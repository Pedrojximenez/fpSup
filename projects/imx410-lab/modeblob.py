#!/usr/bin/env python3
"""Mode switches in a bus log -> the register blob each one sent.

A mode switch is a burst of writes from the 161-register table writer
(FUN_c03258c8, 0xC03258C8..0xC0326D88) plus whatever follows it
outside the per-frame gain/exposure pair.  Each burst is matched against the
ROM mode table (research/imx410/analysis/imx410_modes.csv) to name the mode.

    modeblob.py captures/modescan
"""
import csv, json, pathlib, sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PER_FRAME = {0x41F, 0x5E2, 0x5A6, 0x5A8, 0x5E1, 0x3D, 0x3E, 0x3F, 0x40, 5, 6, 7, 8}
TABLE_LR = (0xC03258C8, 0xC0326D88)


def rom_modes():
    rows = list(csv.DictReader(open(ROOT / 'research/imx410/analysis/imx410_modes.csv')))
    return {int(r['mode_id']): {int(k[4:], 16): int(v) for k, v in r.items() if k.startswith('reg_')}
            for r in rows}


def bursts(bus):
    """Consecutive runs of non-per-frame writes; each run -> ordered [(reg, val, lr)]."""
    out, cur, last_t = [], [], None
    for e in bus:
        r = int(e['reg'], 16)
        if r in PER_FRAME:
            continue
        t = e['t']
        if cur and t - last_t > 50_000:
            out.append(cur); cur = []
        cur.append((r, int(e['val'], 16), int(e['lr'], 16)))
        last_t = t
    if cur:
        out.append(cur)
    return out


def match(blob, modes):
    regs = {r: v for r, v, lr in blob if TABLE_LR[0] <= lr < TABLE_LR[1]}
    if len(regs) < 100:
        return None, regs, []
    best = sorted(((sum(1 for r, v in regs.items() if m.get(r) == v), mid) for mid, m in modes.items()), reverse=True)
    return best[0][1], regs, best[:3]


def main():
    modes = rom_modes()
    for d in sorted(pathlib.Path(sys.argv[1]).iterdir()):
        if not (d / 'bus.json').exists():
            continue
        bus = json.loads((d / 'bus.json').read_text())
        mn = (d / 'mode_now.txt').read_text() if (d / 'mode_now.txt').exists() else ''
        line = next((l.strip() for l in mn.splitlines() if l[:3].isdigit()), '?')
        print(f'== {d.name}: {line}')
        for b in bursts(bus):
            mid, regs, top = match(b, modes)
            extra = [(f'0x{r:04X}', v) for r, v, lr in b if not TABLE_LR[0] <= lr < TABLE_LR[1]]
            if mid is None:
                print(f'   burst {len(b)} writes (not a table): {extra[:12]}')
                continue
            diff = [(f'0x{r:04X}', v, modes[mid].get(r)) for r, v in regs.items() if modes[mid].get(r) != v]
            print(f'   table burst {len(regs)} regs -> mode {mid} (match {top[0][0]}/{len(regs)}; next {top[1:]}); '
                  f'differs from ROM: {diff[:8]}; other writes: {extra[:16]}')


if __name__ == '__main__':
    main()
