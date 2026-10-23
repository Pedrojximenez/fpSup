#!/usr/bin/env python3
"""Build the sys-perf sup: \\fpSup\\70PERF.BIN (Loader v3, one block).

    python3 -B build_perf.py [--out DIR] [--enable dc,nb,fd,lz | --enable all] [--master 0|1]

Default: everything installed, every feature switch OFF (the hooks behave
stock) -- the first on-camera step.  --enable turns features on in the file's
initial values; the host tool perfctl.py flips them at run time.

Modules (each rebuilt here from its source and checked against the sha256 its
own patch.json recorded -- the bytes that were tested are the bytes shipped):
  dirtyclean  projects/sys-perf/dirtyclean   3 bl sites (code)       switch: its C_EN
  filldma     projects/sys-perf/filldma      no sites (dispatcher)   switch: its fd_enable
  neonblit    projects/sys-perf/neonblit     9 span words + fill     switch: pf_nb
  lz4fast     projects/sys-perf/lz4fast      when its patch.json exists   switch: pf_lz
  inputredraw projects/sys-perf/inputredraw  1 ARM bl (C06D1418)     switch: its ir_enable (+8)
  iconcache   projects/sys-perf/iconcache    2 Thumb b.w (C060219C/234C) switch: its EN (+4); arena = block BSS
  pagelru     projects/sys-perf/pagelru      2 Thumb bl->blx (C05DD5CA/670) switch: its enable (+4)
  alphalut    projects/sys-perf/alphalut     1 ARM bl (C0561734)     switch: its enable (+8); ctl +40 (layout 3)
  waveform    projects/sys-perf/waveform     3 vtable words (C05A3728) switch: its enable (+4); ctl +44 (layout 4)
--without ir,ic,pl,al,wf leaves modules out entirely: not assembled in, no
claim, no arena (block_size drops IC_ARENA without ic); its control-block
offset reads 0 and perfctl reports it n/a.
Every switch ships 0.  pf_master=0 sends every hook down its stock path
through a gate stub (the new modules included).
Every firmware word is claimed EXCL with its stock value from the reference
image; the loader journals it and writes it back at power-off.
"""
import argparse, hashlib, json, pathlib, struct, sys, tempfile

HERE = pathlib.Path(__file__).resolve().parent
PERF = HERE.parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'fpSup' / 'fp_usb_shell'))
sys.path.insert(0, str(ROOT / 'fpSup' / 'fp_usb_shell' / 'v3'))
from armasm import assemble, symbols  # noqa: E402

IMAGE = (ROOT / 'out' / 'seg0_c0000000.bin').read_bytes()
B = 0xC0000000
NAME, SUP_ID, VERSION = '70PERF.BIN', 'PERF', 1
SL_EXCL = 2
HEADER = 32
FILL_SLOTS = (0xC2E38E7C, 0xC2EF62A0)      # layer vtables A/B +0x20, stock C0721480
FW_FILL = 0xC0721480
IC_ARENA = 0x100000                         # iconcache arena, sup block BSS (class-0 loader heap)
FEATURES = ('dc', 'nb', 'fd', 'lz', 'ir', 'ic', 'pl', 'al', 'wf')
OPTIONAL = ('ir', 'ic', 'pl', 'al', 'wf')     # --without may drop these
WF_SLOTS = (0xC2DF8F4C, 0xC2DF8FE4, 0xC2DF9220)
WF_STOCK = 0xC05A3728


class BuildError(RuntimeError):
    pass


def word(a):
    if not B <= a < B + len(IMAGE) - 3:
        raise BuildError(f'{a:#x} is not in the reference image')
    return struct.unpack_from('<I', IMAGE, a - B)[0]


def bl_target(at, insn):
    if insn & 0xFF000000 != 0xEB000000:
        raise BuildError(f'{at:#x}: {insn:#010x} is not an ARM bl')
    off = insn & 0xFFFFFF
    if off & 0x800000:
        off -= 1 << 24
    return at + 8 + 4 * off


def sha(b):
    return hashlib.sha256(b).hexdigest()


def module_neonblit():
    d = PERF / 'neonblit'
    pj = json.loads((d / 'patch.json').read_text())
    try:
        code = assemble(d / 'neonblit.S')
        sym = {k: v for k, v in symbols(d / 'neonblit.S').items() if k.startswith('nb_')}
    except BaseException:                    # noqa: BLE001 -- source mid-edit
        code, sym = b'', {}
    if sha(code) != pj['code_sha256']:
        # neonblit.S is being reworked on its own line; ship the tested
        # neonblit.bin it recorded (same sha256 as patch.json), symbols from there
        code = (d / pj['code']).read_bytes()
        if sha(code) != pj['code_sha256']:
            raise BuildError('neither neonblit.S nor neonblit.bin matches patch.json')
        sym = dict(pj['symbols'])
    spans = []
    for p in pj['patches']:
        a, stock = int(p['addr'], 16), int(p['stock'], 16)
        if word(a) != stock:
            raise BuildError(f'neonblit {a:#x}: image {word(a):#x} != {stock:#x}')
        spans.append((a, stock, p['symbol']))
    return code, sym, spans


def module_filldma():
    d = PERF / 'filldma'
    pj = json.loads((d / 'patch.json').read_text())
    code = assemble(d / 'filldma.S')
    if sha(code) != pj['bin_sha256']:
        raise BuildError('filldma.S no longer matches the tested filldma.bin (patch.json)')
    if pj['patches']:
        raise BuildError('filldma is not supposed to patch anything itself')
    for c in pj['fw_checks']:
        if word(int(c['addr'], 16)) != int(c['word'], 16):
            raise BuildError(f'filldma fw_check {c["addr"]} failed')
    sym = symbols(d / 'filldma.S')
    return code, {'fd_layer_fill': sym['fd_layer_fill']}


def module_dirtyclean():
    d = PERF / 'dirtyclean'
    pj = json.loads((d / 'patch.json').read_text())
    code = assemble(d / 'dirtyclean.S')
    if sha(code) != pj['body']['sha256']:
        raise BuildError('dirtyclean.S no longer matches the tested body (patch.json)')
    sym = {k: v for k, v in symbols(d / 'dirtyclean.S').items() if k.startswith('dc_')}
    sites = []
    for s in pj['sites']:
        a, orig = int(s['address'], 16), int(s['orig_word'], 16)
        if word(a) != orig:
            raise BuildError(f'dirtyclean {a:#x}: image {word(a):#x} != {orig:#x}')
        sites.append((s['name'], a, orig, bl_target(a, orig)))
    return code, sym, sites


def module_lz4fast():
    """Optional.  Accepted patch.json shapes: neonblit-style "patches"
    (data words: addr/stock/symbol) and dirtyclean-style "sites" (ARM bl:
    address/orig_word/entry symbol).  Every site is gated by pf_lz."""
    d = PERF / 'lz4fast'
    pj_path = d / 'patch.json'
    if not pj_path.exists():
        return None
    pj = json.loads(pj_path.read_text())
    src = next(iter(sorted(d.glob('*.S'))), None)
    if src is None:
        raise BuildError('lz4fast: patch.json but no .S source')
    code = assemble(src)
    want = pj.get('code_sha256') or pj.get('bin_sha256') or (pj.get('body') or {}).get('sha256')
    if want and sha(code) != want:
        raise BuildError('lz4fast source no longer matches its patch.json sha256')
    sym = symbols(src)
    rows = []
    for p in pj.get('patches', []):
        a, stock = int(p['addr'], 16), int(p['stock'], 16)
        if word(a) != stock:
            raise BuildError(f'lz4fast {a:#x}: image {word(a):#x} != {stock:#x}')
        rows.append(('data', a, stock, p['symbol']))
    entries = (pj.get('body') or {}).get('entries') or {}
    for s in pj.get('sites', []):
        a, orig = int(s['address'], 16), int(s['orig_word'], 16)
        if word(a) != orig:
            raise BuildError(f'lz4fast {a:#x}: image {word(a):#x} != {orig:#x}')
        ent = s.get('entry') or (next(iter(entries)) if len(entries) == 1 else None)
        if ent is None:
            raise BuildError(f'lz4fast site {a:#x}: which entry?')
        rows.append(('bl', a, orig, ent))
    if not rows:
        raise BuildError('lz4fast patch.json lists no patches/sites')
    # its own enable word must ship as 1: pf_lz is the switch (gate stub)
    en = ((pj.get('body') or {}).get('control') or {}).get('enable')
    if en is not None and struct.unpack_from('<I', code, en)[0] != 1:
        raise BuildError('lz4fast ships with its own enable off; pf_lz could not turn it on')
    return code, sym, rows, en


def thumb_bl_target(at, hw):
    h1, h2 = hw
    if h1 & 0xF800 != 0xF000 or h2 & 0xD000 != 0xD000:
        raise BuildError(f'{at:#x}: {h1:04x} {h2:04x} is not a Thumb bl')
    S = (h1 >> 10) & 1
    i1 = 1 - (((h2 >> 13) & 1) ^ S)
    i2 = 1 - (((h2 >> 11) & 1) ^ S)
    imm = (S << 24) | (i1 << 23) | (i2 << 22) | ((h1 & 0x3FF) << 12) | ((h2 & 0x7FF) << 1)
    if S:
        imm -= 1 << 25
    return at + 4 + imm


def halfwords(a):
    o = a - B
    return struct.unpack_from('<HH', IMAGE, o)


def module_inputredraw():
    d = PERF / 'inputredraw'
    pj = json.loads((d / 'patch.json').read_text())
    code = assemble(d / 'inputredraw.S')
    if sha(code) != pj['body']['sha256']:
        raise BuildError('inputredraw.S no longer matches its patch.json')
    sym = symbols(d / 'inputredraw.S')
    (s,) = pj['sites']
    a, orig = int(s['address'], 16), int(s['orig_word'], 16)
    if word(a) != orig or bl_target(a, orig) != 0xC055E1E8:
        raise BuildError(f'inputredraw {a:#x}: image {word(a):#x} != {orig:#x}')
    if struct.unpack_from('<I', code, pj['body']['control']['enable'])[0] != 1:
        raise BuildError('inputredraw enable offset moved')
    return code, {'ir_enq_hook': sym['ir_enq_hook']}, (a, orig)


def module_iconcache():
    d = PERF / 'iconcache'
    pj = json.loads((d / 'patch.json').read_text())
    code = assemble(d / 'iconcache.S')
    if sha(code) != pj['body']['sha256']:
        raise BuildError('iconcache.S no longer matches its patch.json')
    c = pj['body']['control']
    if (c['enable'], c['arena'], c['arena_size']) != (4, 8, 12):
        raise BuildError('iconcache control offsets moved')
    if struct.unpack_from('<4I', code, 4) != (0, 0, 0, 0x80000):
        raise BuildError('iconcache ships with EN/ARENA set or MAXENT changed')
    sym = symbols(d / 'iconcache.S')
    sites = {}
    for st in pj['sites']:
        a, orig = int(st['address'], 16), int(st['orig_word'], 16)
        if a & 3 or word(a) != orig:
            raise BuildError(f'iconcache {a:#x}: image {word(a):#x} != {orig:#x}')
        sites[st['name']] = (a, orig)
    if sites['h1'] != (0xC060219C, 0x46586B71) or sites['h2'] != (0xC060234C, 0x92243204):
        raise BuildError('iconcache sites are not the ones the master gates replay')
    return code, {'ic_h1': sym['ic_h1'], 'ic_h2': sym['ic_h2']}, sites


def module_pagelru():
    d = PERF / 'pagelru'
    pj = json.loads((d / 'patch.json').read_text())
    code = assemble(d / 'pagelru.S')
    if sha(code) != pj['body']['sha256']:
        raise BuildError('pagelru.S no longer matches its patch.json')
    if struct.unpack_from('<I', code, 4)[0] != 0:
        raise BuildError('pagelru ships enabled')
    sym = symbols(d / 'pagelru.S')
    sites = {}
    for st in pj['sites']:
        a = int(st['address'], 16)
        hw = tuple(int(h, 16) for h in st['orig_halfwords'])
        if halfwords(a) != hw:
            raise BuildError(f'pagelru {a:#x}: image {halfwords(a)} != {hw}')
        sites[st['name']] = (a, hw, thumb_bl_target(a, hw))
    if sites['load'][2] != 0xC05D90F0 or sites['unload'][2] != 0xC05D91A0:
        raise BuildError('pagelru sites do not call the stock load/unload')
    return code, {'pl_load': sym['pl_load'], 'pl_unload': sym['pl_unload']}, sites


def module_alphalut():
    d = PERF / 'alphalut'
    pj = json.loads((d / 'patch.json').read_text())
    code = assemble(d / 'alphalut.S')
    if sha(code) != pj['code_sha256']:
        raise BuildError('alphalut.S no longer matches its patch.json')
    if code[:4] != b'ALUT' or struct.unpack_from('<I', code, 8)[0] != 1:
        raise BuildError('alphalut header/enable offset moved')
    sym = symbols(d / 'alphalut.S')
    if sym['al_unpremul'] != pj['symbols']['al_unpremul']:
        raise BuildError('alphalut entry moved')
    (st,) = pj['patches']
    a, orig = int(st['addr'], 16), int(st['stock'], 16)
    if word(a) != orig or bl_target(a, orig) != 0xC0563BA8:
        raise BuildError(f'alphalut {a:#x}: image {word(a):#x} != {orig:#x}')
    return code, {'al_unpremul': sym['al_unpremul']}, (a, orig)


def module_waveform():
    d = PERF / 'waveform'
    pj = json.loads((d / 'patch.json').read_text())
    code = assemble(d / 'waveform.S')
    if sha(code) != pj['code_sha256']:
        raise BuildError('waveform.S no longer matches its patch.json')
    if code[:4] != b'WAVE' or struct.unpack_from('<I', code, 4)[0] != 1:
        raise BuildError('waveform header/enable offset moved')
    sym = symbols(d / 'waveform.S')
    if sym['wf_method'] != pj['symbols']['wf_method']:
        raise BuildError('waveform entry moved')
    slots = []
    for p in pj['patches']:
        a, stock = int(p['addr'], 16), int(p['stock'], 16)
        if word(a) != stock or stock != WF_STOCK:
            raise BuildError(f'waveform {a:#x}: image {word(a):#x} != {stock:#x}')
        slots.append(a)
    if tuple(slots) != WF_SLOTS:
        raise BuildError('waveform slots changed')
    return code, {'wf_method': sym['wf_method']}, slots


def claim_rows(a, n):
    """(addr, [stock words]) covering [a, a+n) on 4-byte boundaries."""
    lo, hi = a & ~3, (a + n + 3) & ~3
    return (lo, [word(x) for x in range(lo, hi, 4)])


def generate(tmp, mods, lz):
    nb_code, nb_sym, spans = mods['nb']
    fd_code, fd_sym = mods['fd']
    dc_code, dc_sym, dc_sites = mods['dc']
    bins = {}
    opt = [k for k in OPTIONAL if k in mods]
    order = ('dc', 'fd', 'nb') + tuple(opt) + (('lz',) if lz else ())
    for k in order:
        c = lz[0] if k == 'lz' else mods[k][0]
        p = tmp / f'{k}.bin'
        p.write_bytes(c)
        bins[k] = p
    g, claims, writes = [], [], []      # writes: (addr, type, phase, label)
    # types: 0 data word, 1 ARM bl, 2 Thumb blx (2-aligned, ARM veneer), 3 Thumb b.w (Thumb veneer)

    def gate_m(label, target, stock):   # master only; the module checks its own enable
        g.extend([f'{label}:',
                  '        ldr     ip, pf_master', '        cmp     ip, #0', f'        bne     {target}',
                  '        ldr     pc, 1f', f'1:      .word   {stock:#010x}'])

    # new modules: gates first, they read pf_master pc-relative
    if 'ir' in mods:
        gate_m('pf_g_ir', 'ir_enq_hook', 0xC055E1E8)
    if 'al' in mods:
        gate_m('pf_g_al', 'al_unpremul', 0xC0563BA8)
    if 'wf' in mods:
        gate_m('pf_g_wf', 'wf_method', WF_STOCK)
    if 'pl' in mods:
        pl_sites = mods['pl'][2]
        gate_m('pf_g_pl_load', 'pl_load', pl_sites['load'][2] | 1)
        gate_m('pf_g_pl_unload', 'pl_unload', pl_sites['unload'][2] | 1)
    # iconcache sites are mid-function: master off replays the two stock
    # instructions exactly as the module's own disabled path does (r1 is dead
    # at both sites: h1 overwrites it, h2 returns through it)
    if 'ic' in mods:
      g.extend(['pf_g_ic1:',
              '        ldr     r1, pf_master', '        cmp     r1, #0', '        bne     ic_h1',
              '        ldr     r1, [r6, #0x34]', '        mov     r0, r11',
              '        ldr     ip, 1f', '        bx      ip', '1:      .word   0xC06021A1',
              'pf_g_ic2:',
              '        ldr     r1, pf_master', '        cmp     r1, #0', '        bne     ic_h2',
              '        adds    r2, r2, #4', '        str     r2, [sp, #0x90]',
              '        ldr     r1, 1f', '        bx      r1', '1:      .word   0xC0602351'])

    # gate stubs first: they read pf_master/pf_nb/pf_lz pc-relative (< 4 KiB)
    def gate(label, switch_off, target, stock):
        g.extend([f'{label}:',
                  '        ldr     ip, pf_master', '        cmp     ip, #0',
                  f'        ldrne   ip, {switch_off}',
                  '        cmpne   ip, #0', f'        bne     {target}',
                  '        ldr     pc, 1f', f'1:      .word   {stock:#010x}'])

    for i, (a, stock, s) in enumerate(spans):
        claims.append((a, stock))
        if a in FILL_SLOTS:
            if stock != FW_FILL:
                raise BuildError(f'{a:#x} is not the stock fill')
            writes.append((a, 0, 1, 'pf_layer_fill'))
        else:
            gate(f'pf_g_nb{i}', 'pf_nb', s, stock)
            writes.append((a, 0, 1, f'pf_g_nb{i}'))
    if sorted(a for a, _, s in spans if a in FILL_SLOTS) != sorted(FILL_SLOTS):
        raise BuildError('neonblit no longer lists both fill slots')
    for name, a, orig, _target in dc_sites:
        claims.append((a, orig))
        label = {'copy': 'dc_copy_hook', 'clear': 'dc_clear_hook', 'clean': 'pf_dc_gate'}[name]
        writes.append((a, 1, 2 if name == 'clean' else 1, label))
    if lz:
        for i, (kind, a, orig, s) in enumerate(lz[2]):
            claims.append((a, orig))
            stock = orig if kind == 'data' else bl_target(a, orig)
            gate(f'pf_g_lz{i}', 'pf_lz', f'lz_{s}', stock)
            writes.append((a, 0 if kind == 'data' else 1, 1, f'pf_g_lz{i}'))

    # phase 1: ir, al, wf, pagelru unload, iconcache h2; phase 2: pagelru load, iconcache h1 (+ dc clean)
    if 'ir' in mods:
        a, orig = mods['ir'][2]
        claims.append((a, orig))
        writes.append((a, 1, 1, 'pf_g_ir'))
    if 'al' in mods:
        a, orig = mods['al'][2]
        claims.append((a, orig))
        writes.append((a, 1, 1, 'pf_g_al'))
    if 'wf' in mods:
        for a in mods['wf'][2]:
            claims.append((a, WF_STOCK))
            writes.append((a, 0, 1, 'pf_g_wf'))
    if 'pl' in mods:
        a, hw, _t = mods['pl'][2]['unload']
        lo, ws = claim_rows(a, 4)
        claims.append((lo, ws))
        writes.append((a, 2, 1, 'pf_g_pl_unload'))
    if 'ic' in mods:
        a, orig = mods['ic'][2]['h2']
        claims.append((a, orig))
        writes.append((a, 3, 1, 'pf_g_ic2'))
    if 'pl' in mods:
        a, hw, _t = mods['pl'][2]['load']
        lo, ws = claim_rows(a, 4)            # C05DD5CA: declare C05DD5C8..CF
        claims.append((lo, ws))
        writes.append((a, 2, 2, 'pf_g_pl_load'))
    if 'ic' in mods:
        a, orig = mods['ic'][2]['h1']
        claims.append((a, orig))
        writes.append((a, 3, 2, 'pf_g_ic1'))

    addrs = [a for a, _ in claims]
    if len(set(addrs)) != len(addrs):
        raise BuildError('two modules patch the same word')
    spans_c = sorted((a, 4 * len(s) if isinstance(s, list) else 4) for a, s in claims)
    for (a0, n0), (a1, _n1) in zip(spans_c, spans_c[1:]):
        if a0 + n0 > a1:
            raise BuildError(f'claims overlap at {a1:#x}')
    n_ven = sum(1 for w in writes if w[1] != 0)

    g.append('        .ltorg')
    g.append('pf_claims:')
    g.append(f'        .word   {len(claims)}')
    for a, stock in claims:
        ws = stock if isinstance(stock, list) else [stock]
        g.append(f'        .word   {a:#010x}, {4 * len(ws)}, {SL_EXCL}, ' + ', '.join(f'{w:#010x}' for w in ws))
    g.append('pf_writes:')
    g.append(f'        .word   {len(writes)}')
    for a, t, ph, label in writes:
        g.append(f'        .word   {a:#010x}, {t}, {ph}, {label} - pf_body')
    for k in order:
        g += ['        .balign 8', f'{k}_mod:', f'        .incbin "{bins[k]}"']
    for s, off in dc_sym.items():
        g.append(f'        .set    {s}, dc_mod + {off:#x}')
    g.append(f'        .set    fd_layer_fill, fd_mod + {fd_sym["fd_layer_fill"]:#x}')
    for s, off in nb_sym.items():
        g.append(f'        .set    {s}, nb_mod + {off:#x}')
    for k in OPTIONAL:
        if k in mods:
            for s, off in mods[k][1].items():
                g.append(f'        .set    {s}, {k}_mod + {off:#x}')
            g.append(f'        .set    {k.upper()}_MOD_OFF, {k}_mod - pf_body')
        else:
            g.append(f'        .set    {k.upper()}_MOD_OFF, 0')
    if lz:
        for s, off in lz[1].items():
            if not s.startswith('$'):
                g.append(f'        .set    lz_{s}, lz_mod + {off:#x}')
        g.append('        .set    LZ_MOD_OFF, lz_mod - pf_body')
    else:
        g.append('        .set    LZ_MOD_OFF, 0')
    g.append('pf_end:')
    inc = tmp / 'gen.inc'
    inc.write_text('\n'.join(g) + '\n')
    return inc, claims, writes, n_ven


LOADERS = {'ir': lambda: module_inputredraw(), 'ic': lambda: module_iconcache(),
           'pl': lambda: module_pagelru(), 'al': lambda: module_alphalut(), 'wf': lambda: module_waveform()}


def build(enable=(), master=1, mods=None, core=HERE / 'perf_core.S', gen_patch=None, without=()):
    """gen_patch: (old, new) applied to the generated gen.inc -- mutation tests only.
    without: OPTIONAL modules left out entirely (no code, no claim, no arena)."""
    bad = set(without) - set(OPTIONAL)
    if bad:
        raise BuildError(f'cannot leave out {sorted(bad)} (only {OPTIONAL})')
    if mods is None:
        mods = {'nb': module_neonblit(), 'fd': module_filldma(), 'dc': module_dirtyclean()}
        mods.update({k: LOADERS[k]() for k in OPTIONAL if k not in without})
    else:
        mods = {k: v for k, v in mods.items() if k not in without}
        for k in OPTIONAL:
            if k not in mods and k not in without:
                mods[k] = LOADERS[k]()
    if set(enable) & set(without):
        raise BuildError(f'cannot enable a left-out module {sorted(set(enable) & set(without))}')
    lz = module_lz4fast()
    if 'lz' in enable and not lz:
        raise BuildError('lz4fast is not built yet')
    with tempfile.TemporaryDirectory(prefix='perfsup-') as t:
        tmp = pathlib.Path(t)
        inc, claims, writes, n_ven = generate(tmp, mods, lz)
        if gen_patch:
            text = inc.read_text()
            if text.count(gen_patch[0]) < 1:
                raise BuildError('gen_patch pattern not found')
            inc.write_text(text.replace(*gen_patch))
        defs = {'GEN_INC': f'"{inc}"', 'N_VENEERS': n_ven,
                'PF_MASTER_INIT': int(bool(master)),
                'PF_NB_INIT': int('nb' in enable), 'PF_LZ_INIT': int('lz' in enable),
                'DC_EN_INIT': int('dc' in enable), 'FD_EN_INIT': int('fd' in enable),
                'IR_EN_INIT': int('ir' in enable), 'IC_EN_INIT': int('ic' in enable),
                'PL_EN_INIT': int('pl' in enable), 'AL_EN_INIT': int('al' in enable),
                'WF_EN_INIT': int('wf' in enable), 'IC_ARENA': IC_ARENA,
                **{f'HAS_{k.upper()}': int(k in mods) for k in OPTIONAL},
                'PF_BUILD_ID': 0}
        dl = [f'{k}={v}' for k, v in defs.items()]
        body = assemble(core, dl)
        bid = int(sha(body)[:8], 16)
        dl[-1] = f'PF_BUILD_ID={bid:#x}'
        body = assemble(core, dl)
        sym = symbols(core, dl)
    import build_v3 as BV3
    file_len = (HEADER + len(body) + 3) & ~3
    arena = IC_ARENA if 'ic' in mods else 0
    block = HEADER + sym['pf_end'] + 7 + arena      # arena = align8(pf_end) .. +IC_ARENA (ic only)
    block = max(block, file_len)
    blob = BV3.make_sup(body, HEADER + sym['pf_entry'], SUP_ID, VERSION, block_size=block, min_svc=1)
    info = {'name': NAME, 'bytes': len(blob), 'sha256': sha(blob), 'build_id': f'{bid:08x}',
            'entry': HEADER + sym['pf_entry'],
            'body_offsets': {k: sym[k] for k in ('pf_body', 'pf_master', 'pf_nb', 'pf_lz', 'pf_state',
                                                  'pf_layer_fill', 'pf_dc_gate', 'pf_entry', 'dc_mod',
                                                  'fd_mod', 'nb_mod', 'pf_end')
                             if k in sym},
            'modules': sorted(k for k in mods),
            'without': sorted(set(OPTIONAL) - set(mods)),
            'block_size': block, 'ic_arena': arena,
            'switches_initial': {'master': int(bool(master)), 'nb': int('nb' in enable),
                                 'dc': int('dc' in enable), 'fd': int('fd' in enable),
                                 'lz': int('lz' in enable), 'ir': int('ir' in enable),
                                 'ic': int('ic' in enable), 'pl': int('pl' in enable),
                                 'al': int('al' in enable), 'wf': int('wf' in enable)},
            'lz4fast': bool(lz),
            'claims': [{'addr': f'{a:#010x}', 'bytes': 4 * len(s) if isinstance(s, list) else 4,
                        'stock': ' '.join(f'{w:#010x}' for w in (s if isinstance(s, list) else [s]))}
                       for a, s in claims],
            'writes': [{'addr': f'{a:#010x}', 'type': ['data', 'bl', 'thumb-blx', 'thumb-b.w'][t],
                        'phase': p, 'target': l}
                       for a, t, p, l in writes],
            'veneers': n_ven,
            'modules_sha256': {n: sha(mods[k][0]) for k, n in
                               (('nb', 'neonblit'), ('fd', 'filldma'), ('dc', 'dirtyclean'),
                                ('ir', 'inputredraw'), ('ic', 'iconcache'), ('pl', 'pagelru'),
                                ('al', 'alphalut'), ('wf', 'waveform')) if k in mods}}
    for k in OPTIONAL:
        if k in mods:
            info['body_offsets'][f'{k}_mod'] = sym[f'{k}_mod']
    return blob, info, sym


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=pathlib.Path, default=HERE / 'out')
    ap.add_argument('--enable', default='', help='comma list of dc,nb,fd,lz,ir,ic,pl,al,wf or "all"')
    ap.add_argument('--without', default='', help='comma list of ir,ic,pl,al,wf to leave out')
    ap.add_argument('--master', type=int, default=1)
    a = ap.parse_args()
    wo = {x for x in a.without.split(',') if x}
    en = (set(FEATURES) - wo - (set() if module_lz4fast() else {'lz'})) if a.enable == 'all' \
        else {x for x in a.enable.split(',') if x}
    bad = en - set(FEATURES)
    if bad:
        raise SystemExit(f'unknown feature {bad}')
    blob, info, _ = build(en, a.master, without=wo)
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / NAME).write_bytes(blob)
    (a.out / 'build.json').write_text(json.dumps(info, indent=1) + '\n')
    print(f'{a.out / NAME}: {len(blob)} B sha256 {info["sha256"][:16]} switches {info["switches_initial"]} '
          f'claims {len(info["claims"])} veneers {info["veneers"]} lz4fast {info["lz4fast"]} '
          f'without {info["without"]} block {info["block_size"]}')


if __name__ == '__main__':
    main()
