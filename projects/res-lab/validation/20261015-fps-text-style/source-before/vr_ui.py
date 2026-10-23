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
  lv(image)   -> [(address, stock bytes, new bytes)], [label key address] * (4 sets x K)
      The LV FrameRate drawable becomes text with 14 keys (9 stock rates, the K virtual
      ones, the hidden 15 fps last), in place, within each set's original slot.
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
LV_STOCK_LABELS = (0x473C, 0x47A8, 0x4894, 0x4ACC, 0x53BC, 0x54CC, 0x5614, 0x21D4, 0x29EC)
P_15 = 0x3400
LV_TIMES = tuple((100 * i) // 3 for i in range(9 + K + 1))   # 0, 33, ... 433


def lv(image):
    import imx410_rate_lv as V
    import native_ui_audit as A
    pool = _pool(image)
    text_name = pool.find(b'\0text\0') + 1
    rect_name = pool.find(b'\0rect\0') + 1
    labels = list(LV_STOCK_LABELS) + [P_240] * K + [P_15]
    runs, marks = [], []
    for spec in V.SETS:
        raw = image[spec['start'] - BASE:spec['end'] - BASE]
        if hashlib.sha256(raw).hexdigest() != spec['sha']:
            raise ValueError('LV set differs: ' + spec['name'])
        records = N.split(raw)
        by = {spec['start'] + r.offset: r for r in records}
        draw, clip, group = by[spec['draw']], by[spec['clip']], by[spec['group']]
        old_clip = A.parse_clip(A.Record(0, clip.to_bytes()), lambda p: N.string_at(pool, p))
        if old_clip['owner_id'] != spec['owner'] or len(old_clip['properties']) != spec['properties']:
            raise ValueError('LV FrameRate drawable changed: ' + spec['name'])
        g = N.decode_image_array(group, pool)
        if g['group'] != 'FrameRate' or g['entries'][0]['b'] != 300:
            raise ValueError('LV FrameRate group changed')
        font = by[spec['font_donor']]
        pair_size = draw.size + clip.size
        draw.body = struct.pack('>6I', DRAWTEXT, 32, 0xFFFFFFFF, spec['owner'], 3, 0x40002015) + \
            struct.pack('>I', labels[0]) + b'\0' + font.body[24:28] + struct.pack('>I', 0) + \
            struct.pack('>I4f', 0xFFFFFFFF, 0, 0, spec['width'], spec['height'])
        props = [V._property(2, 3, text_name, 0, zip(LV_TIMES, labels))]
        props.append(V._property(1, 3, rect_name, 2, [(0, float(spec['width']))]))
        if spec['properties'] == 3:
            props.append(V._property(1, 3, rect_name, 0, [(0, 0.0)]))
        clip.body = struct.pack('>5I', 0x24974, spec['properties'], 0xFFFFFFFF, spec['owner'], 4) + \
            b''.join(props)
        padding = pair_size - draw.size - clip.size
        if padding < 0:
            raise ValueError('LV pair no longer fits: ' + spec['name'])
        clip.body += bytes(padding)
        group.body = _put(group.body, 28, LV_TIMES[-1])
        # key capacities: every 10 -> 14 (the interpreter only budgets the arena)
        h = records[0]
        body = bytearray(h.body)
        n = struct.unpack_from('>I', body, 8)[0]
        for i in range(n):
            o = 12 + 8 * i
            name, count = struct.unpack_from('>II', body, o)
            if name in (DRAWIMAGE, DRAWTEXT):
                want = spec['images'] if name == DRAWIMAGE else spec['texts']
                if count != want:
                    raise ValueError('LV drawable counts changed')
                struct.pack_into('>I', body, o + 4, count + (-1 if name == DRAWIMAGE else 1))
        c = 12 + 8 * n
        c += 4 + struct.unpack_from('>I', body, c)[0] * 12
        c += 4 + struct.unpack_from('>I', body, c)[0] * 4
        keys = struct.unpack_from('>I', body, c)[0]
        c += 4
        grown = 0
        for i in range(keys):
            if struct.unpack_from('>I', body, c + 4 * i)[0] == 10:
                struct.pack_into('>I', body, c + 4 * i, 9 + K + 1)
                grown += 1
        if grown != spec['key_budgets']:
            raise ValueError('LV key-capacity inventory changed')
        h.body = bytes(body)
        new = N.join(records)
        if len(new) != len(raw):
            raise ValueError('LV set size changed')
        # the K virtual keys' values: property 0 (text), keys 9..12 (each key: 2 + 4 + 4 bytes)
        clip_off = _offset_of(records, clip) + N.HEADER       # where the clip landed (draw resized)
        p0 = clip_off + 20 + 20                              # clip prologue, then property 0 head
        for k in range(K):
            marks.append(spec['start'] + p0 + 10 * (9 + k) + 6)
        lo, hi = spec['start'] & ~3, (spec['end'] + 3) & ~3
        old = image[lo - BASE:hi - BASE]
        cur = bytearray(old)
        cur[spec['start'] - lo:spec['end'] - lo] = new
        i = 0
        while i < len(cur):
            if cur[i:i + 4] == old[i:i + 4]:
                i += 4
                continue
            j = i
            while j < len(cur) and cur[j:j + 4] != old[j:j + 4]:
                j += 4
            runs.append((lo + i, bytes(old[i:j]), bytes(cur[i:j])))
            i = j
    for m in marks:          # each mark holds the placeholder "240" offset (BE) now
        a = m
        found = next((n for (s, _, n) in runs if s <= a < s + len(n)), None)
        if found is None:
            raise ValueError(f'LV label mark 0x{a:08X} is not in a changed run')
    return runs, marks
