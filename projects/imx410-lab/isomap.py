#!/usr/bin/env python3
"""Stock ISO -> sensor gain / HCG / SoC digital gain (user, 2026-10-22: cdng 12-bit base 100/3200, others 100/640;
the community's reference is ISO 800).

    isomap.py OUT [--max 60]
For each SetIso index (menu value, a legal stock setting; the original is put back at the end): set it, let AE settle,
log the sensor bus (IMXB) for ~0.4 s and keep the last value of each gain-related register, plus the SoC digital
gain 0x300F0310 (Q8.8) and `imager mode_now` gain/shutter. Live view only, nothing written to the card.
"""
import argparse, json, pathlib, sys, time
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bufa_probe as B                                                # noqa: E402

REGS = (0x003D, 0x003E, 0x003F, 0x0040, 0x05E1, 0x041F, 0x05E2, 0x05A6, 0x05A8, 0x0005, 0x0006, 0x0055)


def mode_now():
    r = B.P().sh('imager mode_now')
    for line in r.splitlines():
        if line.startswith('shutter'):
            return line.strip()
    return ''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out'); ap.add_argument('--max', type=int, default=60)
    a = ap.parse_args()
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    B.not_recording()
    orig = B.P().sh('menu SetIso').strip().splitlines()[-1].strip()
    st = B.bus_state(); rows = []
    try:
        isos = [100, 125, 160, 200, 250, 320, 400, 500, 640, 800, 1000, 1250, 1600, 2000, 2500, 3200, 4000, 5000,
                6400, 8000, 10000, 12800, 16000, 20000, 25600]
        for n in isos:
            B.P().sh(f'menu SetIso {n}')
            got = B.P().sh('menu SetIso').strip().splitlines()[-1].strip()
            time.sleep(1.2)
            B.bus_on(st); time.sleep(0.4)
            ents = B.bus_dump(st)
            v = {}
            for _, r, val, _ in ents:
                if r in REGS:
                    v[f'{r:04X}'] = val
            g = v.get('003D', 0) | v.get('003E', 0) << 8
            dg = B.P().mem_get(0x300F0310)[0]
            row = dict(index=n, readback=got, analog_code=g,
                       analog_db=round(20 * __import__('math').log10(4095 / (4095 - g)), 2) if g < 4095 else None,
                       hcg=v.get('05E1'), soc_dgain=(dg & 0xFFFF) / 256 if dg is not None else None, regs=v, mode_now=mode_now())
            rows.append(row)
            print(f"SetIso {n} (readback {got}): analog {row['analog_db']} dB code {g}  HCG {row['hcg']}  SoC dgain {row['soc_dgain']}  {row['mode_now']}", flush=True)
            (out / 'isomap.json').write_text(json.dumps(rows, indent=1))
    finally:
        B.P().sh(f'menu SetIso {orig}')
        print('restored SetIso', B.P().sh('menu SetIso').strip().splitlines()[-1], flush=True)


if __name__ == '__main__':
    main()
