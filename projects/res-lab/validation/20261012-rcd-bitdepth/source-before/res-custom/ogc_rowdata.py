#!/usr/bin/env python3
"""One OpenGate format's recording data, from og3k_plan, as JSON on stdout.

    OG_TARGET=og3k python3 -B ogc_rowdata.py [PACK_OUT]

With PACK_OUT, also writes the format's private NBR pack there (the three
Quick Set / Settings images named "<LABEL>_QS/_SET/_FONT", and the
font_S_imageSize_* the stock lacks: build_og3k_ui_candidate.assets).

og3k_plan reads OG_TARGET when it is imported, so the multi-format core's
builder (build_v3_rescustom.py) runs this once per format in its own process.
Nothing here is new data: every number is what today's OpenGate card uses
(og3k_plan TARGETS, FMT_*, fmt_timing, engine_fps, CANVAS_REC/CANVAS_PB).
"""
import json
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
os.environ.pop('OG_V3', None)
os.environ.pop('OG_CHAIN', None)
import og3k_plan as P                                       # noqa: E402
import ogc_layout as L                                      # noqa: E402

# The virtual table (2026-10-07, user decision): an entry's own canvas pairs.
# Stock FHD100 (p178) differs from FHD30 (p175) in +0x30 (our engfps already
# gives 50.0) and +0xB0 (1 vs 0): OG3K100 gets +0xB0 = 1 as the stock 100p has.
ENT_CANVAS = {'OG3K100': [(0xB0, 1)], 'OG2K100': [(0xB0, 1)]}   # OG2K100: the user, 2026-10-07

# v3 (2026-10-08, user): a format is its modes, each with the fastest rate it is used
# for; the core times every rate (ogc_layout.solve).  (donor, fastest fps x 100, hmax,
# PAL hmax (0 = hmax), x).  The fastest rate is the mode's own ceiling with its stock
# vblank: 72 MHz / (hmax x (rows + vblank)) -- imx410_full.Registry, checked by the tests.
#   OG3K: M98 (3032x2012, vblank 40) 78.84 fps; its PAL rates on hmax 450 as the stock
#         PAL modes of that raster; 100p on M117 (hmax 330, vblank 70) 104.79 fps
#   OG2K: M139 (2016x1344, vblank 100) 112.04 fps
MODES = {'og3k': [(98, 7884, 445, 450, 4), (117, 10479, 330, 0, 4)],
         'og2k': [(139, 11204, 445, 0, 6)]}
RATE_CANVAS = {'og3k': [{'rank': 10000, 'crop': 0, 'base_profile': 0, 'pairs': [(0xB0, 1)]}],
               'og2k': [{'rank': 10000, 'crop': 0, 'base_profile': 0, 'pairs': [(0xB0, 1)]}]}


def v3(row):
    """A v1/v2 row (per-rate entries) as v3: its modes (donor, the fastest rate it
    timed, the hmax and x it used) and its entries' canvases as rate canvases."""
    lab, ents = row['label'], row['entries']
    modes = []
    for e in ents:
        d = e['donor']
        rank = L.RATE_RANKS[L.RATE_SUFFIX[e['key'][len(lab):].replace('CROP', '')]]
        m = next((m for m in modes if m[0] == d), None)
        if m is None:
            modes.append([d, rank, e['w0'] & 0xFFFF, 0, e['w1'] >> 16])
        else:
            m[1] = max(m[1], rank)
    rc, by = [], {}
    for ec in row.get('ent_canvas', []):
        e = ents[ec['entry']]
        crop = int(e['key'].endswith('CROP'))
        rank = L.RATE_RANKS[L.RATE_SUFFIX[e['key'][len(lab):].replace('CROP', '')]]
        by.setdefault((crop, ec.get('base_profile', 0), tuple(ec['pairs'])), []).append(rank)
    for (crop, bp, pairs), ranks in by.items():
        every = {L.RATE_RANKS[L.RATE_SUFFIX[e['key'][len(lab):].replace('CROP', '')]]
                 for e in ents if int(e['key'].endswith('CROP')) == crop}
        for rank in ([0] if set(ranks) == every else ranks):
            rc.append({'rank': rank, 'crop': crop, 'base_profile': bp, 'pairs': list(pairs)})
    out = {k: v for k, v in row.items() if k not in ('entries', 'ent_canvas', 'maxrate')}
    out['modes'] = [tuple(m) for m in modes]
    out['rate_canvas'] = rc
    return out

RATE_FPS = {"23_98": 24, "24": 24, "25": 25, "30": 30, "48": 48, "50": 50,
            "60": 60, "100": 100, "120": 120}


def jose(name, pack_out):
    """S16 / OG3.5K / OG4K (jose_formats.py) with their pack, the same shape."""
    import jose_formats as J
    out = v3(dict(J.ROWS[name]))
    if pack_out:
        import tempfile
        import build_og3k_ui_candidate as B
        lab = out['label']
        # the tiles draw the format's own text; the imageSize fonts follow its act size
        B.PLAN_TARGET = {'label': out['tile_text'], 'act': tuple(out['act'])}
        with tempfile.TemporaryDirectory(prefix='rcpack-') as d:
            pack, _ = B.assets(pathlib.Path(d), names={'OG3K_QS': lab + '_QS', 'OG3K_SET': lab + '_SET',
                                                       'OG3K_FONT': lab + '_FONT'})
        pathlib.Path(pack_out).write_bytes(pack)
        out['pack_bytes'] = len(pack)
    json.dump(out, sys.stdout)


def main():
    if '--jose' in sys.argv:
        i = sys.argv.index('--jose')
        name = sys.argv[i + 1]
        rest = [a for k, a in enumerate(sys.argv[1:], 1) if k not in (i, i + 1)]
        return jose(name, rest[0] if rest else None)
    t = P.T
    rec = {k: v for k, v in P.CANVAS_REC.items() if k not in (0x80,)}
    out = {'target': P.TARGET, 'label': t['label'], 'profile': t['profile'],
           'rec': list(t['rec']), 'act': list(t['act']),
           'canvas_rec': sorted(rec.items()), 'canvas_pb': sorted(P.CANVAS_PB.items()),
           'prev_h': P.PREV_ON if P.WITH_PREV else 0,
           'prev_profiles': [5, 210, 227, 257, 258, 259],
           'prev_cells': P.PREV,
           'enum': P.OG_ENUMS[P.TARGET],
           # video clamp on the donor's receiver row (VIDEO_CLAMP_V3.md): today's v3 core does it
           'clamp': 1,
           # §12: the stock resolution this format records under (the setting only ever holds 2/3)
           'stock_value': {'og3k': 2, 'og2k': 2, 'hsw': 2, 'og6k': 3}[P.TARGET],
           # §13/§14 UI: the Settings row text and the collapsed summary
           'row_text': '%s %dx%d' % (t['label'], t['act'][0], t['act'][1]),
           'summary': t['label'],
           'modes': MODES[P.TARGET], 'rate_canvas': RATE_CANVAS[P.TARGET],
           'flags': L.RFLAG_CLAMP}
    if len(sys.argv) > 1:
        import tempfile
        import build_og3k_ui_candidate as B
        lab = t['label']
        with tempfile.TemporaryDirectory(prefix='rcpack-') as d:
            pack, _ = B.assets(pathlib.Path(d), names={'OG3K_QS': lab + '_QS', 'OG3K_SET': lab + '_SET',
                                                       'OG3K_FONT': lab + '_FONT'})
        pathlib.Path(sys.argv[1]).write_bytes(pack)
        out['pack_bytes'] = len(pack)
    json.dump(out, sys.stdout)


if __name__ == '__main__':
    main()
