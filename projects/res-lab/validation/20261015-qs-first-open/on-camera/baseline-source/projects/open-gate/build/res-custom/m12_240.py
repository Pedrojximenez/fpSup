"""M12 / p13 square-pixel 240p recipe for the shared virtual-table consumer.

The 25 geometry pairs come from the September 29 H2 live readback, audited in
projects/res-lab/validation/20261011-virtual-rate-context-live/success-version-audit.
The 4,809-frame A001_193 supports that predecessor family, but its exact BIN is
unavailable. The reconstructed H2/native30 file later failed sustained capture;
this real-239.76-menu recipe is a new development candidate, not a proven fix.
"""
import struct

import ogc_layout as L
import rcd

LABEL = 'M12240'
RANK = 23976
RAW = (1008, 672)
ACTIVE = (992, 662)
TIMING = (0x014A014A, 0x0006038E)
ARCHIVED_PAIRS = (
    (0x00, 1008), (0x04, 672), (0x0C, 1008), (0x10, 672),
    (0x20, 992), (0x24, 992), (0x28, 662), (0x2C, 662),
    (0x60, 2048), (0x64, 2048), (0x80, 7), (0x84, 7),
    (0x90, 1), (0xB0, 1), (0xC0, 0), (0xD0, 1024), (0xD4, 1024),
    (0xD8, 1008), (0xDC, 1008), (0xE0, 672), (0xE4, 672),
    (0xF4, 1008), (0xF8, 672), (0xFC, 0x40000000), (0x100, 0x40000000),
)


def row_data(tmp, image):
    """Only data and existing UI assets; no new loader or recording engine."""
    import build_og3k_ui_candidate as UI
    # Validate the stock M12 donor independently of the generated entry solver.
    words = lambda at, n: struct.unpack_from('<' + 'I'*n, image, at-0xC0000000)
    donors = [(i, words(0xC0B59500 + 32*i, 8)) for i in range(70)]
    index, native = next((i, w) for i, w in donors if w[0] == 12)
    if native[1:3] != TIMING:
        raise ValueError('M12 firmware timing differs from the archived 240p donor')
    old = UI.PLAN_TARGET
    try:
        UI.PLAN_TARGET = {'label': LABEL, 'act': ACTIVE}
        pack, assets = UI.assets(tmp, names={
            'OG3K_QS': LABEL+'_QS', 'OG3K_SET': LABEL+'_SET',
            'OG3K_FONT': LABEL+'_FONT'})
    finally:
        UI.PLAN_TARGET = old
    row = dict(
        label=LABEL, profile=13, base_row=rcd._base_row(image, 13),
        enum=0x4D313240, stock_value=2, aspect=2, flags=0,
        prev_h=1334, act=ACTIVE, bit_depths=(12,),
        modes=[(12, RANK, 330, 0, 6)],
        canvas_rec=[p for p in ARCHIVED_PAIRS if p[0] != 0xB0],
        canvas_pb=[(0,1008),(4,672),(0xC,1008),(0x10,672),
                   (0x24,992),(0x2C,662),(0xDC,1008),(0xE4,672)],
        rate_canvas=[dict(rank=r, crop=0, base_profile=13,
                          pairs=[(0xB0, int(r != 0))])
                     for r in (10000, 11988, RANK, 0)],
        row_text='M12240 992x662', summary=LABEL, pack=pack,
        provenance=dict(native_mode=12, native_timing_index=index,
                        archived_profile=13, archived_live_pairs=25,
                        assets=assets, hardware_verified=False),
    )
    generated = next(e for e in L.gen_entries(LABEL, row['modes'], 0)
                     if e['rank'] == RANK)
    if (generated['w0'], generated['w1']) != TIMING:
        raise ValueError('240p solver does not reproduce the original M12 timing')
    return row
