"""The virtual frame rates' menu, built from the stock image (build time only).

res-custom's core offers K = 4 virtual frame rates (OG_MULTIFORMAT_CORE_DESIGN.md,
"虛擬格率"): 239.76, 279.72, 17.98, 8.99 fps.  The camera's setting only ever holds
the stock rate each rides on (119.88 / 23.98); the menu shows them as rows 9..12.

This generalises res-lab's camera-tested single-240 changes (build/imx410_rate_ui.py
for B2_5, build/imx410_rate_lv.py for the four LV layouts) from one extra row to K:

  b25(image)  -> (page bytes, [label offset] * K)
      B2_5 as a page copy: K empty summary Icons become IconText children (their text
      a placeholder the core replaces with each label's string id), K cursor pairs for
      List values 9..12, ListItem instances 9 -> 13, the three maxima 8 -> 12.  The copy
      may grow (the core builds it, uishare's FSPG form), so nothing is dropped.
  lv(image) / lv_record_blob(image)
      Claimed boot patches and small resident record substitutions. Each LV rate
      uses large integer text, small decimal text and FPS, with 14 states. The
      existing NBU record hook supplies the growing records without moving a set.
"""
from __future__ import annotations

import hashlib
import pathlib
import struct
import sys

HERE = pathlib.Path(__file__).resolve().parent
BUILD = HERE.parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / 'research/ui/tools/nbu_probe'))
sys.path.insert(0, str(ROOT / 'research/ui/tools'))
sys.path.insert(0, str(BUILD))
import nbu_format as N                                     # noqa: E402

BASE = 0xC0000000
# rank (fps x 100), the stock internal it rides on, that rate's export, CSV text, label
VRATES = ((23976, 7, 10, '239.76 fps', '239.76'),
          (27972, 7, 10, '279.72 fps', '279.72'),
          (1798, 1, 1, '17.98 fps', '17.98'),
          (899, 1, 1, '8.99 fps', '8.99'))
K = len(VRATES)
FIRST_ROW = 9                 # rows 9..12 (the stock nine are 0..8)

# ---- B2_5 -------------------------------------------------------------------------
SET_START, SET_END = 0xC1A5C590, 0xC1A792FB
SET_SHA256 = "6e0d023dbacad3326f24bccca3dcbae58449a5cf07074546ccfa401a77d44080"
POOL_START, POOL_SIZE = 0xC18C0474, 0x2B018
TEXT_PARENT, ICON_PARENT = 4448, 4457
TEXT_PARENT_RECORD, ICON_PARENT_RECORD = 0xC1A7638D, 0xC1A76E8A
DONOR_START, DONOR_END = 0xC1A76E05, 0xC1A76E8A          # IconText09: obj, base, text
ICONS = tuple(range(4458, 4458 + K))                     # Icon01..Icon04, borrowed
ICONTEXT10, P_240, DRAWTEXT, DRAWIMAGE = 0x14938, 0x47B4, 0x2541C, 0x253E4
LIST_ID, LIST_RECORD = 4439, 0xC1A7498B
LAST_EVENT, LAST_FOCUS = 0xC1A75020, 0xC1A7504C
KEY0 = 0x14                   # the List's local ids end at 0x13 (events and clips)
NUMBERS = {'9': 0x5B7C, '10': 0x21C0, '11': 0x266C, '12': 0x2A98, '13': 0x2DF8}
LIST_CAP = 0xC1A74B44         # the popup List's controller max (BE float)
# (record address, owner, property, body offset, stock, new): tag 0x1000E floats
CONTROLLERS = ((0xC1A7519D, 4440, 3, 28, 9.0, 9.0 + K),       # ListItem instances
               (0xC1A73D43, 4434, 0x12, 24, 8.0, 8.0 + K),    # MenuItem_Select (summary)
               (0xC1A744D5, 4438, 0x12, 24, 8.0, 8.0 + K))    # IconChange (GUI variable)


def _put(data, at, value):
    out = bytearray(data)
    struct.pack_into('>I', out, at, value)
    return bytes(out)


def _pool(image):
    return image[POOL_START - BASE:POOL_START - BASE + POOL_SIZE]


def b25(image):
    original = image[SET_START - BASE:SET_END - BASE]
    if hashlib.sha256(original).hexdigest() != SET_SHA256:
        raise ValueError('B2_5 differs from the pinned stock set')
    pool = _pool(image)
    for off, name in ((P_240, '240'), (ICONTEXT10, 'IconText10'), (DRAWTEXT, 'drawText'),
                      (DRAWIMAGE, 'drawImage'), *((v, k) for k, v in NUMBERS.items())):
        if N.string_at(pool, off) != name:
            raise ValueError(f'NBU pool mismatch: {name}')
    records = N.split(original)
    at = {SET_START + r.offset: r for r in records}
    donor = [r for r in records if DONOR_START <= SET_START + r.offset < DONOR_END]
    if [r.tag for r in donor] != [0x10003, 0x10004, 0x10005]:
        raise ValueError('summary text donor shape changed')
    # each borrowed Icon: obj, base, drawImage, clip -> obj (text parent), base, drawText, clip
    by_icon, order = {}, []
    for i, r in enumerate(records):
        if r.tag == 0x10003 and r.words(7)[3] in ICONS:
            group = records[i:i + 4]
            if [g.tag for g in group] != [0x10003, 0x10004, 0x10005, 0x1000A] or \
                    group[0].words(7) != (3, 0, 0, r.words(7)[3], ICON_PARENT, group[0].words(7)[5], 0) or \
                    group[2].body[-4:] != bytes(4):
                raise ValueError(f'icon {r.words(7)[3]} changed')
            by_icon[r.words(7)[3]] = (i, group)
            order.append(r.words(7)[3])
    if sorted(by_icon) != list(ICONS):
        raise ValueError('borrowed icons missing')
    expected_alpha = struct.pack('>5I', 2, 1, 1, 0x24F08, 3) + b'\0\0' + struct.pack('>If', 33, 1.0) + \
        b'\x01\0' + struct.pack('>If', 66, 1.0)
    replacement, label_marks = {}, {}
    for icon in ICONS:
        _, (obj_r, _, _, clip_r) = by_icon[icon]
        obj = _put(_put(obj_r.body, 16, TEXT_PARENT), 20, ICONTEXT10)
        base = _put(donor[1].body, 12, icon)
        text = _put(donor[2].body, 12, icon)
        if struct.unpack_from('>I', text, 20)[0] != 0x40000001:
            raise ValueError('drawText property mask changed')
        text = _put(text, 20, 0x40002001)              # text + explicit color + rect
        text = _put(text, 24, P_240)                   # placeholder: the core writes the label id
        text = text[:28] + b'\0' + struct.pack('>I', 0xFFFFFFFF) + text[29:]
        clip = clip_r.body
        if len(clip) != 180 or clip[-40:] != expected_alpha:
            raise ValueError(f'icon {icon} alpha is not the redundant opaque constant')
        clip = _put(clip[:-40], 4, 3)
        replacement[icon] = [N.Record(0x10003, 0, obj), N.Record(0x10004, 0, base),
                             N.Record(0x10005, 0, text), N.Record(0x1000A, 0, clip)]
    for address, old, new in ((TEXT_PARENT_RECORD, 9, 9 + K), (ICON_PARENT_RECORD, 8, 8 - K)):
        r = at[address]
        if r.tag != 0x10003 or r.words(3)[2] != old:
            raise ValueError('summary parent child count changed')
        r.body = _put(r.body, 8, new)
    for address, owner, prop, off, stock, value in CONTROLLERS:
        r = at[address]
        if r.tag != 0x1000E or r.words(6)[3:6:2] != (owner, prop) or \
                struct.unpack_from('>f', r.body, off)[0] != stock:
            raise ValueError(f'controller 0x{address:08X} changed')
        r.body = r.body[:off] + struct.pack('>f', value) + r.body[off + 4:]
    # the popup List's controller max (inside some record: patch by address later)
    # cursor pairs for values 9..12 (cloned from the v=8 pair)
    event, focus = at[LAST_EVENT], at[LAST_FOCUS]
    if event.words(9)[3:8] != (0x1C10, LIST_ID, 0x13, 3, 0x12) or \
            struct.unpack_from('>f', event.body, 32)[0] != 8.0 or \
            focus.words(10)[3:5] != (LIST_ID, 0x13) or focus.words(10)[9] != 0x5A18:
        raise ValueError('popup v=8 cursor pair changed')
    lst = at[LIST_RECORD]
    if lst.tag != 0x10003 or lst.words(4)[::3] != (16, LIST_ID):
        raise ValueError('popup List component count changed')
    lst.body = _put(lst.body, 0, 16 + K)
    pairs = []
    for k in range(K):
        v = FIRST_ROW + k
        e = _put(_put(event.body, 12, NUMBERS[str(v + 1)]), 20, KEY0 + k)
        e = e[:32] + struct.pack('>f', float(v)) + e[36:]
        f = _put(_put(focus.body, 16, KEY0 + k), 36, NUMBERS[str(v)])
        pairs += [N.Record(0x10006, 0, e), N.Record(0x10009, 0, f)]
    header = records[0]
    if header.tag != 0x10002:
        raise ValueError('missing allocation header')
    moves = {'drawImage': (62, -K), 'drawText': (61, K), 'controlValueEvent': (85, K),
             'controlFocus': (93, K)}
    seen = set()
    for i in range(struct.unpack_from('>I', header.body, 8)[0]):
        o = 12 + 8 * i
        name, count = struct.unpack_from('>II', header.body, o)
        label = N.string_at(pool, name)
        if label in moves:
            if count != moves[label][0]:
                raise ValueError(f'{label} allocation capacity changed')
            header.body = _put(header.body, o + 4, count + moves[label][1])
            seen.add(label)
    if seen != set(moves):
        raise ValueError('missing drawable allocation classes')
    out = []
    skip = set()
    for icon in ICONS:
        i, _ = by_icon[icon]
        skip.update(range(i, i + 4))
    first = {by_icon[icon][0]: icon for icon in ICONS}
    for i, r in enumerate(records):
        if i in first:
            out.extend(replacement[first[i]])
        if i not in skip:
            out.append(r)
        if SET_START + r.offset == LAST_FOCUS:
            out.extend(pairs)
    page = bytearray(N.join(out))
    # where each label's text offset sits (drawText body +24), and the List max
    marks = []
    for icon in ICONS:
        text_rec = replacement[icon][2]
        marks.append(_offset_of(out, text_rec) + N.HEADER + 24)
    cap = _offset_of_stock(records, out, LIST_CAP - SET_START)
    if page[cap:cap + 4] != struct.pack('>f', 8.0):
        raise ValueError('List max is not 8.0')
    page[cap:cap + 4] = struct.pack('>f', 8.0 + K)
    return bytes(page), marks


def segments(page, image):
    """The page as an edit script over the stock set: [(stock offset, length) | bytes],
    stock runs as long as possible (the core rebuilds the page from the NBU)."""
    stock = image[SET_START - BASE:SET_END - BASE]
    recs = N.split(page)
    st = {}
    for r in N.split(stock):
        st.setdefault(r.to_bytes(), []).append(r.offset)
    out, o = [], 0
    for r in recs:
        b = page[o:o + r.size]
        hits = st.get(b, [])
        hit = None
        if out and isinstance(out[-1], tuple) and out[-1][0] + out[-1][1] in hits:
            hit = out[-1][0] + out[-1][1]
        elif hits:
            hit = hits[0]
        if hit is None:
            if out and isinstance(out[-1], bytes):
                out[-1] += b
            else:
                out.append(b)
        elif out and isinstance(out[-1], tuple) and out[-1][0] + out[-1][1] == hit:
            out[-1] = (out[-1][0], out[-1][1] + r.size)
        else:
            out.append((hit, r.size))
        o += r.size
    if o != len(page):
        raise ValueError('page does not split into records')
    rebuilt = b''.join(stock[x[0]:x[0] + x[1]] if isinstance(x, tuple) else x for x in out)
    if rebuilt != page:
        raise ValueError('segments do not rebuild the page')
    return out


def _offset_of(out, rec):
    o = 0
    for r in out:
        if r is rec:
            return o
        o += r.size
    raise ValueError('record not placed')


def _offset_of_stock(records, out, stock_off):
    """stock byte offset -> offset in the rebuilt page (the record holding it is kept)."""
    for r in records:
        if r.offset <= stock_off < r.offset + r.size:
            return _offset_of(out, r) + (stock_off - r.offset)
    raise ValueError('offset outside the set')


# ---- the four LV layouts ------------------------------------------------------------
LV_VALUES = ('23.98', '24', '25', '29.97', '48', '50', '59.94', '100', '119.88',
             *(r[4] for r in VRATES), '15')
LV_TIMES = tuple((100 * i) // 3 for i in range(len(LV_VALUES)))
LV_LABELS = tuple(v.split('.')[0] for v in LV_VALUES) + tuple(
    '.' + v.split('.')[1] if '.' in v else ' ' for v in LV_VALUES) + ('FPS',)
LV_FPS_ID = 2 * len(LV_VALUES)
# Rounded two-pixel outer edge. Paint these black copies first, then the
# unchanged white glyphs at the center; this does not embolden the white fill.
LV_EDGE_OFFSETS = ((-2, 0), (2, 0), (0, -2), (0, 2),
                   (-1, -1), (1, -1), (-1, 1), (1, 1))
# Explicit px units, left/bottom alignment. Keep text advances separate from
# the stock bitmap widths: the native 35px font advances 14px per digit in the
# measured medium-LV 29.97 capture. Add the integer/fraction join only once.
# The large-layout advances are scaled estimates pending hardware comparison.
LV_STYLE = {
    'LARGE': dict(integer=43, small=26, digit=17, one=17, after_integer=5, fraction=28, gap=4, fps=54),
    'MEDIUM': dict(integer=35, small=25, digit=14, one=14, after_integer=4, fraction=27, gap=4, fps=52),
}


def _fnv(data):
    h = 0x811C9DC5
    for b in data:
        h = ((h ^ b) * 0x01000193) & 0xFFFFFFFF
    return h


def _lv_plan(image):
    """Small in-place claims + resident replacement records for the existing NBU hook.

    Three native text components keep the original object and bindings.
    The allocation
    header and rate clip grow through that hook, keeping every stock address and
    neighbouring record intact. No new object, bitmap, renderer or hook site.
    """
    import imx410_rate_lv as V
    import native_ui_audit as A
    pool = _pool(image)
    text_name, rect_name = (pool.find(b'\0' + n + b'\0') + 1 for n in (b'text', b'rect'))
    if min(text_name, rect_name) <= 0:
        raise ValueError('LV property names missing')
    latin_font = pool.find(b'\0Other_fontsetting\0') + 1
    if latin_font <= 0: raise ValueError('stock Latin font missing')
    patches, replacements = {}, []
    def patch_record(a, data):
        lo, hi = a & ~3, (a + len(data) + 3) & ~3
        for w in range(lo, hi, 4):
            patches.setdefault(w, bytearray(image[w - BASE:w - BASE + 4]))
        for i, b in enumerate(data):
            patches[(a + i) & ~3][(a + i) & 3] = b
    def replace(a, old, records, marks=()):
        # Draw/clip slots also restore older in-place text versions on warm boot.
        # The large allocation header is only guarded, not copied into the journal.
        if struct.unpack_from('>I', old)[0] != 0x10002:
            patch_record(a, old)
        replacements.append(dict(address=a, stock=old, data=N.join(records),
                                 records=len(records), marks=list(marks)))
    for spec in V.SETS:
        raw = image[spec['start'] - BASE:spec['end'] - BASE]
        if hashlib.sha256(raw).hexdigest() != spec['sha']:
            raise ValueError('LV set differs: ' + spec['name'])
        rs = N.split(raw)
        by = {spec['start'] + r.offset: r for r in rs}
        draw, clip, group = (by[spec[k]] for k in ('draw', 'clip', 'group'))
        decoded = A.parse_clip(A.Record(0, clip.to_bytes()), lambda p: N.string_at(pool, p))
        if decoded['owner_id'] != spec['owner'] or len(decoded['properties']) != spec['properties'] or \
                [(p['name'], p['component_ref']) for p in decoded['properties']] != \
                [('image', 3)] + [('rect', 3)] * (spec['properties'] - 1):
            raise ValueError('LV FrameRate drawable changed: ' + spec['name'])
        g = N.decode_image_array(group, pool)
        if g['group'] != 'FrameRate' or g['entries'][0]['b'] != 300:
            raise ValueError('LV FrameRate group changed')
        obj = next(r for r in rs if r.tag == 0x10003 and r.words(4)[3] == spec['owner'])
        used_ids = {r.words(5)[4] for r in rs if r.tag in (0x10004, 0x10005, 0x10009)
                    and r.words(4)[3] == spec['owner']}
        if obj.words(1)[0] not in (4, 6) or used_ids & set(range(8,34)):
            raise ValueError('LV component identities changed')
        # Preserve the stock object and events. The resident record hook must
        # parse all three drawables even when the reader has registered resources.
        patch_record(spec['start'] + obj.offset, N.Record(obj.tag, 0, _put(obj.body, 0, obj.words(1)[0] + 26)).to_bytes())
        style = LV_STYLE[spec['name'].rsplit('_', 1)[-1]]
        int_widths = [sum(style['one'] if ch == '1' else style['digit']
                          for ch in v.split('.')[0]) + style['after_integer']
                      for v in LV_VALUES]
        xcurve = next((p['keys'] for p in decoded['properties'] if p['name'] == 'rect'
                       and p['dimension'] == 0), None)
        stock_x = [k['value'] for k in xcurve] if xcurve else [0.] * 10
        origin_x = stock_x[:9] + [stock_x[8], stock_x[8], stock_x[0], stock_x[0], stock_x[9]]
        frac_x = [x + w for x, w in zip(origin_x, int_widths)]
        fps_x = [x + w + (style['fraction'] if '.' in v else 0) + style['gap']
                 for x, w, v in zip(origin_x, int_widths, LV_VALUES)]
        # Use each drawable's own rect, with one common bottom edge. The parent
        # origin, visibility, FrameRate group and app-variable binding stay stock.
        # Eight black copies extend the edge outwards by two pixels; white
        # text retains its font, position and size and is parsed last.
        draw_specs = []
        parts = ((0, 3, 0, style['integer'], max(int_widths), origin_x),
                 (1, 32, len(LV_VALUES), style['small'], style['fraction'], frac_x),
                 (2, 33, LV_FPS_ID, style['small'], style['fps'], fps_x))
        for part, white, label, size, width, positions in parts:
            for k, (dx, dy) in enumerate(LV_EDGE_OFFSETS):
                draw_specs.append((part, 8+8*part+k, label, size, width, positions, dx, dy, 0x000000FF))
        for part, white, label, size, width, positions in parts:
            draw_specs.append((part, white, label, size, width, positions, 0, 0, 0xFFFFFFFF))
        draws, dmarks = [], []
        for part, component, label, size, width, positions, dx, dy, colour in draw_specs:
            body = struct.pack('>6I', DRAWTEXT, 32, 0xFFFFFFFF, spec['owner'], component,
                               0x4000203F)
            body += struct.pack('>I', P_240) + b'\0' + struct.pack('>6I', latin_font, size, 1, 1, 3, colour)
            body += struct.pack('>4f', positions[0]+dx, dy, width, spec['height'])
            dmarks.append((sum(r.size for r in draws) + N.HEADER + 24, label))
            draws.append(N.Record(0x10005, 0, body))
        replace(spec['draw'], draw.to_bytes(), draws, dmarks)
        props, cmarks = [], []
        for part, component, label, size, width, positions, dx, dy, colour in draw_specs:
            if part < 2:
                start = N.HEADER + 20 + sum(map(len, props)) + 20
                for k in range(len(LV_VALUES)):
                    cmarks.append((start + 10*k + 6, part*len(LV_VALUES)+k))
                props.append(V._property(2, component, text_name, 0, zip(LV_TIMES, [P_240]*len(LV_VALUES))))
            props.append(V._property(1, component, rect_name, 0, zip(LV_TIMES, [x+dx for x in positions])))
        body = struct.pack('>5I', 0x24974, len(props), 0xFFFFFFFF, spec['owner'], 4) + b''.join(props)
        replace(spec['clip'], clip.to_bytes(), [N.Record(clip.tag, 0, body)], cmarks)
        replace(spec['group'], group.to_bytes(), [N.Record(group.tag, 0, _put(group.body, 28, LV_TIMES[-1]))])
        header = A.parse_header(A.Record(0, rs[0].to_bytes()), lambda p: N.string_at(pool, p))
        h = bytearray(rs[0].body)
        nc = struct.unpack_from('>I', h, 8)[0]
        for i in range(nc):
            o = 12 + 8 * i
            name, count = struct.unpack_from('>II', h, o)
            if name in (DRAWIMAGE, DRAWTEXT):
                want = spec['images'] if name == DRAWIMAGE else spec['texts']
                if count != want:
                    raise ValueError('LV drawable counts changed')
                patch_record(spec['start'] + N.HEADER + o + 4, bytes(h[o + 4:o + 8]))
                struct.pack_into('>I', h, o + 4, count + (-1 if name == DRAWIMAGE else 27))
        c = 12 + 8 * nc
        ng = struct.unpack_from('>I', h, c)[0]
        c += 4 + ng * 12
        # These vectors sum arena capacity; their order is not clip order.
        # Retain the stock budgets and add the four new rate curves explicitly.
        pcounts = list(header['clip_property_counts']) + [len(props)]
        kcounts = [len(LV_VALUES) if n == 10 else n for n in header['property_key_counts']]
        if sum(n == 10 for n in header['property_key_counts']) != spec['key_budgets']:
            raise ValueError('LV key budget inventory changed')
        old_keys = c + 4 + 4 * len(header['clip_property_counts']) + 4
        for i, n in enumerate(header['property_key_counts']):
            if n == 10:
                off = old_keys + 4 * i
                patch_record(spec['start'] + N.HEADER + off, rs[0].body[off:off + 4])
        kcounts += [len(LV_VALUES)] * len(props)
        newh = bytes(h[:c]) + struct.pack('>I', len(pcounts)) + struct.pack(f'>{len(pcounts)}I', *pcounts)
        newh += struct.pack('>I', len(kcounts)) + struct.pack(f'>{len(kcounts)}I', *kcounts)
        newh += struct.pack('>I', len(header['trailing_budget'])) + struct.pack(
            f">{len(header['trailing_budget'])}I", *header['trailing_budget'])
        replace(spec['start'], rs[0].to_bytes(), [N.Record(rs[0].tag, 0, newh)])
        # The resident group supplies the endpoint. Keep its source bytes stock
        # so the runtime hash guard also recognizes warm-boot restorations.
        if max(x + style['fps'] for x in fps_x) > 240:
            raise ValueError('LV styled rate overlaps the next status field')
    runs = []
    for a in sorted(patches):
        old, new = image[a - BASE:a - BASE + 4], bytes(patches[a])
        if runs and runs[-1][0] + len(runs[-1][1]) == a:
            s, st, cur = runs[-1]; runs[-1] = (s, st + old, cur + new)
        else:
            runs.append((a, old, new))
    return runs, sorted(replacements, key=lambda r: r['address'])


def lv(image):
    """Boot-time claimed patches; labels are now in resident record substitutions."""
    runs, _ = _lv_plan(image)
    return runs, []


def lv_records(image):
    return _lv_plan(image)[1]


def lv_record_blob(image):
    rows = lv_records(image)
    if len(rows) != 16 or len(LV_LABELS) != 29:
        raise ValueError('LV text runtime inventory changed')
    out = bytearray(struct.pack('<2I', len(rows), 0))
    for r in rows:
        data, marks = r['data'], r['marks']
        if len(data) > 0x2800 or r['records'] > 27 or len(marks) > 256:
            raise ValueError('LV resident record exceeds runtime bounds')
        out += struct.pack('<6I', r['address'], len(r['stock']), _fnv(r['stock']),
                           len(data), r['records'], len(marks))
        out += data + bytes(-len(data) % 4)
        for off, label in marks:
            out += struct.pack('<2I', off, label)
    if len(out) > 0x16000:
        raise ValueError('LV resident table exceeds runtime bounds')
    struct.pack_into('<I', out, 4, len(out))
    return bytes(out)
