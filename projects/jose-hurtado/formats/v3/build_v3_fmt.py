#!/usr/bin/env python3
"""Jose Hurtado's fpSup-Formats (S16, OG3.5K, OG4K) as one Loader v3 sup:
\\fpSup\\31FMT.BIN.

    [FMT_VERSION=0.6.1] python3 -B build_v3_fmt.py --out /absolute/new/directory \\
        [--formats s16,og35k,og4k] [--card [--lossless]]

projects/jose-hurtado/notes/FORMATS_V3.md.  There is no source: the bytes are
Jose's own (formats-v<FMT_VERSION>/original/, default the newest: 0.6.1),
moved from their fixed addresses into the
sup's block by tools/fmt_layout.py's disassembly.  Nothing of the Formats
stays at a fixed cave address.

  - pieces: the three runs of Jose's coordinates (cave 0xC072FB00.., private
    pack 0xC0793060.., icon packs 0xC07A4BF0..), byte for byte;
  - fixups: every MOVW/MOVT pair and 32-bit word that names a coordinate;
  - claims EXCL (his handlers replay the stock instruction and return to the
    firmware; none chains to a layer below): every firmware section of the
    packages -- hooks, value patches, the cleaners' stock words (claim only) --
    and every firmware word his code writes at run time (claim only), the
    v0.6.1 video clamp's eight words included;
  - his string hook (C05E5B58) is NOT armed: his ids FFFFFFD0..FFFFFFF6 and
    his string table go up as a standard uishare string layer
    (uis_layer_fixed, NESTED_HOOKS.md), named after this file, on the three
    string sites claimed SHARED_UI -- so it stacks with 10LOSS and any other
    uishare sup in either order (2026-10-06);
  - hooks through cave veneers, in Jose's section order;
  - the compositor (the VBIN entry) called once, last.

One sup, not one per format: the core finds a format by its fixed slot inside
the core's own layout (registry 0xC0731240 + 0x40 x slot, picker 0xC072FB00 +
0x180 x (slot-1)), and Loader v3 has no service that lets one sup find
another's block.  --formats picks the slots built in; a slot left out stays
zero, as on a card without that package.

--out DIR writes DIR/31FMT.BIN and build.json; --card makes DIR a whole v3
card with a LOADER.BIN built now by build_v3.py (31FMT needs service version
3), --lossless adds 10LOSS.BIN.  Never writes a camera card.
"""
import argparse
import hashlib
import json
import os
import pathlib
import shutil
import struct
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
PKG = HERE.parent
ROOT = PKG.parents[2]
V3 = ROOT / 'fpSup' / 'fp_usb_shell' / 'v3'
UISHARE = ROOT / 'fpSup' / 'uishare'
sys.path.insert(0, str(PKG / 'tools'))
sys.path.insert(0, str(V3))
sys.path.insert(0, str(V3.parent))
sys.path.insert(0, str(ROOT / 'research' / 'ui' / 'tools' / 'arm_text'))

import fmt_layout as FL                                    # noqa: E402
import build_v3 as BV                                      # noqa: E402

NAME, SUP_ID = '31FMT.BIN', 'FMT6'
# 1: v0.6.0 (EXCL strings); 2: v0.6.0 + uishare string layer; 3: v0.6.1
VERSION = {'0.6.0': 2, '0.6.1': 3}[FL.vbin.VERSION]
TAB_MAGIC, TAB_VERSION, TAB_WORDS = 0x33564D46, 2, 21
EXCL, SHARED_UI = 2, 3
MIN_SVC = 3                                          # svc->self/holder (uishare layers)

# His string hook, read out of his bytes and checked (no source): a Thumb B.W at
# C05E5B58 to C0732D64 (bx pc), then ARM: cmn r1,#0x30 / blo miss; cmn r1,#0xa /
# bhi miss; ... add r1,r1,#0x30; ldr ip,=table; ldr r0,[ip,r1,lsl #2].  So ids
# [FFFFFFD0, FFFFFFF6] answer table[id + 0x30]; everything else replays stock.
# (Also: only while the reader's pool is the stock one or an 'FSPL' copy --
# under uishare v1 it always is; the layer does not test it.)
RESOLVE_SITE, RESOLVE_TO = 0xC05E5B58, 0xC0732D64
STRING_SITES = (0xC05E5B58, 0xC05E61C8, 0xC05E61E0)   # uishare ui/chain.SITES
HIS_RESOLVE = {0xC0732D64: 0xBF004778, 0xC0732D68: 0xE3710030, 0xC0732D70: 0xE371000A,
               0xC0732D94: 0xE2811030, 0xC0732DA4: 0xE79C0101}
HIS_TABLE_LITERAL = 0xC0732DA0
STR_BASE, STR_COUNT = 0xFFFFFFD0, 0xFFFFFFF6 - 0xFFFFFFD0 + 1
HOOK_B, HOOK_BL, HOOK_THUMB_BW = 0, 1, 2
ALIGN = 64

# Firmware words Jose's code writes at run time, from tables in the layout.
REGAPPLY_TABLE, REGAPPLY_CELLS = 0xC0730C10, 48     # regapply: 48 setter cells
DONOR_TABLE, DONOR_ROWS = 0xC0730470, 5             # donor timing records +4..+0x14
PICKER0, PICKER_SLOT, PICKER_ENTRY = 0xC072FB00, 0x180, 0x30


class BuildError(RuntimeError):
    pass


def runtime_words(L):
    """(address, bytes) of firmware words the code writes after load."""
    img = L.img
    cells = [img.word(REGAPPLY_TABLE + 4 * i) for i in range(REGAPPLY_CELLS)]
    donors = [img.word(DONOR_TABLE + 20 * i) for i in range(DONOR_ROWS)]
    if None in cells or None in donors:
        raise BuildError('a runtime table is not in the layout')
    for slot in range(6):
        for e in range(8):
            a = PICKER0 + PICKER_SLOT * slot + PICKER_ENTRY * e
            rec = img.word(a + 0x10)
            if rec and rec not in donors:
                raise BuildError(f'picker {a:#x} writes {rec:#x}, not a known donor')
    rows = [(a, 4) for a in cells] + [(d + 4, 16) for d in donors]
    rows += [(a, 4) for a in clamp_words(L, donors)]
    for a, n in rows:
        if not 0xC0000000 <= a < 0xC2F00000 or a % 4:
            raise BuildError(f'runtime word {a:#x} is not a firmware image word')
    return rows


# v0.6.1: the video clamp (README "NEW IN v0.6.1").  In regapply, read out of
# his bytes and checked: every apply clears bit 3 of [rec+4] and bits 14-15 of
# [rec+0x18] for the four records in the literal table at C07319E0 (to the
# stock values: those bits are clear in the image), then, for a Formats mode,
# sets them in the record of the picked donor:
#     rec = C0B5C638 + ((donor - C0B59500) * 7 >> 2)
CLAMP_CODE = {0xC07318E8: 0xE28F20F0, 0xC07318F8: 0xE3C00008, 0xC0731904: 0xE3C00903,
              0xC0731964: 0xE3093500, 0xC0731968: 0xE34C30B5, 0xC0731970: 0xE0644184,
              0xC0731974: 0xE30C3638, 0xC0731978: 0xE34C30B5, 0xC073197C: 0xE0834124,
              0xC0731984: 0xE3833008, 0xC0731990: 0xE3833903}
CLAMP_TABLE, CLAMP_RECORDS = 0xC07319E0, 4
CLAMP_FIELDS = (4, 0x18)


def clamp_words(L, donors):
    """The firmware words the video clamp writes (none before v0.6.1)."""
    img = L.img
    found = [img.word(a) == w for a, w in CLAMP_CODE.items()]
    if not any(found):
        return []
    if not all(found):
        raise BuildError('a video clamp this builder does not know')
    recs = [img.word(CLAMP_TABLE + 4 * i) for i in range(CLAMP_RECORDS)]
    used = set()
    for slot in range(6):
        for e in range(8):
            d = img.word(PICKER0 + PICKER_SLOT * slot + PICKER_ENTRY * e + 0x10)
            if d:
                used.add(0xC0B5C638 + (((d - 0xC0B59500) * 7) & 0xFFFFFFFF) // 4)
    if not used <= set(recs):
        raise BuildError(f'clamp set on a record it never clears: {sorted(map(hex, used - set(recs)))}')
    stock = FL.IMAGE.read_bytes()
    out = []
    for r in recs:
        for f, bits in zip(CLAMP_FIELDS, (0x8, 0xC000)):
            a = r + f
            if struct.unpack_from('<I', stock, a - 0xC0000000)[0] & bits:
                raise BuildError(f'{a:#x}: the clamp bits are set in the image')
            out.append(a)
    return out


def vbin_order():
    """The firmware sections' order in Jose's VBIN tables (hooks are armed in it)."""
    order = []
    for n in FL.FORMATS:
        for a, _ in FL.vbin.load(n)[1][1:]:
            if a not in order:
                order.append(a)
    return order


def compile_entry(tmp):
    """fmt_v3.c with uishare's string layers (ui_pool.c), one unit, as OG's."""
    sys.path.insert(0, str(UISHARE))
    import build_section
    import elf_text
    tree = tmp / 'tree'
    tree.mkdir()
    unit = build_section.unity(tree)
    unit.write_text(unit.read_text() + f'#include "{HERE / "fmt_v3.c"}"\n')
    obj = tmp / 'fmt_v3.o'
    clang = shutil.which('clang') or 'clang'
    r = subprocess.run([clang, *build_section.CFLAGS, '-I', str(tree), '-I', str(V3),
                        '-c', str(unit), '-o', str(obj)], capture_output=True, text=True)
    if r.returncode:
        raise BuildError('compile failed:\n' + r.stderr)
    text = elf_text.load_text(obj)
    if not text.functions.get('fmt_v3_entry', 0) & 1:
        raise BuildError('fmt_v3_entry missing or not Thumb')
    return text


def plan(formats):
    L = FL.Layout(formats)
    if L.branches:
        raise BuildError(f'B/BL out of a piece: {[hex(b[0]) for b in L.branches][:8]}; '
                         'this builder only relocates MOVW/MOVT and words')
    movws = [w for w, *_ in L.pairs]
    if len(set(movws)) != len(movws) or len({t for _, t, _, _ in L.pairs}) != len(L.pairs):
        raise BuildError('a MOVW or MOVT is shared by two pairs')
    img = FL.IMAGE.read_bytes()
    stock = lambda a, n: img[a - 0xC0000000:a - 0xC0000000 + n]   # noqa: E731

    order = {a: i for i, a in enumerate(vbin_order())}
    claims, hooks, fwmm, fwabs, notes = [], [], [], [], []
    movw_sites = {m: t for m, t in FL.FW_MOVW_MOVT}
    for a, want in HIS_RESOLVE.items():
        if L.img.word(a) != want:
            raise BuildError(f'{a:#x}: not the string hook this builder knows ({L.img.word(a)})')
    table = L.img.word(HIS_TABLE_LITERAL)
    if FL.piece_of(table) is None or not any(x == HIS_TABLE_LITERAL for x, _ in L.abs):
        raise BuildError('the string table literal is not a relocated coordinate')
    strings = (table, STR_COUNT, STR_BASE)
    resolve_seen = False
    for a, b, role in sorted(L.firmware_sections(), key=lambda r: order[r[0]]):
        kind = role[0]
        if kind == 'hook' and a == RESOLVE_SITE:
            if role[1:] != ('B.W', RESOLVE_TO):
                raise BuildError(f'C05E5B58 goes to {role}')
            resolve_seen = True                 # a uishare layer instead (strings)
            continue
        if kind == 'hook':
            k = {'B': HOOK_B, 'BL': HOOK_BL, 'B.W': HOOK_THUMB_BW}[role[1]]
            hooks.append((a, role[2], k))
            claims.append((a, stock(a, 4), EXCL, None, 'hook'))
        elif kind == 'stock':
            claims.append((a, stock(a, len(b)), EXCL, None, 'stock word (cleaner)'))
        elif kind == 'fw_abs':
            fwabs.append((a, role[1]))
            claims.append((a, stock(a, 4), EXCL, None, 'firmware pointer to a coordinate'))
        elif kind == 'fw_movw_movt':
            if a in movw_sites:
                t = movw_sites[a]
                mw, = struct.unpack('<I', b)
                mt, = struct.unpack('<I', L.secs[t])
                fwmm.append((a, t, mw, mt))
            claims.append((a, stock(a, 4), EXCL, None, 'firmware MOVW/MOVT of a coordinate'))
        else:
            claims.append((a, stock(a, len(b)), EXCL, b, 'value'))
    held = [(a, a + len(s)) for a, s, *_ in claims]
    for a, n in runtime_words(L):
        if any(lo <= a and a + n <= hi for lo, hi in held):
            continue                            # a section already claims it
        claims.append((a, stock(a, n), EXCL, None, 'written at run time'))
    if not resolve_seen:
        raise BuildError('no string hook at C05E5B58 in the packages')
    for a in STRING_SITES:
        claims.append((a, stock(a, 4), SHARED_UI, None, 'uishare string layer site'))
    spans = sorted((a, a + len(s)) for a, s, *_ in claims)
    if any(e > a for (_, e), (a, _) in zip(spans, spans[1:])):
        raise BuildError('two claims overlap')
    for a, s, _, new, _ in claims:
        if len(s) % 4 or a % 4:
            raise BuildError(f'{a:#x}: claims are whole words')
    return L, claims, hooks, fwmm, fwabs, strings


def build(formats, tmp):
    L, claims, hooks, fwmm, fwabs, strings = plan(formats)
    text = compile_entry(tmp)
    hdr = BV.SL_HEADER_LEN
    tab_off = hdr
    rows_off = tab_off + 4 * TAB_WORDS
    # rows: pieces, claims (+ data), abs, mm, fwmm, fwabs, hooks
    piece_rows_off = rows_off
    claim_off = piece_rows_off + 12 * len(FL.PIECES)
    data_off = claim_off + 20 * len(claims)
    data = b''
    crows = []
    for a, s, kind, new, _ in claims:
        so = data_off + len(data)
        data += s
        no = 0
        if new is not None:
            no = data_off + len(data)
            data += new
        crows.append((a, len(s), kind, so, no))
    abs_off = data_off + len(data)
    mm_off = abs_off + 4 * len(L.abs)
    fwmm_off = mm_off + 8 * len(L.pairs)
    fwabs_off = fwmm_off + 16 * len(fwmm)
    hook_off = fwabs_off + 8 * len(fwabs)
    code_off = (hook_off + 12 * len(hooks) + 3) & ~3
    p_off, cur = [], code_off + len(text.code)
    for a, b in FL.PIECES:
        cur = (cur + ALIGN - 1) & ~(ALIGN - 1)
        cur += (a - cur) % ALIGN                   # same address mod ALIGN as Jose's
        p_off.append(cur)
        cur += b - a
    file_len = (cur + 3) & ~3
    scratch_off = file_len
    block = (scratch_off + 4 * len(hooks) + 63) & ~63

    def boff(c):
        k = FL.piece_of(c)
        return p_off[k] + c - FL.PIECES[k][0]

    out = bytearray(file_len)
    tab = struct.pack(f'<{TAB_WORDS}I', TAB_MAGIC, TAB_VERSION,
                      len(FL.PIECES), piece_rows_off, len(claims), claim_off,
                      len(L.abs), abs_off, len(L.pairs), mm_off,
                      len(fwmm), fwmm_off, len(fwabs), fwabs_off,
                      len(hooks), hook_off, FL.ENTRY, scratch_off, *strings)
    out[tab_off:tab_off + len(tab)] = tab
    pr = b''.join(struct.pack('<3I', a, b - a, p_off[k]) for k, (a, b) in enumerate(FL.PIECES))
    out[piece_rows_off:piece_rows_off + len(pr)] = pr
    cr = b''.join(struct.pack('<5I', *r) for r in crows)
    out[claim_off:claim_off + len(cr)] = cr
    out[data_off:data_off + len(data)] = data
    ab = b''.join(struct.pack('<I', boff(a)) for a, _ in L.abs)
    out[abs_off:abs_off + len(ab)] = ab
    mm = b''.join(struct.pack('<2I', boff(w), boff(t)) for w, t, _, _ in L.pairs)
    out[mm_off:mm_off + len(mm)] = mm
    fm = b''.join(struct.pack('<4I', *r) for r in fwmm)
    out[fwmm_off:fwmm_off + len(fm)] = fm
    fa = b''.join(struct.pack('<2I', *r) for r in fwabs)
    out[fwabs_off:fwabs_off + len(fa)] = fa
    hk = b''.join(struct.pack('<3I', *r) for r in hooks)
    out[hook_off:hook_off + len(hk)] = hk
    out[code_off:code_off + len(text.code)] = text.code
    for s, b in L.img.secs:
        o = boff(s)
        out[o:o + len(b)] = b
    body = bytes(out[hdr:])
    entry = code_off + text.functions['fmt_v3_entry']
    sup = BV.make_sup(body, entry, SUP_ID, VERSION, block_size=block, min_svc=MIN_SVC)
    if len(sup) != file_len:
        raise BuildError('the file is not the length the table says')
    facts = {
        'file': NAME, 'sup_id': SUP_ID, 'formats': list(formats),
        'file_len': file_len, 'block': block, 'entry_off': entry, 'code_off': code_off,
        'text': len(text.code), 'pieces': [{'coord': f'0x{a:08X}', 'bytes': b - a,
                                            'block_off': p_off[k]}
                                           for k, (a, b) in enumerate(FL.PIECES)],
        'summary': L.summary(), 'claims': len(claims), 'hooks': len(hooks),
        'strings': {'table': f'0x{strings[0]:08X}', 'count': strings[1],
                    'base': f'0x{strings[2]:08X}'},
        'claims_list': [{'address': f'0x{a:08X}', 'bytes': len(s),
                         'kind': {EXCL: 'EXCL', SHARED_UI: 'SHARED_UI'}[k],
                         'writes': new is not None, 'why': why}
                        for a, s, k, new, why in claims],
        'hooks_list': [{'site': f'0x{s:08X}', 'to': f'0x{t:08X}',
                        'kind': ('B', 'BL', 'Thumb B.W')[k]} for s, t, k in hooks],
        'fw_movw_movt': [f'0x{a:08X}' for a, *_ in fwmm],
        'fw_abs': [f'0x{a:08X}' for a, _ in fwabs],
        'abs_words': [f'0x{a:08X}' for a, _ in L.abs],
        'movw_movt': [f'0x{w:08X}' for w, *_ in L.pairs],
        'entry_coord': f'0x{FL.ENTRY:08X}',
        'jose_version': FL.vbin.VERSION, 'sup_version': VERSION, 'min_svc': MIN_SVC,
        'clamp_words': [f'0x{a:08X}' for a in clamp_words(L, [])],
    }
    return sup, facts


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--out', type=pathlib.Path, required=True)
    ap.add_argument('--formats', default=','.join(FL.FORMATS))
    ap.add_argument('--card', action='store_true',
                    help='a whole v3 card: AutoRun, a LOADER.BIN built now (service '
                         'version 3, which 31FMT needs), fpSup/UI/, 31FMT.BIN')
    ap.add_argument('--lossless', action='store_true',
                    help='with --card: also 10LOSS.BIN, built now from fpSup/lossless')
    a = ap.parse_args()
    formats = tuple(x for x in a.formats.split(',') if x)
    bad = set(formats) - set(FL.FORMATS)
    if bad or not formats:
        raise SystemExit(f'--formats: choose from {",".join(FL.FORMATS)}')
    out = a.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f'{out} is not empty: this never overwrites a build or a card')
    with tempfile.TemporaryDirectory(prefix='fmtv3-') as t:
        sup, facts = build(formats, pathlib.Path(t))
    out.mkdir(parents=True, exist_ok=True)
    if a.card:
        with tempfile.TemporaryDirectory(prefix='fmtcard-') as t:
            sp = pathlib.Path(t) / NAME
            sp.write_bytes(sup)
            r = subprocess.run([sys.executable, '-B', str(V3 / 'build_v3.py'), '--out', str(out),
                                '--sup', str(sp)], capture_output=True, text=True)
            if r.returncode:
                raise SystemExit('build_v3.py failed:\n' + r.stderr[-2000:])
        if a.lossless:
            sys.path.insert(0, str(ROOT / 'fpSup' / 'lossless'))
            import build_v3_lossless as LS
            with tempfile.TemporaryDirectory(prefix='fmtloss-') as t:
                (out / 'fpSup' / '10LOSS.BIN').write_bytes(LS.sup_file(pathlib.Path(t))[0])
        lines = [f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(out)}'
                 for p in sorted(out.rglob('*')) if p.is_file() and p.name != 'MANIFEST.sha256']
        (out / 'MANIFEST.sha256').write_text('\n'.join(lines) + '\n')
    else:
        (out / NAME).write_bytes(sup)
    sources = [pathlib.Path(__file__), HERE / 'fmt_v3.c', PKG / 'tools' / 'fmt_layout.py',
               V3 / 'sloader.h', UISHARE / 'ui_pool.c', UISHARE / 'ui_pool.h',
               UISHARE / 'ui_strings_code.h'] + [FL.vbin.ORIG / FL.vbin.FORMATS[n] / 'fpSup.BIN'
                                    for n in FL.FORMATS]
    meta = {'file': NAME, 'sha256': hashlib.sha256(sup).hexdigest(), 'facts': facts,
            'sources': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in sources}}
    (out / 'build.json').write_text(json.dumps(meta, indent=1) + '\n')
    print(f'{NAME}: {len(sup)} B, block {facts["block"]} B, {facts["claims"]} claims, '
          f'{facts["hooks"]} hooks, {facts["summary"]}')


if __name__ == '__main__':
    main()
