#!/usr/bin/env python3
"""OpenGate (OG3K or OG2K) as a Loader v3 sup: \\fpSup\\30OG3K.BIN / 30OG2K.BIN.

    python3 -B build_v3_og.py --target og3k --out /absolute/new/directory [--card]

projects/usb-shell-sup/notes/LOADER_V3.md §8 step 4. The same recording core as
the AutoRun card (og3k_plan.py, OG_UISHARE=1), assembled with OG_V3=1
(og_pic.inc): every OpenGate address in the cave becomes a coordinate in one
layout that the sup's block carries, reached PC-relative. Nothing of
OpenGate's stays at a fixed cave address.

The menu (2026-10-06, user decision): uishare's shared Quick Set layer
(fpSup/uishare/QS_SHARE.md §9) -- one ui.options.resolution_qs() block: the
Settings row, the QS state, the footer cell, the private NBR pack with the
image names prefixed by this file's name.  og3k_ui.S (its own NBU record,
layout and NBR hooks, the 360-record table, the aliases) is not used.

  - the layout image: the words the AutoRun card puts at 0xC0730000..0xC0735000,
    at the same relative places;
  - claims (og_v3.c): every hook site (EXCL), every firmware word the payloads
    change at run time (the GTAB groups, the donors' timing records; EXCL,
    claim only), the uishare sites its FPUI block hangs on (SHARED_UI); the QS
    sites uia_apply claims itself (qs_check, through the loader's svc);
  - fixups: the format table's key pointers -- the only coordinates the
    firmware is handed;
  - hooks through cave veneers (the block is ~48 MB from the firmware), in the
    AutoRun card's order;
  - the AutoRun card's stale-hook cleaners (34 words that wrote stock values to
    sites OpenGate no longer uses) are gone: a claim repairs residue now.

Proof that nothing absolute into the block is left: the whole layout is
assembled a second time at another origin (a subprocess, OG_V3_OGV) and must be
byte-identical.

--out DIR writes DIR/<NAME> and build.json. --card makes DIR a whole v3 card:
AutoRun.txt, fpSup/LOADER.BIN, fpSup/UI/ and the shell and lossless sups taken
from --from-card (default: the step-2 card) plus this one. Never writes a camera
card.
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
ROOT = HERE.parent.parent.parent
FPSUP = ROOT / 'fpSup'
V3 = FPSUP / 'fp_usb_shell' / 'v3'
UISHARE = FPSUP / 'uishare'
STEP2_CARD = ROOT / 'projects/usb-shell-sup/cards/20261006-v3-step2-lossless'

CAVE0, CAVE_END = 0xC0730000, 0xC0735000
UIS_RES_QSCUR = 0x55435351                   # "QSCU", uishare ui_pool.h
QS_SITES = ((0xC05E6400, 4), (0xC05D90F0, 4), (0xC05E84D8, 4), (0xC06BDA3C, 8),
            (0xC06BDA48, 4))                 # uishare qs_layer.h: what qs_install claims
GEOMETRY = {'OG3K': 'OG3K 3008x2000', 'OG2K': 'OG2K 2000x1334'}   # the Settings row
SHIFT_OGV = 0x10000000                    # the second origin for the PIC proof
CHAIN, EXCL, SHARED_UI = 1, 2, 3
HOOK_B, HOOK_BL, HOOK_THUMB_BW = 0, 1, 2
TAB_MAGIC, TAB_VERSION, TAB_WORDS = 0x3356474F, 1, 14
NAMES = {'og3k': '30OG3K.BIN', 'og2k': '30OG2K.BIN'}
VERSION = 1


class BuildError(RuntimeError):
    pass


def _env(target, ogv=None):
    os.environ.update({'OG_TARGET': target, 'OG_UISHARE': '1', 'OG_V3': '1', 'OG_CHAIN': '1'})
    if ogv is not None:
        os.environ['OG_V3_OGV'] = hex(ogv)
    else:
        os.environ.pop('OG_V3_OGV', None)


def compose(target):
    """The AutoRun card's recording core, assembled for v3: (items, plan, P)."""
    sys.path.insert(0, str(HERE))
    import og3k_plan as P
    if not (P.V3 and P.UISHARE) or P.TARGET != target:
        raise BuildError('compose: environment not set before the import')
    plan = P.Plan()
    bad = plan.check()
    if bad:
        raise BuildError('OpenGate plan check failed:\n' + '\n'.join(bad))
    return list(plan.all()), plan, P


def layout_image(items):
    """The layout image: cave words at their offsets."""
    img = bytearray(CAVE_END - CAVE0)
    for a, v, _ in items:
        if CAVE0 <= a < CAVE_END:
            struct.pack_into('<I', img, a - CAVE0, v)
    return bytes(img)


def image_only(target, ogv, path):
    """Subprocess side of the PIC proof: the layout image at origin `ogv`."""
    _env(target, ogv)
    items, _, _ = compose(target)
    pathlib.Path(path).write_bytes(layout_image(items))


def classify(items, plan, P):
    """Split the plan. Returns (hooks, patches, fix_offs, dropped)."""
    og_hooks = {site: (code, stock, kind) for site, code, stock, kind, _ in P.HOOKS}
    code_notes = {f'{n} payload' for n, _, _ in P.PAYLOADS}
    hooks, patches, fixes, dropped = [], [], [], []
    for a, v, note in items:
        if CAVE0 <= a < CAVE_END:
            if note in code_notes:
                continue
            if CAVE0 <= v < CAVE_END:
                if not note.startswith('格式表') or (a - P.TABLE) % 48 != 12:
                    raise BuildError(f'0x{a:08X} ({note}) holds 0x{v:08X}, a layout '
                                     'address nobody relocates')
                fixes.append(a - CAVE0)                  # relative to the image
            continue
        if a in og_hooks:
            to, stock, kind = og_hooks[a]
            if v != P.branch(kind, to, a) or plan.word(a) != stock:
                raise BuildError(f'hook 0x{a:08X}: the card word is not its branch')
            hooks.append((a, to, HOOK_BL if kind == 'bl' else HOOK_B, stock))
        elif note.endswith('還原原廠'):
            # Plan.cleanup()/playback(): stock words written to sites the card
            # no longer hooks, against an older card's residue.
            if v != plan.word(a):
                raise BuildError(f'0x{a:08X} ({note}) is not the stock word')
            dropped.append((a, note))
        else:
            patches.append((a, v, note))
    if [h[0] for h in hooks] != [s for s, *_ in P.HOOKS] or hooks[-1][0] != P.PIK_HOOK:
        raise BuildError('the picker is not the last OpenGate hook')
    return hooks, patches, fixes, dropped


def chain_rows(hooks, P, plan):
    """{site: (next coordinate, replay coordinate)} -- og_pic.inc OG_PASS.  A site
    whose payload calls through the word (og3kfps: a BL site) needs no replay:
    chain_next always finds the stock BL's own target."""
    sys.path.insert(0, str(HERE))
    from armasm import symbols
    by_base = {base: (n, f) for n, f, base in P.PAYLOADS}
    out = {}
    for site, to, kind, _ in hooks:
        name, src = by_base[to]
        slot = P.CHAIN_NEXT0 + 4 * P.CHAIN_SLOT[name]
        sym = symbols(HERE / src, plan.pdefs[name])
        replay = to + sym['og_replay'] if 'og_replay' in sym else 0
        if not replay and plan.word(site) & 0x0F000000 != 0x0B000000:
            raise BuildError(f'{site:#x}: no og_replay and the stock word is not a BL')
        out[site] = (slot, replay)
    return out


def runs(words):
    """[(address, value)] sorted -> [(address, bytes)] of consecutive words."""
    out = []
    for a, v in sorted(words):
        if out and out[-1][0] + len(out[-1][1]) == a:
            out[-1] = (out[-1][0], out[-1][1] + struct.pack('<I', v))
        else:
            out.append((a, struct.pack('<I', v)))
    return out


def runtime_words(P, plan):
    """Firmware words the payloads write after load: (address, bytes) to claim.
    og3ksel/og3kfmt switch the GTAB groups; fmttable writes each donor's timing
    record (+4, +8), og3ksel/og3kfmt put the donor's back."""
    rows = [(a, 4) for addrs, _, _ in plan.groups() for a in addrs]
    donors = sorted({donor for _, donor, _, _ in P.FMT})
    timing = [P.TT + plan.idx[d] * 0x20 + 4 for d in donors]
    if P.DONOR_TIMING_ADDR + 4 not in timing:
        raise BuildError('the restored donor is not one the table writes')
    rows += [(a, 8) for a in timing]
    return rows


def fpui_block(target, P, tmp):
    """The menu: one uishare resolution_qs() block (QS_SHARE.md §9) -- the
    Settings row, the QS state, the footer, the private NBR pack.  The three QS
    images are named after this file (§9.4: "30OG3K_QS"); the pack's other
    resources (font_S_imageSize_* the stock lacks) keep their stock-style names.
    Returns (block bytes, uishare sites, image names, pack bytes)."""
    sys.path.insert(0, str(UISHARE))
    sys.path.insert(0, str(HERE))
    import build_og3k_ui_candidate as B
    import build_section
    import qs_build
    from ui import fpui, options
    stem = NAMES[target][:-4]
    images = tuple(f'{stem}_{s}' for s in ('QS', 'SET', 'FONT'))
    pack, _ = B.assets(tmp / 'assets', names={'OG3K_QS': images[0], 'OG3K_SET': images[1],
                                              'OG3K_FONT': images[2]})
    label = P.T['label']
    blk = options.resolution_qs(GEOMETRY[label], label, images, P.OG_ENUMS[target],
                                qs_build.layer_blob(), pack=pack).encode()
    _, ops, _ = fpui.decode(blk)
    if any(code == fpui.OP_STRBASE for code, _ in ops):
        raise BuildError('a STRBASE in the block: its address would need relocating')
    if sum(code == fpui.OP_QS_OPTION for code, _ in ops) != 1:
        raise BuildError('the block must carry exactly one QS_OPTION')
    return blk, build_section.sites(blk), images, pack


def compile_entry(tmp, tab_off):
    """og_v3.c with uishare's applier, one unit, no relocations."""
    sys.path.insert(0, str(UISHARE))
    sys.path.insert(0, str(ROOT / 'research/ui/tools/arm_text'))
    import build_section
    import elf_text
    tree = tmp / f'tree{tab_off:x}'
    tree.mkdir()
    unit = build_section.unity(tree)
    unit.write_text(unit.read_text() + f'#include "{HERE / "og_v3.c"}"\n')
    obj = tree / 'og_v3.o'
    clang = shutil.which('clang') or 'clang'
    r = subprocess.run([clang, *build_section.CFLAGS, f'-DOG_TAB_OFF=0x{tab_off:X}u',
                        '-I', str(tree), '-I', str(V3), '-c', str(unit), '-o', str(obj)],
                       capture_output=True, text=True)
    if r.returncode:
        raise BuildError('compile failed:\n' + r.stderr)
    text = elf_text.load_text(obj)
    if not text.functions.get('og_v3_entry', 0) & 1:
        raise BuildError('og_v3_entry missing or not Thumb')
    return text


def stock(addr, n):
    sys.path.insert(0, str(V3))
    import build_v3
    return build_v3.stock(addr, n)


def build(target, tmp):
    _env(target)
    items, plan, P = compose(target)
    img = layout_image(items)

    # The PIC proof: the same layout at another origin, byte for byte.
    moved = tmp / 'moved.bin'
    r = subprocess.run([sys.executable, '-B', __file__, '--image-only', target,
                        hex(SHIFT_OGV), str(moved)], capture_output=True, text=True)
    if r.returncode:
        raise BuildError('the moved assembly failed:\n' + r.stderr[-4000:])
    if moved.read_bytes() != img:
        diff = next(i for i in range(len(img)) if img[i] != moved.read_bytes()[i])
        raise BuildError(f'the layout is not position-independent: first difference at '
                         f'0x{CAVE0 + diff:08X}')

    hooks, patches, fixes, dropped = classify(items, plan, P)
    fpui, ui_sites, images, pack = fpui_block(target, P, tmp)
    strbase_at = []

    claims = []                                  # (addr, stock bytes, kind, new or None)
    chain = chain_rows(hooks, P, plan)
    for site, _, _, stock_word in hooks:
        s = stock(site, 4)
        if s != struct.pack('<I', stock_word):
            raise BuildError(f'hook 0x{site:08X}: stock is not the reference image')
        claims.append((site, s, CHAIN, None))            # every hook is a layer (OG_CHAIN)
    for a, new in runs([(a, v) for a, v, _ in patches]):
        claims.append((a, stock(a, len(new)), EXCL, new))
    groups = plan.groups()
    shared = {a for addrs, _, _ in (groups[:P.GTAB_SHARED_GROUPS] if P.WITH_CLAMP else groups)
              for a in addrs}
    for a, n in runtime_words(P, plan):
        # The shared GTAB group (the six preview heights) is the same words in OG3K
        # and OG2K: CHAIN, each writes only while it is the active one (og3ksel /
        # og3kfmt OG_CHAIN).  The donors' timing records and the video clamp of
        # the donor modes (the private groups, og3k_plan.CLAMP_*) are each
        # target's own (98/117 vs 139): EXCL.
        claims.append((a, stock(a, n), CHAIN if a in shared else EXCL, None))
    for a, s in ui_sites:
        if stock(a, 4) != struct.pack('<I', s):
            raise BuildError(f'uishare site 0x{a:08X}: stock is not the reference image')
        claims.append((a, struct.pack('<I', s), SHARED_UI, None))
    # The QS layer's sites (uishare qs_layer.h), claimed here too -- the same
    # ranges and kind qs_install claims, so the books hold one claim each -- but
    # BEFORE uia_apply: the first claim repairs a patch a missed power-off left
    # (camera 2026-10-07: the old OG3K's Thumb hooks survived a shell reboot and
    # qs_check refused them, UIA_HOOK).  qs_check runs before its own claims.
    for a, n in QS_SITES:
        claims.append((a, stock(a, n), SHARED_UI, None))
    # uishare QS_SHARE.md §9: every QS sup claims the shared "current format"
    # resource; the first holder issues the shared image ids (uis_qs_shared).
    # Without it uia_apply refuses QS_OPTION (camera 2026-10-07: UIA_HOOK, op 37).
    claims.append((UIS_RES_QSCUR, b'', SHARED_UI, None))
    spans = sorted((a, a + len(s)) for a, s, _, _ in claims if s)
    if any(e > a for (_, e), (a, _) in zip(spans, spans[1:])):
        raise BuildError('two claims overlap')

    restore = P.RESTORE_CODE if P.WITH_FMTGUARD else 0

    def lay(tab_off):
        """Everything after the text, for the text's length: (bytes, facts)."""
        rows_off = tab_off + 4 * TAB_WORDS
        claim_off = rows_off
        data_off = claim_off + 20 * len(claims)
        data, rows = b'', b''
        for a, s, kind, new in claims:
            so = data_off + len(data) if s else 0
            data += s
            no = 0
            if new is not None:
                no = data_off + len(data)
                data += new
            rows += struct.pack('<5I', a, len(s), kind, so, no)
        hook_off = data_off + len(data)
        hook_rows = b''.join(struct.pack('<5I', s, to, k, *chain[s]) for s, to, k, _ in hooks)
        fix_off = hook_off + len(hook_rows)
        img_off = (fix_off + 4 * (len(fixes) + len(strbase_at)) + 63) & ~63
        fpui_off = (img_off + len(img) + 3) & ~3
        fix_list = [img_off + f for f in fixes] + [fpui_off + f for f in strbase_at]
        file_len = fpui_off + len(fpui)
        file_len += -file_len % 4
        scratch_off = file_len
        tab = struct.pack(f'<{TAB_WORDS}I', TAB_MAGIC, TAB_VERSION, img_off, CAVE0,
                          len(claims), claim_off, len(fix_list), fix_off,
                          fpui_off, len(fpui), len(hooks), hook_off,
                          restore, scratch_off)
        tail = tab + rows + data + hook_rows + struct.pack(f'<{len(fix_list)}I', *fix_list)
        tail += b'\0' * (img_off - tab_off - len(tail))
        tail += img + b'\0' * (fpui_off - img_off - len(img)) + fpui
        tail += b'\0' * (file_len - tab_off - len(tail))
        return tail, {'img_off': img_off, 'fpui_off': fpui_off, 'file_len': file_len,
                      'scratch_off': scratch_off, 'claims': len(claims), 'fixes': len(fix_list),
                      'hooks': len(hooks)}

    hdr = 32
    tab_off = 0
    for _ in range(5):
        text = compile_entry(tmp, tab_off)
        need = (hdr + len(text.code) + 3) & ~3
        if need == tab_off:
            break
        tab_off = need
    else:
        raise BuildError('OG_TAB_OFF did not settle')
    tail, facts = lay(tab_off)
    body = text.code + b'\0' * (tab_off - hdr - len(text.code)) + tail
    block = facts['scratch_off'] + 4 * len(hooks)
    block += -block % 64
    sys.path.insert(0, str(V3))
    import build_v3
    entry = hdr + text.functions['og_v3_entry']
    data = build_v3.make_sup(body, entry, P.T['label'], VERSION, block_size=block)
    if len(data) != facts['file_len']:
        raise BuildError('the file is not the length the table says')
    facts.update({
        'target': target, 'label': P.T['label'], 'entry': entry, 'tab_off': tab_off,
        'text': len(text.code), 'block': block, 'image': len(img), 'fpui': len(fpui),
        'pack': len(pack), 'images': list(images), 'enum': P.OG_ENUMS[target],
        'v3_growth': plan.v3_growth,
        'pic_proof_ogv': f'0x{SHIFT_OGV:08X}',
        'hooks_list': [{'site': f'0x{s:08X}', 'to': f'0x{to:08X}',
                        'kind': ('B', 'BL', 'Thumb B.W')[k],
                        'next': f'0x{chain[s][0]:08X}', 'replay': f'0x{chain[s][1]:08X}'}
                       for s, to, k, _ in hooks],
        'claims_list': [{'address': f'0x{a:08X}', 'bytes': len(s),
                         'kind': {CHAIN: 'CHAIN', EXCL: 'EXCL', SHARED_UI: 'SHARED_UI'}[k],
                         'writes': new is not None} for a, s, k, new in claims],
        'patches': [{'address': f'0x{a:08X}', 'value': f'0x{v:08X}', 'note': n}
                    for a, v, n in patches],
        'dropped_stock_writes': len(dropped),
        'restore': f'0x{restore:08X}' if restore else None,
        # for test_v3_og.py: where things are, as coordinates or file offsets
        'uia_apply_off': hdr + text.functions['uia_apply'],
        'cave0': f'0x{CAVE0:08X}',
        'table': f'0x{P.TABLE:08X}', 'fmt_keys': [k for k, *_ in P.FMT],
        'flag': f'0x{P.FLAG:08X}', 'fmtlatch': f'0x{P.FMTLATCH:08X}',
        'donor_timing': f'0x{P.DONOR_TIMING_ADDR:08X}',
        'gtab_words': [f'0x{a:08X}' for a, _ in runtime_words(P, plan)],
        'clamp_words': [{'address': f'0x{a:08X}', 'on': f'0x{on:08X}', 'off': f'0x{off:08X}'}
                        for (a,), on, off in (plan.clamp_groups() if P.WITH_CLAMP else [])],
    })
    return data, facts


def main():
    if len(sys.argv) == 5 and sys.argv[1] == '--image-only':
        image_only(sys.argv[2], int(sys.argv[3], 0), sys.argv[4])
        return
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--target', choices=sorted(NAMES), required=True)
    ap.add_argument('--out', type=pathlib.Path, required=True)
    ap.add_argument('--card', action='store_true',
                    help='a whole v3 card: loader, AutoRun, frames, shell, lossless and this')
    ap.add_argument('--from-card', type=pathlib.Path, default=STEP2_CARD,
                    help='where --card takes LOADER.BIN, AutoRun, UI frames, 00SHELL and '
                         '10LOSS from (the bytes already tested on the camera)')
    a = ap.parse_args()
    out = a.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f'{out} is not empty: this never overwrites a build or a card')
    with tempfile.TemporaryDirectory(prefix='ogv3b-') as t:
        data, facts = build(a.target, pathlib.Path(t))
    name = NAMES[a.target]
    out.mkdir(parents=True, exist_ok=True)
    if a.card:
        src = a.from_card.resolve()
        shutil.copy2(src / 'AutoRun.txt', out / 'AutoRun.txt')
        shutil.copytree(src / 'fpSup', out / 'fpSup')
        (out / 'fpSup' / name).write_bytes(data)
        lines = []
        for p in sorted(out.rglob('*')):
            if p.is_file() and p.name != 'MANIFEST.sha256':
                lines.append(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  '
                             f'{p.relative_to(out)}')
        (out / 'MANIFEST.sha256').write_text('\n'.join(lines) + '\n')
    else:
        (out / name).write_bytes(data)
    sources = [pathlib.Path(__file__), HERE / 'og_v3.c', HERE / 'og_pic.inc',
               HERE / 'og3k_plan.py', HERE / 'build_og3k_ui_candidate.py'] + \
              [HERE / f for _, f, _ in __import__('og3k_plan').PAYLOADS] + \
              sorted(UISHARE.glob('*.[chS]')) + sorted((UISHARE / 'ui').glob('*.py'))
    (out / 'build.json').write_text(json.dumps({
        'product': f'fpSup-{facts["label"]}, Loader v3 sup', 'file': name,
        'sup_id': facts['label'], 'version': VERSION, 'card': a.card,
        'from_card': str(a.from_card) if a.card else None,
        'sha256': hashlib.sha256(data).hexdigest(), 'facts': facts,
        'sources': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in sources}}, indent=1, ensure_ascii=False) + '\n')
    print(f'{name}: {len(data):,} B, block {facts["block"]:,} B, {facts["claims"]} claims, '
          f'{facts["hooks"]} hooks, {facts["fixes"]} fixups, '
          f'{facts["dropped_stock_writes"]} stale-hook cleaners dropped -> {out}')


if __name__ == '__main__':
    main()
