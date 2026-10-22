#!/usr/bin/env python3
"""What the frame-sync interrupts say about a recorded take.

    python3 -B vd_report.py CLIP_DIR

Reads every DNG's FSG2 block and its Vd (type 3, IRQ 0x79) and IRQ 0x7f
(type 4) events: each is a gyro-stream position (base_idx + pos) and the
TickTimer at the interrupt.  Prints, in gyro samples and in milliseconds:
the Vd period and its jitter, double fires, the frame hook's distance after
the last Vd (the hook's own jitter, Vd taken as the clock), and 0x7f after Vd
next to the readout time.
"""
import pathlib, statistics, sys
import fsg2 as F

EVENT_VD, EVENT_V7F = 3, 4


def main():
    clip = pathlib.Path(sys.argv[1])
    recs = [F.read_frame(p.read_bytes()) for p in sorted(clip.glob('*.DNG'))]
    period_ms = recs[0]['period_ps'] * 1e-9
    vd, x7f, hooks = [], [], []
    for r in recs:
        for pos, kind, v in r['events']:
            g = r['base_idx'] + pos
            tick = int.from_bytes(v, 'little')
            (vd if kind == EVENT_VD else x7f if kind == EVENT_V7F else []).append((g, tick, r['frame_seq']))
        hooks.append((r['base_idx'] + r['n_samples'], r['frame_seq']))
    print(f'{clip.name}: {len(recs)} frames, {len(vd)} Vd, {len(x7f)} 0x7f, readout {recs[0]["readout_ns"] / 1e6:.3f} ms')
    if len(vd) < 3:
        print('  too few Vd events: the hook did not fire or was not claimed')
        return

    def ms(samples):
        return samples * period_ms

    gaps = [b[0] - a[0] for a, b in zip(vd, vd[1:])]
    nominal = statistics.median(gaps)
    doubles = [g for g in gaps if g < nominal * 0.5]
    clean = [g for g in gaps if g >= nominal * 0.5]
    print(f'  Vd period: median {nominal:.2f} samples = {ms(nominal):.3f} ms; '
          f'jitter rms {statistics.pstdev(clean):.2f} samples = {ms(statistics.pstdev(clean)):.3f} ms; '
          f'double fires {len(doubles)} (gaps {sorted(set(doubles))[:8]})')
    tgaps = [((b[1] - a[1]) & 0xFFFFFFFF) for a, b in zip(vd, vd[1:]) if b[0] - a[0] >= nominal * 0.5]
    print(f'  Vd period by TickTimer: median {statistics.median(tgaps) / 1000:.3f} ms, rms {statistics.pstdev(tgaps) / 1000:.3f} ms')

    # The frame hook against the newest real Vd before it.
    real = [v for i, v in enumerate(vd) if i == 0 or v[0] - vd[i - 1][0] >= nominal * 0.5]
    lag, j = [], 0
    for h, _ in hooks:
        while j + 1 < len(real) and real[j + 1][0] <= h:
            j += 1
        if real[j][0] <= h:
            lag.append(h - real[j][0])
    if lag:
        print(f'  hook after the last Vd: mean {ms(statistics.mean(lag)):.2f} ms, rms {ms(statistics.pstdev(lag)):.2f} ms, '
              f'min {ms(min(lag)):.2f}, max {ms(max(lag)):.2f}')
        print(f'  (measured from the footage: the first row is read {13.35:.2f} ms before the hook on average)')

    if x7f:
        after, j = [], 0
        for g, _, _ in x7f:
            while j + 1 < len(real) and real[j + 1][0] <= g:
                j += 1
            if real[j][0] <= g:
                after.append(g - real[j][0])
        print(f'  0x7f after the last Vd: mean {ms(statistics.mean(after)):.3f} ms, rms {ms(statistics.pstdev(after)):.3f} ms '
              f'(readout {recs[0]["readout_ns"] / 1e6:.3f} ms, frame {ms(nominal):.3f} ms)')


if __name__ == '__main__':
    main()
