"""res-custom's format data files (RCD1) and the Quick Set scheme B, in Python.

notes/OG_MULTIFORMAT_CORE_DESIGN.md §13 (scheme B) and §14 (data files).

    encode(row, pack)      one format's \\fpSup\\RESCUS\\<LABEL>.RCD
    decode(data)           the same checks ogc.c makes, raising RcdError(why)
    ui_template()          the core's FPUI block template (uishare ops, no code
                           from the data file: the strings are substituted)
    ui_block(tpl, ...)     the block ogc.c builds from the template for one row
    qs_target(...)         scheme B on one NBU record (the reference ogc.c is
                           tested against)

A data file holds parameters only: the picker entries, the virtual modes'
overrides, the canvas lists, two texts and the private image pack.  The code
that uses them -- recording, menu, Quick Set -- is all in the core.
"""
import pathlib
import struct
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[3]
UISHARE = ROOT / 'fpSup' / 'uishare'
sys.path.insert(0, str(HERE))
import ogc_layout as L                                    # noqa: E402

H = L.RCD


class RcdError(ValueError):
    def __init__(self, why, text=''):
        super().__init__(f'{why}: {text}')
        self.why = why


def fnv(b):
    h = 0x811C9DC5
    for x in b:
        h = ((h ^ x) * 0x01000193) & 0xFFFFFFFF
    return h


def _text_ok(t, n, label=False):
    b = t.encode('latin1')
    if not 0 < len(b) < n:
        return False
    if label:
        return all(48 <= c <= 57 or 65 <= c <= 90 or 97 <= c <= 122 for c in b)
    return all(0x20 <= c <= 0x7E and c not in b',@"' for c in b)


# ---- the file -------------------------------------------------------------------
def encode(row, pack, version=None, mincore=None, extra=()):
    """row: ogc_rowdata.py's dict (+ optional 'overrides' [(donor, kind, off, value)]).
    extra: more (type, flags, bytes) sections (tests: unknown types)."""
    lab = row['label']
    if mincore is None:
        mincore = 2 if row.get('aspect', 2) == 9 else 1
    if 'binning' in row:
        mincore = max(mincore, 3)
    if 'bit_depths' in row:
        mincore = max(mincore, 4)
    if row.get('writer') or 'rates' in row:
        # 'rates' present, even empty, is a declaration; a v4 file has none (core
        # 5 reads it as the rates core 4 offered)
        mincore = max(mincore, 5)
    rates = [dict(r) for r in row.get('rates', ())]
    if not _text_ok(lab, 8, label=True):
        raise RcdError('FIELD', f'label {lab!r}')
    # v3 (2026-10-08): the modes and their fastest rate; the core makes the entries
    modes = [tuple(m) for m in row['modes']]
    if not 0 < len(modes) <= L.RCD_MAX_MODES:
        raise RcdError('ENTRY', 'one to four modes')
    md = struct.pack('<I', len(modes))
    for m in modes:
        if len(m) != 5 or not 0 < m[1] <= 100000 or not 0 < m[2] < 0x10000 or not 0 <= m[3] < 0x10000:
            raise RcdError('ENTRY', repr(m))
        md += struct.pack('<5I', *m)
    if not L.gen_entries(lab, modes, row.get('flags', 0), rates):
        raise RcdError('ENTRY', 'no rate fits any mode')
    cv = struct.pack('<8I', row['prev_h'], row['act'][0], row['act'][1], len(row['canvas_rec']),
                     len(row['canvas_pb']), 0, 0, 0)
    for off, v in list(row['canvas_rec']) + list(row['canvas_pb']):
        cv += struct.pack('<2I', off, v)
    ui = row['row_text'].encode().ljust(L.RCD_UI_ROW, b'\0') + \
        row['summary'].encode().ljust(L.RCD_UI_SUM, b'\0')
    secs = [(L.SEC_MODES, 1, md), (L.SEC_CANVAS, 1, cv), (L.SEC_UI, 1, ui)]
    if 'bit_depths' in row:
        depths = tuple(row['bit_depths'])
        if not depths or len(set(depths)) != len(depths) or any(d not in L.BIT_DEPTHS for d in depths):
            raise RcdError('BITDEPTH')
        mask = sum(1 << L.BIT_DEPTHS.index(d) for d in depths)
        secs.append((L.SEC_BITDEPTH, 1, struct.pack('<I', mask)))
    if 'binning' in row:
        bh,bv,kh,kv,mode = row['binning']
        if bh not in (1,3) or bv not in (1,3) or not 0 <= kh < 6 or not 0 <= kv < 6 or mode not in (0,1):
            raise RcdError('BINFILT')
        secs.append((L.SEC_BINFILT, 1, struct.pack('<5I',bh,bv,kh,kv,mode)))
    if row.get('standby'):
        sb = struct.pack('<I', len(row['standby']))
        for g in row['standby']:
            pids, pairs, cond = g[0], g[1], (g[2] if len(g) > 2 else 0)
            sb += struct.pack('<2I', cond << 16 | len(pids), len(pairs)) + struct.pack(f'<{len(pids)}I', *pids)
            for off, v in pairs:
                sb += struct.pack('<2I', off, v)
        secs.append((L.SEC_STANDBY, 1, sb))
    if row.get('rate_canvas'):
        if len(row['rate_canvas']) > L.RCD_MAX_RCANVAS:
            raise RcdError('ENTRY', 'too many rate canvases')
        rc = struct.pack('<I', len(row['rate_canvas']))
        for x in row['rate_canvas']:
            rc += struct.pack('<4I', x['rank'], x['crop'], x.get('base_profile', 0), len(x['pairs']))
            for off, v in x['pairs']:
                rc += struct.pack('<2I', off, v)
        secs.append((L.SEC_RATECANVAS, 1, rc))
    if version is None:
        version = L.RCD_VERSION
    if row.get('overrides'):
        vm = struct.pack('<I', len(row['overrides']))
        for o in row['overrides']:
            vm += struct.pack('<4I', *o)
        secs.append((L.SEC_VMODES, 1, vm))
    if row.get('capture_timing'):
        # A required section prevents older cores silently recording at the
        # carrier rate. UI/container rates retain the generated entry key.
        timings = row['capture_timing']
        st = struct.pack('<I', len(timings))
        for timing in timings:
            st += struct.pack('<6I', *timing)
        secs.append((L.SEC_CAPTURE_TIMING, 1, st))
    if row.get('writer'):
        # Required: an older core would record with the native writer policy.
        wr = list(row['writer'])
        if not 0 < len(wr) <= L.RCD_MAX_WRITER:
            raise RcdError('WRITER')
        sw = struct.pack('<I', len(wr))
        for rank, crop, bits, fl in wr:
            sw += struct.pack('<4I', rank, crop, bits, fl)
        secs.append((L.SEC_WRITER, 1, sw))
    if rates:
        # Required: an older core would record these keys at their carrier rate.
        if len(rates) > L.RCD_MAX_RATES:
            raise RcdError('RATES')
        sr = struct.pack('<I', len(rates))
        for r in rates:
            sr += struct.pack('<7I', r['rank'], r['num'], r['den'], r['cycles'], r['carrier'],
                              r['nominal'], r['engine'])
        secs.append((L.SEC_RATES, 1, sr))
    secs += list(extra)
    secs.append((L.SEC_PACK, 1, pack))
    table_off = L.RCD_HDR
    body = bytearray(L.RCD_HDR + L.RCD_SEC_BYTES * len(secs))
    rows = []
    for typ, flags, data in secs:
        align = 64 if typ == L.SEC_PACK else 4
        body += bytes(-len(body) % align)
        rows.append((typ, len(body), len(data), flags))
        body += data
    body += bytes(-len(body) % 4)
    for i, r in enumerate(rows):
        struct.pack_into('<4I', body, table_off + L.RCD_SEC_BYTES * i, *r)
    struct.pack_into('<I', body, H['MAGIC'], L.RCD_MAGIC)
    struct.pack_into('<I', body, H['VERSION'], version)
    struct.pack_into('<I', body, H['HLEN'], L.RCD_HDR)
    struct.pack_into('<I', body, H['FLEN'], len(body))
    struct.pack_into('<I', body, H['NSEC'], len(secs))
    struct.pack_into('<I', body, H['SECOFF'], table_off)
    struct.pack_into('<I', body, H['STOCK'], row['stock_value'])
    struct.pack_into('<I', body, H['ASPECT'], row.get('aspect', 2))
    struct.pack_into('<I', body, H['FLAGS'], row.get('flags', 1 if row.get('clamp') else 0))
    struct.pack_into('<I', body, H['MAXRATE'], max(m[1] for m in modes))
    struct.pack_into('<I', body, H['PROFILE'], row['profile'])
    struct.pack_into('<I', body, H['MINCORE'], mincore)
    body[H['LABEL']:H['LABEL'] + 8] = lab.encode().ljust(8, b'\0')
    struct.pack_into('<I', body, H['ENUM'], row['enum'])
    struct.pack_into('<I', body, H['SUM'], fnv(body[L.RCD_HDR:]))
    return bytes(body)


def reseal(data):
    """The file with its FNV made again (tests change fields)."""
    b = bytearray(data)
    struct.pack_into('<I', b, H['SUM'], fnv(b[L.RCD_HDR:]))
    return bytes(b)


def decode(data, image=None, stock_ids=None):
    """What ogc.c accepts, as a dict; RcdError(why) where ogc.c refuses.
    image/stock_ids: check the base profile and the donors as ogc.c does."""
    n = len(data)
    if n < L.RCD_HDR or n > L.RCD_MAX_FILE or n % 4:
        raise RcdError('SIZE')
    w = lambda o: struct.unpack_from('<I', data, o)[0]               # noqa: E731
    if w(H['MAGIC']) != L.RCD_MAGIC:
        raise RcdError('MAGIC')
    if w(H['VERSION']) not in L.RCD_VERSIONS or w(H['HLEN']) != L.RCD_HDR:
        raise RcdError('VERSION')
    if w(H['MINCORE']) > L.CORE_VERSION:
        raise RcdError('NEWER')
    if w(H['FLEN']) != n:
        raise RcdError('SIZE')
    if w(H['SUM']) != fnv(data[L.RCD_HDR:]):
        raise RcdError('SUM')
    lab = data[H['LABEL']:H['LABEL'] + 8]
    if lab[7] != 0:
        raise RcdError('FIELD', 'label')
    raw, lab = lab, lab.split(b'\0')[0]
    if any(raw[len(lab):]) or not _text_ok(lab.decode('latin1'), 8, label=True):
        raise RcdError('FIELD', 'label')
    if w(H['STOCK']) not in (2, 3) or w(H['ASPECT']) not in (2, 3, 9) or w(H['FLAGS']) & ~15 or \
            (w(H['ASPECT']) == 9 and w(H['MINCORE']) < 2):
        raise RcdError('FIELD')
    if w(H['FLAGS']) & L.RFLAG_CROP and len(lab) > 6:       # label + "23_98CROP" fits 15
        raise RcdError('FIELD')
    ns, so = w(H['NSEC']), w(H['SECOFF'])
    if not 0 < ns <= L.RCD_MAX_SECS or so < L.RCD_HDR or so % 4 or so + L.RCD_SEC_BYTES * ns > n:
        raise RcdError('SECTION')
    secs = {}
    for i in range(ns):
        typ, off, ln, flags = struct.unpack_from('<4I', data, so + L.RCD_SEC_BYTES * i)
        if off < L.RCD_HDR or off % 4 or ln > n - off or flags & ~1:
            raise RcdError('SECTION')
        if typ not in (L.SEC_MODES, L.SEC_VMODES, L.SEC_CANVAS, L.SEC_UI, L.SEC_PACK,
                       L.SEC_STANDBY, L.SEC_RATECANVAS, L.SEC_BINFILT, L.SEC_CAPTURE_TIMING,
                       L.SEC_BITDEPTH, L.SEC_WRITER, L.SEC_RATES):
            if flags & 1:
                raise RcdError('UNKNOWN')
            continue
        if typ in secs:
            raise RcdError('SECTION', 'twice')
        if typ == L.SEC_CAPTURE_TIMING and flags != 1:
            raise RcdError('ENTRY', 'sensor timing must be required')
        if typ == L.SEC_BITDEPTH and flags != 1:
            raise RcdError('BITDEPTH', 'bit-depth policy must be required')
        if typ == L.SEC_WRITER and flags != 1:
            raise RcdError('WRITER', 'writer policy must be required')
        if typ == L.SEC_RATES and flags != 1:
            raise RcdError('RATES', 'declared rates must be required')
        secs[typ] = (off, ln)
    for t in (L.SEC_MODES, L.SEC_CANVAS, L.SEC_UI, L.SEC_PACK):
        if t not in secs:
            raise RcdError('SECTION', f'missing {t}')
    out = {'label': lab.decode(), 'stock_value': w(H['STOCK']), 'aspect': w(H['ASPECT']),
           'clamp': w(H['FLAGS']) & 1, 'flags': w(H['FLAGS']), 'maxrate': w(H['MAXRATE']),
           'profile': w(H['PROFILE']), 'enum': w(H['ENUM'])}
    if image is not None:
        out['base_row'] = _base_row(image, out['profile'])
    off, ln = secs[L.SEC_MODES]
    nm = w(off) if ln >= 4 else 0
    if not 0 < nm <= L.RCD_MAX_MODES or ln != 4 + L.RCD_MODE_BYTES * nm:
        raise RcdError('ENTRY')
    modes = [struct.unpack_from('<5I', data, off + 4 + L.RCD_MODE_BYTES * i) for i in range(nm)]
    for donor, mx, hm, pal, x in modes:
        if not 0 < mx <= 100000 or not 0 < hm < 0x10000 or pal >= 0x10000 or x >= 0x10000 or \
                (stock_ids is not None and donor not in stock_ids):
            raise RcdError('ENTRY')
    if w(H['MAXRATE']) != max(m[1] for m in modes):
        raise RcdError('FIELD')
    if L.SEC_BITDEPTH in secs:
        off, ln = secs[L.SEC_BITDEPTH]
        if w(H['MINCORE']) < 4 or ln != 4 or not 0 < w(off) < 8:
            raise RcdError('BITDEPTH')
        out['bit_depths'] = tuple(d for j, d in enumerate(L.BIT_DEPTHS) if w(off) & (1 << j))
    out['rates'] = []
    if L.SEC_RATES in secs:
        off, ln = secs[L.SEC_RATES]
        nr = w(off) if ln >= 4 else 0
        if w(H['MINCORE']) < 5 or not 0 < nr <= L.RCD_MAX_RATES or ln != 4 + L.RCD_RATE_BYTES * nr:
            raise RcdError('RATES')
        for i in range(nr):
            rk, num, den, cyc, en, nom, eng = struct.unpack_from('<7I', data, off + 4 + L.RCD_RATE_BYTES * i)
            if not 0 < num <= 1000000 or not 0 < den <= 100000 or rk in L.ALL_RANKS or \
                    rk != num * 100 // den or cyc * num != L.CLOCK * den or en not in L.RATE_ROW or \
                    not 1 <= nom <= 1000 or not 0x3f800000 <= eng <= 0x447a0000 or \
                    any(r['rank'] == rk for r in out['rates']):
                raise RcdError('RATES')
            out['rates'].append({'rank': rk, 'num': num, 'den': den, 'cycles': cyc, 'carrier': en,
                                 'nominal': nom, 'engine': eng})
    elif w(H['MINCORE']) < 5:
        # written before SEC_RATES: such a file was recorded by a core that offered
        # its own rates -- read it as declaring those (ogc.c rate_word, the same rule)
        out['rates'] = [dict(r) for r in L.DEFAULT_RATES]
    ranks = L.ALL_RANKS + tuple(r['rank'] for r in out['rates'])
    out['modes'] = modes
    out['entries'] = L.gen_entries(out['label'], modes, out['flags'], out['rates'])
    if not out['entries'] or len(out['entries']) > L.MAX_GEN:
        raise RcdError('ENTRY')
    out['capture_timing'] = []
    if L.SEC_CAPTURE_TIMING in secs:
        off, ln = secs[L.SEC_CAPTURE_TIMING]
        nt = w(off) if ln >= 4 else 0
        if not 0 < nt <= L.MAX_GEN or ln != 4 + 24 * nt:
            raise RcdError('ENTRY', 'sensor timing length')
        seen = set()
        for i in range(nt):
            rank, crop, tw0, tw1, eng, nominal = struct.unpack_from('<6I', data, off + 4 + 24*i)
            entry = next((e for e in out['entries'] if e['rank'] == rank and e['crop'] == crop), None)
            if (rank, crop) in seen or entry is None or (tw0 & 0xffff) != (entry['w0'] & 0xffff) or \
                    (tw0 >> 16) < L.MIN_TAIL or (tw1 & 0xffff) < 2 or (tw1 >> 16) != (entry['w1'] >> 16):
                raise RcdError('ENTRY', 'sensor timing fields')
            seen.add((rank, crop))
            if not 0x3f800000 <= eng <= 0x447a0000 or not 1 <= nominal <= 1000:
                raise RcdError('ENTRY', 'capture engine/nominal')
            entry.update(w0=tw0, w1=tw1, engfps=eng, nominal=nominal)
            out['capture_timing'].append((rank, crop, tw0, tw1, eng, nominal))
    out['writer'] = []
    if L.SEC_WRITER in secs:
        off, ln = secs[L.SEC_WRITER]
        nw = w(off) if ln >= 4 else 0
        if w(H['MINCORE']) < 5 or not 0 < nw <= L.RCD_MAX_WRITER or ln != 4 + 16 * nw:
            raise RcdError('WRITER')
        for i in range(nw):
            rank, crop, bits, fl = struct.unpack_from('<4I', data, off + 4 + 16 * i)
            if (rank and rank not in ranks) or crop > (1 if w(H['FLAGS']) & L.RFLAG_CROP else 0) or \
                    not 0 < bits < 8 or not fl or fl & ~(L.WR_BATCH4M | L.WR_HDRCPU) or \
                    any(r == rank and c == crop for r, c, _, _ in out['writer']):
                raise RcdError('WRITER')
            out['writer'].append((rank, crop, bits, fl))
    off, ln = secs[L.SEC_CANVAS]
    if ln < L.RCD_CANVAS_HEAD:
        raise RcdError('CANVAS')
    prev_h, aw, ah, nr, npb, z0, z1, z2 = struct.unpack_from('<8I', data, off)
    if z0 or z1 or z2 or nr > L.RCD_MAX_PAIRS or npb > L.RCD_MAX_PAIRS or \
            ln != L.RCD_CANVAS_HEAD + 8 * (nr + npb):
        raise RcdError('CANVAS')
    pairs = [struct.unpack_from('<2I', data, off + L.RCD_CANVAS_HEAD + 8 * i) for i in range(nr + npb)]
    if any(o >= 0x108 or o % 4 for o, _ in pairs):
        raise RcdError('CANVAS')
    out.update(prev_h=prev_h, act=(aw, ah), canvas_rec=pairs[:nr], canvas_pb=pairs[nr:])
    if L.SEC_BINFILT in secs:
        off,ln=secs[L.SEC_BINFILT]
        if w(H['MINCORE']) < 3 or ln != 20: raise RcdError('BINFILT')
        bh,bv,kh,kv,mode=struct.unpack_from('<5I',data,off)
        if bh not in (1,3) or bv not in (1,3) or kh>=6 or kv>=6 or mode>1: raise RcdError('BINFILT')
        out['binning']=(bh,bv,kh,kv,mode)
    off, ln = secs[L.SEC_UI]
    if ln != L.RCD_UI_BYTES:
        raise RcdError('UI')
    texts = []
    for o, size in ((off, L.RCD_UI_ROW), (off + L.RCD_UI_ROW, L.RCD_UI_SUM)):
        t = data[o:o + size]
        s = t.split(b'\0')[0]
        if t[size - 1] or any(t[len(s):]) or not _text_ok(s.decode('latin1'), size):
            raise RcdError('UI')
        texts.append(s.decode())
    out['row_text'], out['summary'] = texts
    off, ln = secs[L.SEC_PACK]
    if off % 64 or ln < 16 or w(off) != 0x0052424E:
        raise RcdError('PACK')
    out['pack'] = (off, ln)
    out['standby'] = []
    if L.SEC_STANDBY in secs:
        off, ln = secs[L.SEC_STANDBY]
        ng = w(off) if ln >= 4 else 0
        if not 0 < ng <= L.MAX_SBY_GROUPS:
            raise RcdError('STANDBY')
        at = off + 4
        for _ in range(ng):
            if at + 8 > off + ln:
                raise RcdError('STANDBY')
            npid, npair = w(at) & 0xFFFF, w(at + 4)
            cond = w(at) >> 16
            if cond > 2 or not (0 < npid <= L.MAX_SBY_PIDS and 0 < npair <= L.MAX_SBY_PAIRS) or \
                    at + 8 + 4 * npid + 8 * npair > off + ln:
                raise RcdError('STANDBY')
            pids = [w(at + 8 + 4 * i) for i in range(npid)]
            pairs = _pairs_ok(data, at + 8 + 4 * npid, npair)
            if pairs is None or any(p > 0x200 or p in L.VPID_POOL for p in pids):
                raise RcdError('STANDBY')
            out['standby'].append((pids, pairs, cond))
            at += 8 + 4 * npid + 8 * npair
        if at != off + ln:
            raise RcdError('STANDBY')
    out['rate_canvas'] = []
    if L.SEC_RATECANVAS in secs:
        off, ln = secs[L.SEC_RATECANVAS]
        nl = w(off) if ln >= 4 else 0
        if not 0 < nl <= L.RCD_MAX_RCANVAS:
            raise RcdError('ENTRY')
        at = off + 4
        for _ in range(nl):
            if at + 16 > off + ln:
                raise RcdError('ENTRY')
            rank, crop, bp, npair = w(at), w(at + 4), w(at + 8), w(at + 12)
            if (rank and rank not in ranks) or crop > 1 or npair > L.RCD_MAX_PAIRS or \
                    at + 16 + 8 * npair > off + ln:
                raise RcdError('ENTRY')
            pairs = _pairs_ok(data, at + 16, npair)
            if pairs is None:
                raise RcdError('ENTRY')
            x = {'rank': rank, 'crop': crop, 'base_profile': bp, 'pairs': pairs}
            if image is not None:
                x['base_row'] = _base_row(image, bp or out['profile'])
            out['rate_canvas'].append(x)
            at += 16 + 8 * npair
        if at != off + ln:
            raise RcdError('ENTRY')
    out['overrides'] = []
    if L.SEC_VMODES in secs:
        off, ln = secs[L.SEC_VMODES]
        no = w(off) if ln >= 4 else 0xFFFFFFFF
        if no > L.RCD_MAX_OVR or ln != 4 + L.RCD_OVR_BYTES * no:
            raise RcdError('OVERRIDE')
        donors = {e['donor'] for e in out['entries']}
        for i in range(no):
            donor, kind, o, v = struct.unpack_from('<4I', data, off + 4 + L.RCD_OVR_BYTES * i)
            if donor not in donors or not override_ok(kind, o):
                raise RcdError('OVERRIDE')
            out['overrides'].append((donor, kind, o, v))
    return out


def _base_row(image, pid):
    if pid in L.VPID_POOL or pid > 0x200:
        raise RcdError('PROFILE')
    base = struct.unpack_from('<I', image, L.MAPPING + 4 * pid - 0xC0000000)[0]
    if base == 0xFFFFFFFF:
        raise RcdError('PROFILE')
    return base


def _pairs_ok(data, at, n):
    out = [struct.unpack_from('<2I', data, at + 8 * i) for i in range(n)]
    return out if all(o < 0x108 and o % 4 == 0 for o, _ in out) else None


def override_ok(kind, off):
    if kind < len(L.TABLES):
        return 4 <= off < L.TABLES[kind][3] and off % 4 == 0
    if kind == len(L.TABLES):                  # the +0x10 value
        return off == 0
    if kind == L.T_ZOOM_KIND:
        return 4 <= off < L.ZOOM[2] and off % 4 == 0
    return False


# ---- the menu: the core's FPUI template ----------------------------------------------
TOKENS = {'@R': 'row_text', '@S': 'summary', '@L': 'label'}


def ui_template(virtual=False):
    """uishare's resolution_qs() Settings part, with the three image names as
    STRBASE strings whose ids land in the row (ROW.QSID + 4i, relocated by the
    entry) -- and no QS_OPTION: the Quick Set is the core's (scheme B).  The
    data-dependent texts are tokens: @R the row text, @S the summary, @L the label.
    Returns (block bytes, info)."""
    sys.path.insert(0, str(UISHARE))
    from ui import fpui, options as O
    img = O.image()
    blk = fpui.Block()
    O.hook_fv(blk)
    name, addr, size = O.RES_CSV
    O.csv_file(blk, addr, size, ['{N},@R,Popup,,1,2'])
    a, off, n = O.resource_set('B2_5')
    s = blk.string('@S', fpui.NOT_STOCK)
    blk.op(fpui.OP_PAGE, blk.string('B2_5', fpui.NAME), off, n, 1, 0, 64, 4)
    blk.op(fpui.OP_GUARD, 0, struct.unpack('>I', O.at(img, a, 4))[0])
    blk.op(fpui.OP_ADDF, O.RES_LIST_MAX - a, 1)
    ks = sorted(O.RES_SUMMARY_K)
    blk.op(fpui.OP_SETSTR_SLOT, 0, ks[0], len(ks), s, *[O.RES_SUMMARY_K[k][0] + 32 - a for k in ks])
    # Tool settings live in their own SupManager entry. Keep stock Help
    # unchanged; rewriting it for every appended row invalidates later guards.
    zeros = blk.fragment(bytes(5))
    for k in ks:
        rec, grow = O.RES_SUMMARY_K[k]
        step = O.RES_POPUP_F.get(k + 1, 0) - O.RES_POPUP_F.get(k, 0)

        def emit(rec=rec, grow=grow, step=step, k=k):
            if grow:
                blk.op(fpui.OP_GUARD, rec + 28 - a, struct.unpack('>I', O.at(img, rec + 28, 4))[0])
                blk.op(fpui.OP_ADD32, rec + 4 - a, 5)
                blk.op(fpui.OP_ADD32, rec + 28 - a, 1)
                blk.op(fpui.OP_INSERT, rec + 36 - a, zeros, 5)
            if step:
                blk.op(fpui.OP_ADDF, O.RES_POPUP_Y - a, step)
            # NOT uishare's RES_EXCL (k == 3): it points the six frame-rate list
            # variants (B2_5_5, _excl.._excl5) all at B2_5_5, so FHD/UHD lose their
            # frame-rate greying in Settings (camera 2026-10-08).  The core keeps
            # EXCL_FrameRate right instead (the class-0x19 recompute).
        if grow or step:
            O._if_slot(blk, 0, k, emit)
    blk.op(fpui.OP_DONE)
    for i, suffix in enumerate(('QS', 'SET', 'FONT')):
        blk.op(fpui.OP_STRBASE, blk.string('@L_' + suffix, fpui.NOT_STOCK), L.ROW['QSID'] + 4 * i)
    data = blk.encode()
    strings, ops, _ = fpui.decode(data)
    for text, at in strings:
        if '@' in text and at not in (fpui.NOT_STOCK, fpui.NAME):
            raise RcdError('UI', 'a token in a stock string')
    if sum(code == fpui.OP_CSV_ADD for code, _ in ops) != 1 or ops[1][0] != fpui.OP_FILE or \
            [c for c, _ in ops].index(fpui.OP_CSV_ADD) != 2:
        raise RcdError('UI', 'the CSV row must be the first slot')
    from build_section import sites
    return data, {'sites': sites(data), 'strings': len(strings), 'ops': len(ops)}


def ui_block(tpl, row, row_addr):
    """The block ogc.c builds for one row: tokens replaced, STRBASE targets moved to
    the row (row_addr = where the row lies), the hash made again."""
    sys.path.insert(0, str(UISHARE))
    from ui import fpui
    magic, ver, total, _h, ns, nw, nf, z = struct.unpack_from('<4sIIIIIII', tpl)
    cur = 0x20
    body = bytearray()
    for _ in range(ns):
        at, n = struct.unpack_from('<II', tpl, cur)
        t = tpl[cur + 8:cur + 8 + n].decode()
        cur += (8 + n + 1 + 3) & ~3
        for tok, field in TOKENS.items():
            t = t.replace(tok, row[field])
        b = t.encode()
        if not 0 < len(b) < 64:
            raise RcdError('UI', 'string length')
        body += struct.pack('<II', at, len(b)) + b + b'\0'
        body += bytes(-len(body) % 4)
    words = list(struct.unpack_from(f'<{nw}I', tpl, cur))
    i = 0
    while i < nw:
        code, n = words[i] >> 24, words[i] & 0xFFFFFF
        if code == fpui.OP_STRBASE:
            words[i + 2] = (words[i + 2] + row_addr) & 0xFFFFFFFF
        i += 1 + n
    body += struct.pack(f'<{nw}I', *words)
    body += tpl[cur + 4 * nw:total]
    head = struct.pack('<4sIIIIIII', magic, ver, 0x20 + len(body), fnv(body), ns, nw, nf, z)
    return head + bytes(body)


# ---- the Quick Set, scheme B (QS_SHARE.md §13) ---------------------------------------------
def t_k(k):
    return 100 * k // 3


def qs_target(row, old, n, rows):
    """The bytes for one recipe record (uishare ui/qs.py's row dict, `old` its
    stock bytes): `rows` = {k: (qs, set, font)} the core's rows with a Quick
    Set state.  None: not changed.  Rows k >= n get nothing."""
    sys.path.insert(0, str(UISHARE))
    from ui import qs
    rows = {k: v for k, v in rows.items() if 2 <= k < n}
    if not rows:
        return None
    rule = row['rule']
    if rule == 'clone':
        cur = old
        for k in sorted(rows):
            ids = list(rows[k]) + [rows[k][1]]
            m = row['marker']
            cur = qs.clone_key(cur, t_k(k), row['prop'] if m is not None else -1,
                               ids[m] if m is not None else 0)
        return cur
    if rule == 'end':
        end = max(struct.unpack('>I', old[36:40])[0], t_k(n - 1))
        return old[:36] + struct.pack('>I', end) + old[40:]
    if rule in ('qs_max', 'cursor', 'footer_n8'):
        return qs.target(row, old, n, 0, [0, 0, 0, 0])
    if rule == 'footer_label':
        k = row['k']
        if k not in rows:
            return None
        ids = list(rows[k]) + [rows[k][1]]
        return qs.apply_edits(old, row['edits'], ids)
    raise RcdError('QS', rule)


def qs_max_record(n_max=8):
    """The longest record scheme B makes (every row on, N = n_max): sizes ogc.c's copy buffers."""
    sys.path.insert(0, str(UISHARE))
    from ui import qs
    img = qs.image()
    rows = {k: (0x40000000 + 3 * k, 0x40000001 + 3 * k, 0x40000002 + 3 * k) for k in range(2, n_max)}
    worst = 0
    for r in qs.recipe()['records']:
        for n in range(3, n_max + 1):
            t = qs_target(r, qs.stock(r, img), n, {k: v for k, v in rows.items() if k < n})
            if t is not None:
                worst = max(worst, len(t))
    return worst


# ---- the native list copies (the core greys rows per format) ------------------------------
RATE_CSV = ((0xC0F8E848, 257, 'B2_5_5'), (0xC0F8E94C, 257, 'B2_5_5_excl'),
            (0xC0F8EA50, 257, 'B2_5_5_excl2'), (0xC0F8EB54, 257, 'B2_5_5_excl3'),
            (0xC0F8EC58, 257, 'B2_5_5_excl4'), (0xC0F8ED5C, 257, 'B2_5_5_excl5'))
BIT_CSV = ((0xC0F8E6A8, 113, 'B2_5_2'), (0xC0F8E71C, 113, 'B2_5_2_excl'))


def bit_template():
    """Own copies of the two native lists; the consumer applies each RCD's mask.
    No page edits and no SD/SSD policy. Leaving custom formats restores the copies."""
    sys.path.insert(0, str(UISHARE))
    from ui import fpui, options as O
    blk = fpui.Block()
    O.hook_fv(blk)
    for addr, size, _ in BIT_CSV:
        blk.op(fpui.OP_FILE, addr, size, 0)
        blk.op(fpui.OP_FILE_DONE)
    return blk.encode()


def rate_template():
    """Own copies of the six frame-rate list variants, as they are: the core greys
    the stock rows a format has no entry for and gives the stock flags back."""
    sys.path.insert(0, str(UISHARE))
    from ui import fpui, options as O
    blk = fpui.Block()
    O.hook_fv(blk)
    for addr, size, _ in RATE_CSV:
        blk.op(fpui.OP_FILE, addr, size, 0)
        blk.op(fpui.OP_FILE_DONE)
    return blk.encode()
