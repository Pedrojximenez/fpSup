#!/usr/bin/env python3
"""The verified-mode list for Res-Custom2 (user 2026-10-24: Res-Custom2 reads a list, it does not guess).

    export_modes.py [--db captures/full_v1.json] [--out export/modes_verified.json]

A mode is listed only if the generator still produces it (smc_validate.all_set), its light pass passed (every check,
incl. the offline cols / top_exposed / colour ones) and its class is not excluded below. Each entry carries what the
camera side needs: the sensor writes on top of the donor mode, the SoC timing, the output geometry, the ISP-side
attrs (smc.attrs_from_plan) and the validation status. The full mode-table rows are rebuilt on the host from
(key, crop, out, fps) with readout_cfg.plan + smc.create -- they are not copied here (about 25 KB per mode).
"""
import argparse, json, pathlib, sys, time
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / 'offline'))
import readout_cfg as C, smc, smc_validate as V

AD = {'14': 14, 'normal': 12, 'fast': 11}

RULES = {
    'exposure': 'exposure_lines = VMAX - 2*SHS (all modes, IMX410_RULES §3); SHS >= VMAX/2 = no shutter reset (whole-frame exposure)',
    'line_width': '1x1 format words narrower than 6064 carry fmt_w - 16 real columns; the raster never goes past line_w (§72)',
    'rolling_ms': 'HMAX * receiver_lines / 72 MHz',
    'camera_settings_at_validation': 'ISO 800, shutter 1/30 (smc_validate.CAMERA); dark references measured at ISO 800',
    'excluded': {
        'h3 (3:1 horizontal, no vertical merge)': 'no red / blue: R and B at black (§72); removed from the generator',
        'new V3 windows before 2026-10-24 evening': 'top 14 rows periodically unexposed; fixed by a 16-row margin (§76) -- only results run with y_skip = 16 are listed',
        'format words other than the listed ones': 'not usable or unknown (§74)',
    },
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', default=str(HERE / 'captures' / 'full_v1.json'))
    ap.add_argument('--out', default=str(HERE / 'export' / 'modes_verified.json'))
    a = ap.parse_args()
    db = json.loads(pathlib.Path(a.db).read_text())
    modes, skipped = [], {}
    for key, crop, outsz, fps in V.all_set():
        p = C.plan(key, *crop, *outsz, fps)
        r = C.BY_KEY[key]
        e = db.get(p['id'], {})
        lt, dk = e.get('light'), e.get('dark')
        if not lt or not lt.get('PASS'):
            skipped[p['id']] = 'light: ' + (','.join(k for k, c in (lt or {}).get('checks', {}).items()
                                                    if not c.get('PASS', True) and k != 'rowphase_v1') or 'not run'); continue
        at = smc.attrs_from_plan(p)
        modes.append(dict(
            id=p['id'], key=key, name=r['name'], bits=r['bits'], ad=AD[r['ad']], merge=[r['mh'], r['mv']],
            crop=list(crop), out=list(outsz), fps=fps or round(p['fps_max'], 3),
            verified=dict(light=True, dark=(bool(dk.get('PASS')) if dk else None)),
            timing=dict(hmax=p['soc']['hmax'], vmax=p['soc']['vmax'], fps=round(p['fps'], 3), fps_max=round(p['fps_max'], 3),
                        rolling_ms=round(p['rolling_ms'], 3), receiver_lines=p['receiver_lines']),
            sensor_out=dict(fmt_w=p['fmt_w'], line_w=p.get('line_w', p['fmt_w']), raster_w=p['raster_w'], rows=p['out_h'],
                            windowed=dict(p['sensor']).get(0x0003) == 1, y_skip=p.get('y_skip', 0), rwzm=[round(x, 4) for x in p['rwzm']]),
            donor=r['donor'], sensor=[[f'{reg:04X}', f'{val:02X}'] for reg, val in p['sensor']],
            attrs={k: at[k] for k in ('cls', 'hbin', 'vbin', 'vadd', 'width', 'height', 'x0', 'x1', 'y0', 'y1', 'win', 'wstart', 'wh')},
        ))
    doc = dict(generated=time.strftime('%Y-%m-%d %H:%M'), source=pathlib.Path(a.db).name, rules=RULES,
               counts=dict(listed=len(modes), dark_verified=sum(1 for m in modes if m['verified']['dark']),
                           dark_not_run=sum(1 for m in modes if m['verified']['dark'] is None), skipped=len(skipped)),
               modes=modes, skipped=skipped)
    out = pathlib.Path(a.out); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=1, ensure_ascii=False))
    print(out, doc['counts'])


if __name__ == '__main__':
    main()
