#!/usr/bin/env python3
"""Build Res Lab for Loader v3: sidebar, automatic Virtual RCD and SAVE.

    python3 -B build_v3_reslab.py --virtual-rcd --out NEW_DIRECTORY [--card] [--no-shell]

With --virtual-rcd, SupManager opens FILTER / OUTPUT / SAVE. Completed edits
automatically pass a memory recipe to res-custom in 32RESCUS.BIN; SAVE writes
named RCD files (or automatic LABnnn.RCD) for later use. Without the flag,
Help opens the export-only calculator.
The shared loader and uishare own UI claims, journal and shutdown restoration.
"""
import argparse
import hashlib
import json
import pathlib
import shutil
import struct
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
V3 = ROOT / 'fpSup/fp_usb_shell/v3'
sys.path[:0] = [str(HERE), str(HERE / 'sl_menu'), str(V3), str(V3.parent),
               str(ROOT / 'research/ui/tools/arm_text'), str(ROOT / 'research/ui/tools'),
               str(HERE / 'res-custom')]
import build_sl_menu as BSM
import build_v3 as BV
import elf_text
import ogc_layout as RCD

NAME, SUP_ID, VERSION, MIN_SERVICES = '50RES-Lab v0.1.0test.BIN', 'RLAB', 17, 3
GUI_SITE, PAGE_SITE = 0xC056461C, 0xC05E82F0
TAB_WORDS = 48
EXPORT_CAP = 0x20000


def slmp(virtual=False):
    """Stock recording rows; only Help navigates to the independent calculator."""
    import sl_b25_page as SP
    import sl_lab_page as LAB
    import sl_size_page as SZ
    import sl_pages as PG
    import sl_lists as LL
    SP.WITH_LAB_JUMP = SP.WITH_CLONES = SP.WITH_CUSTOM_LISTS = False
    SP.WITH_PRIVATE_LISTS = True
    LAB.CALC_ONLY = True
    LAB.VIRTUAL_APPLY = virtual
    # This input has stock rows and the stock Help event. No resolution setter.
    res = SP.build()
    seq = [bytearray(r.to_bytes()) for r in SP.N.split(res['page'])]
    owner, found = None, 0
    for d in seq:
        if SP.u32(d, 0) == 0x10003:
            owner = SP.u32(d, 20)
        if owner == SP.HELP_ROW and SP.u32(d, 0) == 0x10009 and SP.u32(d, 24) == SP.HELP_KEY:
            if res['pool'].text(SP.u32(d, 8)) == 'controlAppState':
                off, _ = res['pool'].intern('SL_LAB')
                SP.put(d, 36, off)
                found += 1
    if found != 1:
        raise RuntimeError('stock B2_5 Help -> SetupHelpMenu changed')
    page = b''.join(seq)
    # New private references, as well as any inherited ones, from the typed page.
    refs = list(res['abs_refs'])
    at = 0
    for d in seq:
        if SP.u32(d, 0) == 0x10009 and len(d) == 41 and res['pool'].text(SP.u32(d, 8)) == 'controlAppState' and res['pool'].text(SP.u32(d, 36)) == 'SL_LAB':
            refs.append((at + 36, 'SL_LAB'))
        at += len(d)
    res['page'], res['abs_refs'] = page, refs
    img = BV.IMAGE.read_bytes()
    pages, refs_by = PG.lab_pages(img, res['pool'])
    # Validate structural allocation budgets without requiring Unicorn to build.
    SZ.check_refs(pages[0][1], refs_by['SL_LAB'], res['pool'])
    stray = LAB.check_settings_free(pages[0][1], res['pool'], SP.load_schemas(img))
    if stray:
        raise RuntimeError(f'calculator page references camera frame-guide settings: {stray[:5]}')
    pp = PG.build_pack(pages,
                       [('FT_LIST','SL_LAB','SL_LAB'),('FT_Y6','SL_LAB','SL_LAB')] if virtual else (),
                       {'SL_LAB': 'FT_LIST'} if virtual else None)
    lists = LL.build_pack(img, calc=True)
    # SL_RATE / SL_BIT are not named by any recording page; omit them altogether.
    # All remaining modelCSV lists are private calculator inputs.
    # Three sidebar pages include native diagram objects and key editors. The
    # owning SUP allocation below is sized from this exact pack length.
    return SP.pack(res, lists, pp, 0xA0000, PG.pack_refs(pp, pages, refs_by))


def literal_xci(w, h):
    """Valid LZ4 literal-only block, whose raw pixels the ARM exporter fills."""
    raw = bytes(w * h * 2)
    ext, n = bytearray(), len(raw) - 15
    while n >= 255:
        ext.append(255); n -= 255
    ext.append(n)
    block = b'\xf0' + ext + raw
    head = bytearray(0x33)
    head[:4] = b'XC\0\0'
    struct.pack_into('<IHHIH', head, 4, len(block) + 23, w, h, 0x400, 0x202)
    head[0x20:0x26] = b'\x04\x22\x4d\x18\x88\x10'
    struct.pack_into('<I', head, 0x26, len(block) + 19)
    struct.pack_into('<I', head, 0x2f, len(block))
    return bytes(head) + block + bytes(4), 0x34 + len(ext)


def export_pack():
    """Five XCI assets, resident alpha glyphs; no external tools needed on camera."""
    import nbr
    from PIL import Image, ImageDraw, ImageFont
    resources, pixels = [], []
    specs = [('LAB0001_QS', 86, 49), ('LAB0001_SET', 86, 74), ('LAB0001_FONT', 150, 38),
             ('font_S_imageSize_0000', 88, 38), ('font_S_imageSize_1111', 88, 38)]
    for i, (name, w, h) in enumerate(specs):
        data, po = literal_xci(w, h)
        resources.append(nbr.Resource(name, f'e{i}.xci', data))
        pixels.append((po, w, h))
    pack = nbr.build(resources)
    inv = nbr.inspect(pack)
    rows = []
    for i, (name, w, h) in enumerate(specs):
        f = next(f for f in inv['files'] if f['filename'] == f'e{i}.xci')
        rows.append((pack.index(name.encode() + b'\0'), f['offset'] + pixels[i][0], w, h))
    atlas = bytearray()
    for w, h, cap in ((10, 18, 15), (18, 28, 24)):
        for ch in '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ-ab':
            font = ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc', cap-2)
            a = Image.new('L', (w,h)); draw = ImageDraw.Draw(a)
            box = draw.textbbox((0,0),ch,font=font)
            draw.text(((w-box[2]+box[0])//2-box[0],(h-box[3]+box[1])//2-box[1]),ch,font=font,fill=255)
            atlas += a.tobytes()
    return pack, rows, bytes(atlas)


def compile_unit(tmp, tab_off, offsets, probe='', virtual=False):
    tree = tmp / f't{tab_off:x}{"p" if probe else ""}'
    tree.mkdir()
    # The consumer owns the wire format; never maintain a second header layout.
    constants = {f'H_{k}': v for k, v in RCD.RCD.items()}
    constants.update(MAGIC=RCD.RCD_MAGIC, VERSION=RCD.RCD_VERSION, HDR=RCD.RCD_HDR,
                     CORE_VERSION=RCD.CORE_VERSION,CAVE_FIRST=BV.cave.CAVE_ARENA,CAVE_END=BV.cave.CAVE_ARENA_END)
    for k in ('SEC_MODES', 'SEC_CANVAS', 'SEC_UI', 'SEC_STANDBY', 'SEC_RATECANVAS', 'SEC_PACK', 'SEC_BINFILT'):
        constants[k] = getattr(RCD, k)
    if RCD.RCD_HDR != 64 or RCD.RCD_VERSION != 3:
        raise RuntimeError('review calculator sections for the new res-custom format')
    (tree / 'rl_rcd.h').write_text(''.join(f'#define RLC_{k} {v}u\n' for k, v in constants.items()))
    shutil.copy2(ROOT / 'projects/open-gate/build/res-custom/virtual_rcd.h', tree / 'virtual_rcd.h')
    unit = BSM.unity(tree, dynamic=True, calc=True)
    unit.write_text(unit.read_text() + f'\n#include "{HERE / "rl_v3.c"}"\n' + probe)
    obj = tree / 'rl.o'
    flags = BSM.CFLAGS_DYNAMIC + ['-mstackrealign', '-DSL_CALC_ONLY=1', '-DSL_DYNAMIC_CORE=1',
                                '-DSL_MENU_IN_BLOCK=1', '-DSL_NRATE=11u',
                                f'-DSL_LAB_FOCUS0={BSM.lab_focus0()}u', f'-DRL_TAB_OFF={tab_off}u']
    if virtual: flags += ['-DRL_VIRTUAL_RCD=1','-DSL_PRIVATE_ONLY=1']
    flags += [f'-DSL_OFF_{k.upper()}={v}u' for k, v in offsets.items()]
    r = subprocess.run([shutil.which('clang') or 'clang', *flags, '-I', str(tree), '-I', str(V3),
                        '-c', str(unit), '-o', str(obj)], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr)
    return obj if probe else elf_text.load_text(obj)


def build(tmp,virtual=False):
    import imx410_block as K
    offsets = dict(axis=0, asptab=40, ratetab=60, tmgtab=192, flag=0, coltab=0, recipe=0,
                   rate240=0, binfilt=36, gtab=0, mark=0, fmt_code=0, core_magic=0)
    calc = bytes(40) + K.aspect_q_table() + K.rate_table() + K.timing_table()
    area = struct.pack('<I', len(menu := slmp(virtual))) + bytes(4092) + menu
    pack, pack_rows, atlas = export_pack()
    tab_off = 0
    for _ in range(6):
        text = compile_unit(tmp, tab_off, offsets, virtual=virtual)
        need = (32 + len(text.code) + 7) & ~7
        if need <= tab_off:
            break
        tab_off = max(need,tab_off)
    else:
        raise RuntimeError('calculator table offset did not settle')
    fields = ('result', 'app', 'reader', 'entry', 'page', 'nbr', 'nbr_len', 'core_base', 'pages_state',
              'out_w', 'out_h', 'ro_w', 'ro_h', 'ro_sx', 'ro_sy', 'bin_h', 'bin_v', 'axis_armed',
              'mode_ids', 'modes_rows', 'mode_sel', 'canvas', 'canvas_valid', 'export_text',
              'crop_w', 'crop_h', 'ratio', 'edit_field', 'editing', 'crop_lock', 'lens_on', 'lens_factor',
              'small_edit', 'applied_geometry', 'applied_valid', 'bin_kh', 'bin_kv', 'bin_mode',
              'output_policy', 'lock_num', 'lock_den', 'save_name', 'name_text', 'name_field', 'name_editing')
    probe = compile_unit(tmp, tab_off, offsets, '\nchar rl_state_probe[sizeof(struct sl_menu)];\n' +
                         ''.join(f'char rl_off_{f}[__builtin_offsetof(struct sl_menu,{f}) + 1];\n' for f in fields),virtual=virtual)
    state_bytes = BSM.symbol_size(probe, 'rl_state_probe')
    sf = {f: BSM.symbol_size(probe, f'rl_off_{f}') - 1 for f in fields}
    calc_off = (tab_off + TAB_WORDS * 4 + 63) & ~63
    area_off = (calc_off + len(calc) + 7) & ~7
    pack_off = (area_off + len(area) + 63) & ~63
    atlas_off = pack_off + len(pack)
    file_len = (atlas_off + len(atlas) + 7) & ~7
    state_off = file_len
    export_off = (state_off + state_bytes + 63) & ~63
    fobj_off = export_off + EXPORT_CAP
    back_off = fobj_off + 0x1000
    block_size = (back_off + EXPORT_CAP + 64) & ~63
    # C struct rl_tab: keep the contract small and fully in the product file.
    tab = [0x32434C52, 2, calc_off, state_off, area_off, len(area), pack_off, len(pack), atlas_off,
           export_off, fobj_off, back_off, EXPORT_CAP,
           *struct.unpack('<2I', BV.stock(GUI_SITE, 4) + BV.stock(PAGE_SITE, 4)),
           0, 0, 0, 0, 0]
    tab += [x for row in pack_rows for x in row]
    tab += [0] * (TAB_WORDS - len(tab))
    body = bytearray(file_len - 32)
    def put(off, b): body[off - 32:off - 32 + len(b)] = b
    for off, data in ((32, text.code), (tab_off, struct.pack(f'<{TAB_WORDS}I', *tab)),
                      (calc_off, calc), (area_off, area), (pack_off, pack), (atlas_off, atlas)):
        put(off, data)
    data = BV.make_sup(body, 32 + text.functions['rl_v3_entry'], SUP_ID, VERSION,
                       block_size, MIN_SERVICES)
    facts = dict(file_len=len(data), block=block_size, architecture='virtual-rcd-producer' if virtual else 'calculation-only', tab_off=tab_off,
                 calc_off=calc_off, area_off=area_off, area_bytes=len(area), slmp_bytes=len(menu),
                 state_off=state_off, state_bytes=state_bytes, state_fields=sf, functions={n: 32 + o for n, o in text.functions.items()},
                 claims=2, own_claims=[hex(GUI_SITE), hex(PAGE_SITE)], core_hooks=[], pointer_pairs=[],
                 static_recording_patches=[], export_version=3, export_path='fpSup/RESCUS/LABnnn.RCD',
                 export_pack_bytes=len(pack), export_off=export_off, offsets=offsets)
    return data, facts


def source_hashes():
    paths = [pathlib.Path(__file__), HERE / 'rl_v3.c', HERE / 'sl_lab_page.py', HERE / 'sl_b25_page.py',
             HERE / 'sl_pages.py', HERE / 'sl_lists.py', HERE / 'sl_lab_sidebar.py', HERE / 'imx410_block.py', HERE / 'imx410_full.py',
             *BSM.UNITS, BSM.HERE / 'sl_menu.h', BSM.HERE / 'build_sl_menu.py',
             HERE / 'res-custom/ogc_layout.py', HERE / 'res-custom/ogc_shims.S',
             HERE / 'res-custom/rcd.py', HERE / 'res-custom/virtual_rcd.h',
             HERE / 'res-custom/ogc_virtual.c', HERE / 'res-custom/ogc_binfilt.c', HERE / 'res-custom/ogc.c', HERE / 'res-custom/build_v3_rescustom.py', V3 / 'sloader.h', V3 / 'sloader.c', V3 / 'build_v3.py',
             HERE / 'res-custom/ogc_files.c', HERE / 'res-custom/rc_files_page.py',
             ROOT / 'fpSup/uishare/tab/manage_page.py',ROOT / 'fpSup/uishare/tab/ft6_page.py',
             V3 / 'allsups.c', ROOT / 'fpSup/uishare/tab/build_ft6.py']
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--out', type=pathlib.Path, required=True)
    ap.add_argument('--card', action='store_true')
    ap.add_argument('--no-shell', action='store_true')
    ap.add_argument('--virtual-rcd',action='store_true',help='Apply through the common res-custom memory service')
    a = ap.parse_args()
    out = a.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f'{out} is not empty: refusing to overwrite a previous artifact')
    with tempfile.TemporaryDirectory(prefix='rlcalc-') as d:
        data, facts = build(pathlib.Path(d),virtual=a.virtual_rcd)
        if a.virtual_rcd:
            import build_v3_rescustom as RC
            core, core_facts, _ = RC.build_core(pathlib.Path(d),virtual=True)
            facts['rescustom']=core_facts
    out.mkdir(parents=True, exist_ok=True)
    dest = out / 'fpSup' if a.card else out
    dest.mkdir(exist_ok=True)
    (dest / NAME).write_bytes(data)
    if a.virtual_rcd: (dest / '32RESCUS.BIN').write_bytes(core)
    (dest / 'RESCUS').mkdir(exist_ok=True)
    (dest / 'RESCUS/README.TXT').write_text(('RES-Lab applies completed edits through Virtual RCD in memory without saving. ' if a.virtual_rcd else '') + 'SAVE exports named RCD files here (1-7 A-Z/0-9 characters; blank uses LABnnn). Existing names are never overwritten. RES-CUSTOM settings manage which files are enabled. Restart after changing the enable list to update Resolution and QS. With Virtual RCD, five file slots are available; disable one first if full.\n')
    if a.card:
        loader, facts['loader'] = BV.loader_bin(allsups=a.virtual_rcd)
        (dest / 'LOADER.BIN').write_bytes(loader)
        (out / 'AutoRun.txt').write_bytes(BV.autorun(out))
        (dest / 'UI').mkdir()
        for i, px in enumerate(BV.splash_frames()): (dest / 'UI' / f'{i}.BIN').write_bytes(px)
        if a.virtual_rcd:
            sys.path.insert(0,str(ROOT/'fpSup/uishare/tab'))
            import build_ft6
            manager,_=build_ft6.data_file()
            (dest/'UI'/BV.ALLSUPS_FILE).write_bytes(manager)
        if not a.no_shell: (dest / '00SHELL.BIN').write_bytes(BV.shell_sup())
    (out / 'build.json').write_text(json.dumps(dict(product='Res Lab Virtual RCD, Loader v3' if a.virtual_rcd else 'res-lab calculator, Loader v3', file=NAME,
        sup_id=SUP_ID, version=VERSION, min_services=MIN_SERVICES, card=a.card, shell=a.card and not a.no_shell,
        sha256=hashlib.sha256(data).hexdigest(), source_sha256=source_hashes(), facts=facts), indent=1) + '\n')
    (out / 'MANIFEST.sha256').write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(out)}\n'
                                        for p in sorted(out.rglob('*')) if p.is_file()))
    print(f'{NAME}: {len(data):,} B, block {facts["block"]:,} B; '+('Virtual RCD apply' if a.virtual_rcd else 'RCD v3 export'))


if __name__ == '__main__': main()
