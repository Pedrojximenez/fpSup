#!/usr/bin/env python3
"""Export the readout classes (readout_cfg) and the validation results (captures/smc_validated.json) as one JSON for the
imx410-lab simulator page (sim/imx410_lab_sim.html ports readout_cfg.plan to JS and reads this). Offline only.

    export_sim.py                 -> sim/lab_data.json + sim/imx410_lab_sim.html (links the frames in captures/)
    export_sim.py --site DIR      -> DIR/imx410-lab-sim.html + DIR/imx410-lab-shots/*.jpg (self-contained, for fpSup)
    export_sim.py --site DIR --artifact   -> DIR/imx410_lab_sim.html without the document wrapper (claude.ai artifact)
    --db FILE --cap DIR   results + frames of one pass (default: captures/smc_validated.json + captures/smc_m1)
    --clean               rebuild DIR/imx410-lab-shots from this pass only, no class_shots (user 10-23: once the full
                          pass exists, the old test images go)
"""
import json, pathlib, shutil, sys
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / 'offline'))
import readout_cfg as C

KEEP = ('key', 'name', 'mh', 'mv', 'bits', 'ad', 'donor', 'fmt', 'hmin', 'over', 'centre', 'v016', 'v016_min',
        'rows_full', 'y0', 'new', 'exp', 'ev', 'fast_set', 'extra')
LOWGAIN = {'12h3', 'f12h3'}            # SMC_VERIFY round 16: convex response above gain ~3700 -> low gain only


def arg(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def main():
    classes = []
    for r in C.READOUTS:
        c = {k: r.get(k) for k in KEEP}
        c['extra'] = [list(x) for x in r.get('extra') or []]
        c['fmt'] = {str(w): code for w, code in r['fmt'].items()}
        c['ad'] = {'14': '14', 'normal': '12', 'fast': '11'}[r['ad']]      # 11-bit AD == the fast class (§21)
        c['rows_full'] = C.full_rows(r['key'])
        c['lowgain'] = r['key'] in LOWGAIN
        classes.append(c)
    db = json.loads(pathlib.Path(arg('--db', HERE / 'captures' / 'smc_validated.json')).read_text())
    cap = pathlib.Path(arg('--cap', HERE / 'captures' / 'smc_m1')).resolve()
    clean = '--clean' in sys.argv
    results = {}
    for cid, e in db.items():
        results[cid] = {t: bool(e[t]['PASS']) for t in ('light', 'dark') if t in e and 'PASS' in e[t]}
    site = pathlib.Path(sys.argv[sys.argv.index('--site') + 1]) if '--site' in sys.argv else None
    shots = {}
    if site and clean and (site / 'imx410-lab-shots').exists():
        shutil.rmtree(site / 'imx410-lab-shots')
    for jpg in sorted(cap.glob('*/preview*.jpg')):
        d = jpg.parent.name                               # KEY_CWxCH_OWxOH@FPS -> KEY:CWxCH>OWxOH@FPS
        k, crop, rest = d.split('_', 2)
        cid = f'{k}:{crop}>{rest}'
        if cid not in results:
            continue
        kind = 'd' if jpg.name == 'preview_dark.jpg' else 'l'
        if site and kind == 'd':                          # dark frames are noise JPEGs (~40 KB each): local page only
            continue
        if site:
            rel = f'imx410-lab-shots/{d}{"_dark" if kind == "d" else ""}.jpg'
            (site / 'imx410-lab-shots').mkdir(parents=True, exist_ok=True)
            shutil.copyfile(jpg, site / rel)
        else:
            rel = f'../captures/{cap.relative_to(HERE / "captures")}/{d}/{jpg.name}'
        shots.setdefault(cid, {})[kind] = rel
    class_shots = {}                                      # other experiments, same generated class (preview.py classes)
    cs_dir = HERE / 'captures' / 'class_shots'
    idx = json.loads((cs_dir / 'index.json').read_text()) if (cs_dir / 'index.json').exists() and not clean else []
    for e in idx:
        if site:
            rel = f'imx410-lab-shots/class_{e["file"]}'
            (site / 'imx410-lab-shots').mkdir(parents=True, exist_ok=True)
            shutil.copyfile(cs_dir / e['file'], site / rel)
        else:
            rel = f'../captures/class_shots/{e["file"]}'
        class_shots.setdefault(e['key'], []).append(dict(label=e['label'], src=rel, rows=e['rows']))
    out = dict(clk=C.CLK, vmax_max=C.VMAX_MAX, sensor_h=C.SENSOR_H, win=[C.WIN_TOP, C.WIN_BOTTOM],
               classes=classes, results=results, shots=shots, class_shots=class_shots)
    js = json.dumps(out, separators=(',', ':'), ensure_ascii=False)
    t = (HERE / 'sim' / 'template.html').read_text().replace('__DATA__', js.replace('</', '<\\/'))
    if site and '--artifact' in sys.argv:                  # claude.ai artifact: same paths, the publish adds the skeleton
        (site / 'imx410_lab_sim.html').write_text(t)
    elif site:                                            # fpSup explainers are full documents (no publish skeleton)
        head, body = t.split('<div class="wrap">', 1)
        body = body.replace('<header>', '<header>\n    <a class="back" href="../research.html">← fpSup 研究</a>', 1)
        head = head.replace('<style>', '<style>\n.back { flex-basis: 100%; color: var(--accent); text-decoration: none; font-size: .85rem; }', 1)
        (site / 'imx410-lab-sim.html').write_text(
            '<!doctype html>\n<html lang="zh-Hant">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">\n'
            '<meta name="description" content="IMX410 讀出模式模擬器：AD、合併、寬度預設、裁切與幀率，照 imx410-lab 生成器規則計算，並附實機驗證結果與拍到的畫面。">\n'
            '<link rel="icon" href="../assets/favicon.ico" sizes="any">\n'
            '<link rel="icon" href="../assets/favicon-32.png" type="image/png" sizes="32x32">\n'
            + head + '</head>\n<body>\n<div class="wrap">' + body + '\n</body>\n</html>\n')
    else:
        (HERE / 'sim' / 'lab_data.json').write_text(js)
        (HERE / 'sim' / 'imx410_lab_sim.html').write_text(t)
    print(len(classes), 'classes', len(results), 'configs', len(shots), 'with frames')


if __name__ == '__main__':
    main()
