#!/usr/bin/env python3
"""14-bit `0001` sweep (2026-10-22, IMX410_RULES §67): the format words §43 found outside the stock tables under
12-bit, now with the 14-bit Family A, HMAX 911 and the 14-bit receiver -- is any of them a 14-bit word at another
width or speed? Direct writes from mode 10 (bins.run), two frames, the firmware restores the table.
The readout-matrix classes themselves are in readout_cfg (new=True) and go through readout_batch.py --set matrix.

    matrix.py list | run OUT [NAME ...]
"""
import json, pathlib, subprocess, sys
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bins, l7

CELLS = {}          # name -> (h, v, ad, regs, hmax, rx, yend, rx14, base)
# 14-bit `0001` sweep (§43 found these outside the stock tables under 12-bit): 14-bit Family A, 14-bit receiver
for w in (0x01, 0x03, 0x15, 0x16, 0x18, 0x1A, 0x1B, 0x2B, 0x3A, 0x3D, 0x3E):
    CELLS[f'w14_{w:02X}'] = (1, 1, '14', bins.FAM14 + [(0x0001, w)], 911, None, 0, True, 10)

# 12-bit format scan (2026-10-23, goal: every mode with a proper Bayer output): words with an image in §43 that the
# generator does not use, Z CAM's strip / v-6 words, and 2C (4176) under the normal AD. Mode-10 window kept; VMAX
# raised to 3000 lines so 2086-row words (3D/3E) fit in one frame.
W12 = (0x2C, 0x18, 0x03, 0x01, 0x16, 0x3D, 0x3E, 0x34, 0x35, 0x36, 0x31)
for w in W12:
    CELLS[f'w12_{w:02X}'] = (1, 1, '12', [(0x0001, w)], 445, None, 0, False, 10)
SOC12 = [(0x30100020, (3000 - 1) << 16)]
CONTROLS = ['m10_1x1']
FRESH = False
ORDER = CONTROLS + list(CELLS) + ['m10_end']


def register():
    for n, (h, v, ad, regs, hm, rx, ye, r14, base) in CELLS.items():
        bins.V[n] = (regs, hm, rx, ye, r14)
        if base != 10:
            bins.BASEMODE[n] = base
        if n.startswith('w12_'):
            bins.SOC[n] = SOC12


register()


def run(out, names):
    out.mkdir(parents=True, exist_ok=True)
    (out / 'cells.json').write_text(json.dumps({n: dict(h=c[0], v=c[1], ad=c[2], hmax=c[4], rx=c[5], yend=c[6], rx14=c[7], base=c[8],
                                                       regs=[f'{r:04X}={x:02X}' for r, x in c[3]]) for n, c in CELLS.items()}, indent=1))

    def focus():                                        # user rule: AF after every (re)boot and at the start
        subprocess.run([sys.executable, 'bufa_probe.py', 'focus', '--hold', '1.0'], cwd=HERE, capture_output=True, timeout=90)
    focus()
    for n in names:
        if (out / 'STOP').exists():
            print('STOP file: stopping', flush=True); break
        if (out / n / 'frame2.raw').exists() or (out / n / 'frame2.raw.zst').exists():
            continue
        if FRESH:                                       # matrix r2: shell wedges after a few configs per boot
            rb = subprocess.run([sys.executable, '-c', 'import sweep; sweep.KEEP=None; sweep.fastreboot()'], cwd=HERE, capture_output=True, timeout=300)
            if rb.returncode:
                print('camera did not come back -- stopping', flush=True); break
            focus()
        try:                                           # sensor temperature before every config (user 10-23: runs hot)
            import thermal
            _t = thermal.wait_cool(); thermal.log(out / 'thermal.jsonl', n)
            print(f"  temp {_t.get('C')}", flush=True)
        except Exception as _e:                        # noqa: BLE001
            print('  temp read failed', _e, flush=True)
        r = subprocess.run([sys.executable, '-u', '-c', f'import matrix, bins, pathlib; bins.run(pathlib.Path({str(out)!r}), {n!r})'],
                           cwd=HERE, capture_output=True, text=True, timeout=600)
        tail = [l for l in r.stdout.splitlines() if l.startswith(n)]
        print(' | '.join(tail) or n, ('ERROR ' + (r.stderr.strip().splitlines() or ['?'])[-1][:160]) if r.returncode else '', flush=True)
        (out / n).mkdir(parents=True, exist_ok=True)
        (out / n / 'log.txt').write_text(r.stdout + '\n--- stderr\n' + r.stderr)
        if r.returncode or 'NO FRAME' in r.stdout:      # bins.run rebooted (or failed): check the camera, refocus
            chk = subprocess.run([sys.executable, '-c', 'import vmode; vmode.check_stock()'], cwd=HERE, capture_output=True, timeout=120)
            if chk.returncode:
                rb = subprocess.run([sys.executable, '-c', 'import sweep; sweep.KEEP=None; sweep.fastreboot()'], cwd=HERE, capture_output=True, timeout=300)
                if rb.returncode:
                    print('camera did not come back -- stopping', flush=True); break
            focus()


if __name__ == '__main__':
    if sys.argv[1] == 'list':
        for n, c in CELLS.items():
            print(f'{n:12s} h{c[0]} v{c[1]} {c[2]:4s} HMAX {c[4]} rx {c[5]} yend {c[6]} base {c[8]}  {len(c[3])} regs')
    elif sys.argv[1] == 'run':
        if '--fresh' in sys.argv:
            sys.argv.remove('--fresh'); FRESH = True
        run(pathlib.Path(sys.argv[2]), sys.argv[3:] or ORDER)
