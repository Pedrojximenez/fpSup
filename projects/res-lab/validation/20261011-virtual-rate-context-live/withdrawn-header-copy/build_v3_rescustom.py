#!/usr/bin/env python3
"""res-custom: the multi-format OpenGate core and its format data files, for Loader v3.

(Was "ogcore" / 32OG.BIN / sup_id OGCO until 2026-10-07; renamed by the user.)

    python3 -B build_v3_rescustom.py --out /absolute/new/directory [--formats og3k,og2k]

notes/OG_MULTIFORMAT_CORE_DESIGN.md §10-§15.  Writes

    32RESCUS.BIN        the core: all the code -- recording (virtual profile +
                        virtual mode, no firmware table is written), the menu
                        (uishare's applier on the core's template), the Quick
                        Set (scheme B), the choice kept in this file (§12)
    RESCUS/<LABEL>.RCD  one data file per format: parameters only (rcd.py);
                        the core reads \fpSup\RESCUS\ at its entry
    build.json

The core is laid out the res-lab way (rl_v3.c / OG_V3_PAIR): the shims are
assembled at a coordinate origin with plain movw/movt pairs, og_pic.py rewrites
the pairs that name the layout PC-relative, and the whole layout is built a
second time at another origin and must come out byte-identical.  The state S
holds offsets, never addresses.  Never writes a camera card.
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
BUILD = HERE.parent
ROOT = BUILD.parent.parent.parent
FPSUP = ROOT / 'fpSup'
V3 = FPSUP / 'fp_usb_shell' / 'v3'
UISHARE = FPSUP / 'uishare'
IMAGE = ROOT / 'out' / 'MAIN_c0000000.bin'
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(BUILD))
import ogc_layout as L                                   # noqa: E402

CHAIN, EXCL, SHARED_UI = 1, 2, 3
HOOK_B, HOOK_BL, HOOK_TW = 0, 1, 2
TAB_MAGIC, TAB_VERSION, TAB_WORDS = 0x3343474F, 6, 29
DATA_BYTES = 0x48000                # the data files, each row's menu block, the 240 B2_5 copy
FOBJ_BYTES = 0x1000                 # a file object + read-back for the BIN write (§12.4)
PAIR_SITES = ((0xC06BDA3C, 8), (0xC06BDA48, 4),   # the resolution converter's movw/movt, mov #n
              (0xC06BDB0C, 8), (0xC06BDB18, 4),   # the frame-rate converter (row <-> internal)
              (0xC06CB6DC, 8), (0xC06CB6E8, 4))   # the frame-rate summary (export -> state)
CORE_NAME, CORE_ID, VERSION = '32RESCUS.BIN', 'RCUS', 13
RCD_DIR = 'RESCUS'
SHIFT = 0x10000000
SPAN = 0x8000                       # the layout must fit og_pic's window
TT = 0xC0B59500                     # the timing table (claimed, never written)
FORMATS = ('og3k', 'og2k', 's16', 'og35k', 'og4k')
JOSE = ('s16', 'og35k', 'og4k')       # jose_formats.py (milestone 5)
GEOMETRY = {'OG3K': 'OG3K 3008x2000', 'OG2K': 'OG2K 2000x1334'}   # the menu sups' row texts


class BuildError(RuntimeError):
    pass


def img():
    return IMAGE.read_bytes()


def word(a, image=None):
    return struct.unpack_from('<I', image or img(), a - 0xC0000000)[0]


def stock(a, n):
    sys.path.insert(0, str(V3))
    import build_v3
    return build_v3.stock(a, n)


# ---- the rows -----------------------------------------------------------------
def row_data(target, tmp):
    jose = target in JOSE
    env = dict(os.environ, OG_TARGET='og3k' if jose else target)
    for k in ('OG_V3', 'OG_CHAIN', 'OG_V3_OGV', 'OG_UISHARE'):
        env.pop(k, None)
    pk = tmp / f'{target}.nbr'
    r = subprocess.run([sys.executable, '-B', str(HERE / 'ogc_rowdata.py'), str(pk)]
                       + (['--jose', target] if jose else []),
                       capture_output=True, text=True, env=env)
    if r.returncode:
        raise BuildError(f'{target} row data:\n' + r.stderr[-3000:])
    d = json.loads(r.stdout)
    d['pack'] = pk.read_bytes()
    if d['label'] in GEOMETRY and d['row_text'] != GEOMETRY[d['label']]:
        raise BuildError(f'{target}: row text {d["row_text"]!r} is not the menu sup\'s')
    image = img()
    base = word(L.MAPPING + 4 * d['profile'], image)
    if base == 0xFFFFFFFF:
        raise BuildError(f'{target}: p{d["profile"]} has no mapping row')
    d['base_row'] = base
    d.setdefault('aspect', 2)               # OG3K / OG2K: 3:2 (the Jose rows say theirs)
    return d


def check_ids(image):
    if len(set(L.VPID_POOL)) != L.MAX_VARS or L.VPID_POOL[:L.MAX_ROWS] != list(range(L.VPID0, L.VPID0 + L.MAX_ROWS)):
        raise BuildError('the virtual profile pool')
    for pid in L.VPID_POOL:
        if word(L.MAPPING + 4 * pid, image) != 0xFFFFFFFF:
            raise BuildError(f'virtual profile {pid}: the mapping slot is not empty')
        for lo, hi in ((0, 4), (5, 11), (17, 40), (101, 129), (131, 198), (301, 312), (401, 434)):
            if lo <= pid <= hi:
                raise BuildError(f'virtual profile {pid} falls in FUN_c043a1c8 class {lo}..{hi}')
    stock_ids = {word(TT + 0x20 * i, image) for i in range(70)}
    for v in range(L.MAX_VMS):
        vid = L.VMID0 + v
        if vid in stock_ids or vid in (0x77, 0x99, 0x9A, 0xB7) or 0xA6 <= vid <= 0xAE or vid >= 250:
            raise BuildError(f'virtual mode {vid} collides')


# ---- the layout ---------------------------------------------------------------
def layout(origin, tmp):
    """(image bytes, shim symbol offsets) at coordinate `origin`: the shims, then
    S's header (the body is filled at the entry, in the zeroed tail)."""
    sys.path.insert(0, str(BUILD))
    import armasm
    import og_pic
    d = tmp / f'lay{origin:x}'
    d.mkdir()
    hdr = L.header()
    if origin != L.LAYOUT0:
        hdr = hdr.replace(f'#define OGC_LAYOUT0 0x{L.LAYOUT0:X}', f'#define OGC_LAYOUT0 0x{origin:X}')
        hdr = hdr.replace(f'#define OGC_S_COORD 0x{L.S_COORD:X}',
                          f'#define OGC_S_COORD 0x{origin + L.SHIMS_MAX:X}')
    (d / 'ogc_layout.h').write_text(hdr)
    shutil.copy2(HERE / 'ogc_shims.S', d / 'ogc_shims.S')
    code = armasm.assemble(d / 'ogc_shims.S')
    syms = armasm.symbols(d / 'ogc_shims.S')
    if len(code) > L.SHIMS_MAX:
        raise BuildError(f'shims are {len(code)} bytes, more than {L.SHIMS_MAX}')
    pic, n = og_pic.pc_relative(code + b'\0' * (-len(code) % 4), origin, origin, origin + SPAN)
    image = pic + b'\0' * (L.SHIMS_MAX - len(pic)) + L.s_header()
    if L.SHIMS_MAX + L.S['BODY'] > SPAN:
        raise BuildError('the S header is outside the shims\' window')
    return image, syms, n


def compile_core(tmp, tab_off, probe=False):
    """ogc.c after uishare's applier (build_section.unity), one unit, no relocations."""
    sys.path.insert(0, str(UISHARE))
    sys.path.insert(0, str(ROOT / 'research/ui/tools/arm_text'))
    import build_section
    import elf_text
    tree = tmp / f'c{tab_off:x}{"p" if probe else ""}'
    tree.mkdir()
    (tree / 'ogc_layout.h').write_text(L.header())
    unit = build_section.unity(tree)
    for name in ('ogc.c', 'ogc_virtual.c', 'ogc_binfilt.c', 'ogc_files.c', 'virtual_rcd.h'):
        shutil.copy2(HERE / name, tree / name)
    unit.write_text(unit.read_text() + f'#include "{tree / "ogc.c"}"\n')
    if probe: unit.write_text(unit.read_text()+'\nchar vrc_size_probe[(sizeof(struct vrc_state)+63u)&~63u];\nchar rcui_size_probe[(sizeof(struct rc_ui)+63u)&~63u];\n')
    obj = tree / 'ogc.o'
    clang = shutil.which('clang') or 'clang'
    r = subprocess.run([clang, *build_section.CFLAGS, f'-DOGC_TAB_OFF=0x{tab_off:X}u',
                        '-I', str(tree), '-I', str(V3), '-c', str(unit), '-o', str(obj)],
                       capture_output=True, text=True)
    if r.returncode:
        raise BuildError('ogc.c:\n' + r.stderr)
    if probe: return obj
    text = elf_text.load_text(obj)
    for f in ('ogc_v3_entry', 'uia_apply'):
        if not text.functions.get(f, 0) & 1:
            raise BuildError(f'{f} missing or not Thumb')
    return text


def qs_table():
    sys.path.insert(0, str(UISHARE))
    from ui import qs
    return qs.encode()


def build_rcd(formats, tmp):
    """{file name: bytes} and the decoded rows (rcd.decode, as the core sees them)."""
    import rcd
    image = img()
    stock_ids = {word(TT + 0x20 * i, image) for i in range(70)}
    files, rows = {}, []
    for t in formats:
        d = row_data(t, tmp)
        data = rcd.encode(d, d['pack'])
        dec = rcd.decode(data, image, stock_ids)
        name = f'{d["label"]}.RCD'
        if name in files:
            raise BuildError(f'two formats are called {d["label"]}')
        files[name] = data
        dec['target'] = t
        rows.append(dec)
    return files, rows


def build_core(tmp, n_formats=len(FORMATS), virtual=False):
    import rcd
    image = img()
    check_ids(image)
    lay, syms, n_pic = layout(L.LAYOUT0, tmp)
    moved, _, _ = layout(L.LAYOUT0 + SHIFT, tmp)
    if moved != lay:
        i = next(i for i in range(len(lay)) if lay[i] != moved[i])
        raise BuildError(f'the layout is not position-independent: first difference at +0x{i:X}')
    tpl, tinfo = rcd.ui_template(virtual=virtual)
    import rc_files_page
    file_page,file_page_info=rc_files_page.build()
    qtab = qs_table()
    if rcd.qs_max_record() > L.QS_CAP:
        raise BuildError('a scheme-B record outgrows QS_CAP')

    hooks = []
    kinds = {'b': HOOK_B, 'bl': HOOK_BL, 'tw': HOOK_TW}
    for name, site, kind in L.HOOKS:
        if name not in syms:
            raise BuildError(f'shim {name} missing')
        to = L.LAYOUT0 + syms[name]
        nx = L.S_COORD + L.S['NEXT'] + 4 * L.HOOK_INDEX[name]
        rp = L.LAYOUT0 + syms[name + '_replay'] if name + '_replay' in syms else 0
        sw = word(site, image)
        if not rp and sw & 0x0F000000 != 0x0B000000:
            raise BuildError(f'{name} 0x{site:08X}: no replay and the stock word is not a BL')
        hooks.append((site, to, kinds[kind], nx, rp, sw))
    hooks.sort(key=lambda h: h[0] == 0xC043CCF8)            # the picker last
    if len(hooks) > 64:
        raise BuildError('S.NEXT holds 64')

    claims = [(h[0], stock(h[0], 4), CHAIN) for h in hooks]
    for a, sw in tinfo['sites']:                # the menu: the file-redirect and string sites
        if stock(a, 4) != struct.pack('<I', sw):
            raise BuildError(f'uishare site 0x{a:08X}: stock is not the reference image')
        claims.append((a, struct.pack('<I', sw), SHARED_UI))
    for a, n in PAIR_SITES:                 # written at entry, from where S landed (claim only)
        claims.append((a, stock(a, n), EXCL))
    spans = sorted((a, a + len(s)) for a, s, _ in claims)
    if any(e > a for (_, e), (a, _) in zip(spans, spans[1:])):
        raise BuildError('two claims overlap')
    tt = b''.join(stock(TT + 0x20 * i + 4, 8) for i in range(70))
    # the virtual frame rates' menu (vr_ui, rcd.vr_template): the core applies it at every load
    import vr_ui
    vrtpl = rcd.vr_template(image)
    page, marks = vr_ui.b25(image)
    segs = vr_ui.segments(page, image)
    vrpg = struct.pack(f'<{2 + vr_ui.K}I', len(page), len(segs), *marks)
    for x in segs:                      # {stock offset, length} or {0xFFFFFFFF, length, bytes}
        if isinstance(x, tuple):
            vrpg += struct.pack('<2I', *x)
        else:
            vrpg += struct.pack('<2I', 0xFFFFFFFF, len(x)) + x + bytes(-len(x) % 4)
    lv, lmarks = vr_ui.lv(image)
    vrlv = struct.pack('<I', len(lv)) + b''.join(
        struct.pack('<2I', a, len(n)) + st + n for a, st, n in lv)
    for a, st, n in lv:
        if len(st) != len(n) or len(n) % 4 or stock(a, len(n)) != st:
            raise BuildError(f'LV run 0x{a:08X}')
    vrlm = struct.pack(f'<{1 + len(lmarks)}I', len(lmarks), *lmarks)
    vrcsv = struct.pack('<6I', *(a for a, _, _ in rcd.VR_CSV))
    if (vr_ui.K, vr_ui.FIRST_ROW) != (L.VR_K, L.VR_ROW0) or \
            [v[:3] for v in vr_ui.VRATES] != [tuple(v) for v in L.VRATES]:
        raise BuildError('vr_ui and ogc_layout disagree on the virtual rates')

    virtual_blob = b''
    if virtual:
        d = row_data('og3k', tmp)
        d.update(label='VRC000', enum=L.ENUM_RES_BASE+0x100, row_text='RES-Lab', summary='RES-Lab')
        import build_og3k_ui_candidate as B
        B.PLAN_TARGET={'label':'RES-Lab', 'act':tuple(d['act'])}
        pk, _ = B.assets(tmp / 'virtual-assets', names={'OG3K_QS':'VRC000_QS',
                      'OG3K_SET':'VRC000_SET','OG3K_FONT':'VRC000_FONT'})
        virtual_blob=rcd.encode(d, pk)
        rcd.decode(virtual_blob,image,{word(TT+32*i,image) for i in range(70)})

    def lay_out(tab_off):
        claim_off = tab_off + 4 * TAB_WORDS
        data_off = claim_off + 20 * len(claims)
        rows_b, data = b'', b''
        for a, s, k in claims:
            rows_b += struct.pack('<5I', a, len(s), k, data_off + len(data), 0)
            data += s
        hook_off = data_off + len(data)
        hook_b = b''.join(struct.pack('<5I', s, to, k, nx, rp) for s, to, k, nx, rp, _ in hooks)
        tpl_off = (hook_off + len(hook_b) + 7) & ~7
        qstab_off = (tpl_off + len(tpl) + 7) & ~7
        tt_off = (qstab_off + len(qtab) + 7) & ~7
        vrtpl_off = (tt_off + len(tt) + 7) & ~7
        vrpg_off = (vrtpl_off + len(vrtpl) + 7) & ~7
        vrlv_off = (vrpg_off + len(vrpg) + 7) & ~7
        vrlm_off = (vrlv_off + len(vrlv) + 7) & ~7
        vrcsv_off = (vrlm_off + len(vrlm) + 7) & ~7
        files_off=(vrcsv_off+len(vrcsv)+7)&~7
        virtual_off=(files_off+len(file_page)+7)&~7
        img_off = (virtual_off + len(virtual_blob) + 63) & ~63
        scratch_off = img_off + L.SHIMS_MAX + L.S_BYTES
        fobj_off = (scratch_off + 8 * len(hooks) + 63) & ~63
        qsbuf_off = fobj_off + FOBJ_BYTES
        data_area = qsbuf_off + L.QS_SLOTS * 2 * L.QS_CAP
        virtual_state=(data_area+DATA_BYTES+63)&~63
        virtual_bytes=virtual_header_bytes
        virtual_bytes+=L.S_BYTES+0x1000+2*L.RCD_MAX_FILE
        files_state=virtual_state+(virtual_bytes if virtual else 0)
        files_state=(files_state+63)&~63
        files_state_bytes=files_header_bytes+L.S['BODY']+0x1000+L.RCD_MAX_FILE
        tab = struct.pack(f'<{TAB_WORDS}I', TAB_MAGIC, TAB_VERSION, img_off, L.LAYOUT0,
                          len(claims), claim_off, len(hooks), hook_off, scratch_off, fobj_off,
                          tpl_off, len(tpl), qstab_off, tt_off, qsbuf_off, data_area, DATA_BYTES,
                          vrtpl_off, len(vrtpl), vrpg_off, vrlv_off, vrlm_off, virtual_off, len(virtual_blob), virtual_state, vrcsv_off,
                          files_off,len(file_page),files_state)
        tail = tab + rows_b + data + hook_b
        tail += b'\0' * (tpl_off - tab_off - len(tail)) + tpl
        tail += b'\0' * (qstab_off - tab_off - len(tail)) + qtab
        tail += b'\0' * (tt_off - tab_off - len(tail)) + tt
        tail += b'\0' * (vrtpl_off - tab_off - len(tail)) + vrtpl
        tail += b'\0' * (vrpg_off - tab_off - len(tail)) + vrpg
        tail += b'\0' * (vrlv_off - tab_off - len(tail)) + vrlv
        tail += b'\0' * (vrlm_off - tab_off - len(tail)) + vrlm
        tail += b'\0' * (vrcsv_off - tab_off - len(tail)) + vrcsv
        tail += b'\0' * (files_off - tab_off - len(tail)) + file_page
        tail += b'\0' * (virtual_off - tab_off - len(tail)) + virtual_blob
        tail += b'\0' * (img_off - tab_off - len(tail)) + lay
        return tail, {'img_off': img_off, 'scratch_off': scratch_off, 'fobj_off': fobj_off,
                      'file_len': img_off + len(lay), 'tpl_off': tpl_off, 'qstab_off': qstab_off,
                      'tt_off': tt_off, 'qsbuf_off': qsbuf_off, 'data_off': data_area,
                      'vrtpl_off': vrtpl_off, 'vrpg_off': vrpg_off, 'vrlv_off': vrlv_off,
                      'vrlm_off': vrlm_off, 'vrcsv_off': vrcsv_off,
                      'virtual_off': virtual_off, 'virtual_bytes': len(virtual_blob),
                      'virtual_state': virtual_state, 'virtual_runtime_bytes': virtual_bytes if virtual else 0,
                      'files_off':files_off,'files_state':files_state,'files_ui':file_page_info,
                      'block': files_state+files_state_bytes}

    # [FSB1 32][the BIN settings area, CFG_BYTES, zero = no record][text ...]
    cfg = bytes(L.CFG['BYTES'])
    hdr = 32 + len(cfg)
    tab_off = 0
    for _ in range(5):
        text = compile_core(tmp, tab_off)
        need = (hdr + len(text.code) + 63) & ~63
        if need <= tab_off:             # fits (a 64-byte pad when the code shrank back)
            break
        tab_off = max(need, tab_off)
    else:
        raise BuildError('OGC_TAB_OFF did not settle')
    sys.path.insert(0, str(BUILD / 'sl_menu'))
    import build_sl_menu as BSM
    size_probe=compile_core(tmp,tab_off,probe=True)
    virtual_header_bytes=BSM.symbol_size(size_probe,'vrc_size_probe')
    files_header_bytes=BSM.symbol_size(size_probe,'rcui_size_probe')
    tail, f = lay_out(tab_off)
    body = cfg + text.code + b'\0' * (tab_off - hdr - len(text.code)) + tail
    block = f['block'] + -f['block'] % 64
    sys.path.insert(0, str(V3))
    import build_v3
    entry = hdr + text.functions['ogc_v3_entry']
    data = build_v3.make_sup(body, entry, CORE_ID, VERSION, block_size=block, min_svc=3)
    if len(data) != f['file_len']:
        raise BuildError(f'core file {len(data)} != {f["file_len"]}')
    facts = {'file': CORE_NAME, 'label': CORE_ID, 'block': block, 'entry': entry,
             'layout0': f'0x{L.LAYOUT0:08X}', 'cfg_off': 32, 'cfg_bytes': L.CFG['BYTES'],
             's_coord': f'0x{L.S_COORD:08X}', 'text': len(text.code), 'pairs_rewritten': n_pic,
             'uia_apply_off': hdr + text.functions['uia_apply'],
             'virtual_dispatch_off': hdr + text.functions['ogc_virtual_dispatch'],
             'files_button_off':hdr+text.functions['ogc_files_button'],
             'hooks': [{'site': f'0x{s:08X}', 'to': f'0x{to:08X}', 'kind': k,
                        'next': f'0x{nx:08X}', 'replay': f'0x{rp:08X}'}
                       for s, to, k, nx, rp, _ in hooks],
             'hook_names': {f'0x{site:08X}': n for n, site, _ in L.HOOKS},
             'claims': [{'address': f'0x{a:08X}', 'bytes': len(s), 'kind': k} for a, s, k in claims],
             'ui_sites': [f'0x{a:08X}' for a, _ in tinfo['sites']],
             'shims': {k: v for k, v in syms.items()},
             'fns': {n: L.S['FN'] + 4 * i for i, n in enumerate(L.FNS)},
             'S': L.S, 'ROW': L.ROW, 'ENT': L.ENT, 'VM': L.VM, 'VM_BUF': L.VM_BUF}
    facts.update({k: v for k, v in f.items() if k != 'block'})
    return data, facts, tpl


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--out', type=pathlib.Path, required=True)
    ap.add_argument('--formats', default=','.join(FORMATS))
    ap.add_argument('--virtual-rcd',action='store_true',help='one shared dynamic RCD service')
    a = ap.parse_args()
    formats = tuple(f.strip() for f in a.formats.split(',') if f.strip())
    out = a.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f'{out} is not empty: this never overwrites a build')
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='ogc-') as t:
        tmp = pathlib.Path(t)
        data, facts, tpl = build_core(tmp,virtual=a.virtual_rcd)
        rcds, rows = build_rcd(formats, tmp)
    need = sum((len(d) + 63) & ~63 for d in rcds.values()) + L.MAX_ROWS * ((len(tpl) + 512 + 63) & ~63)
    if len(rcds) <= L.MAX_ROWS and need > DATA_BYTES:
        raise SystemExit(f'the data area ({DATA_BYTES}) cannot hold these files ({need})')
    (out / CORE_NAME).write_bytes(data)
    (out / RCD_DIR).mkdir()
    for n, d in rcds.items():
        (out / RCD_DIR / n).write_bytes(d)
    facts['formats'] = list(formats)
    facts['rows'] = [{k: (list(v) if isinstance(v, tuple) else v) for k, v in r.items()}
                     for r in rows]
    files = {CORE_NAME: (data, facts)}
    files.update({f'{RCD_DIR}/{n}': (d, {'label': r['label'], 'target': r['target']})
                  for (n, d), r in zip(rcds.items(), rows)})
    (out / 'build.json').write_text(json.dumps({
        'product': 'fpSup res-custom, the multi-format OpenGate core and its data files (Loader v3)',
        'card': {'\\\\fpSup\\\\' + CORE_NAME: CORE_NAME,
                 **{'\\\\fpSup\\\\RESCUS\\\\' + n: f'{RCD_DIR}/{n}' for n in rcds}},
        'files': {n: {'sha256': hashlib.sha256(d).hexdigest(), 'bytes': len(d), 'facts': f}
                  for n, (d, f) in files.items()}}, indent=1) + '\n')
    for n, (d, _) in files.items():
        print(f'{n}: {len(d):,} B')


if __name__ == '__main__':
    main()
