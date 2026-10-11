#!/usr/bin/env python3
"""Sensor Lab's tenth Settings summary label, as bounded NBU data patches.

The popup CSV and enum converter do not create a tenth collapsed label.  The
stock B2_5 has nine IconText children and eight unused, empty Icon children.
Borrow its first empty Icon for the new text child, retaining that object's
ID and RGB lock animation.  No resource index, loader or interpreter hook is
changed.  Build-time input is the original Ver.5.02 image, not live memory.

An explicit opaque-white initial color replaces the donor's redundant alpha
animation (both keys were 1.0).  This leaves the set three bytes SHORTER.  The
terminator is followed by three zero bytes; the next set keeps its address.
Allocation capacities stay at their stock upper bounds, except the drawable
class counts, which transfer one instance from drawImage to drawText.

This proves serialized structure, not rendering or object ordering on camera.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import struct
import sys
from collections.abc import Mapping
from functools import lru_cache

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "research/ui/tools/nbu_probe"))
import nbu_format as N

BASE = 0xC0000000
SET_START, SET_END = 0xC1A5C590, 0xC1A792FB
SET_SHA256 = "6e0d023dbacad3326f24bccca3dcbae58449a5cf07074546ccfa401a77d44080"
POOL_START, POOL_SIZE = 0xC18C0474, 0x2B018
TEXT_PARENT, ICON_PARENT, BORROWED_ID = 4448, 4457, 4458
TEXT_PARENT_RECORD, ICON_PARENT_RECORD = 0xC1A7638D, 0xC1A76E8A
DONOR_START, DONOR_END = 0xC1A76E05, 0xC1A76E8A
BORROW_START, BORROW_END = 0xC1A76EFA, 0xC1A7701A
# Two controller floats (tag 0x1000E, BE) that r2 missed, found 2026-09-30 by
# scanning every stock list in all 221 NBU sets:
#   popup ListItem instance count = max(8, rows)  (B2_5_5 9->9, B6_2_1 11->11,
#     B3_5_5 12->12); a tenth CSV row has no instance to draw or put the cursor on.
#   MenuItem_Select prop 0x12 = max(7, IconText children - 1)  (8->7, 9->8,
#     11->10, 5->4); ten summary children need 9.0 or state 9 is clamped.
# (record address, owner id, property, body offset, stock, new)
CONTROLLERS = ((0xC1A7519D, 4440, 3, 28, 9.0, 10.0),    # ListItem: popup rows
               (0xC1A73D43, 4434, 0x12, 24, 8.0, 9.0),  # MenuItem_Select: summary
               (0xC1A744D5, 4438, 0x12, 24, 8.0, 9.0))  # IconChange: GUI var clamp
# IconChange is the third frame-rate maximum (with List C1A74B44 and
# MenuItem_Select).  Camera 2026-10-01 (r9 + RAM): the stock notifier writes
# row 9 back into MV_FrameRate, IconChange clamped it to 8, and that write
# re-entered the setter and cleared the row-nine flag.  9.0 in RAM fixed it.
# The popup List (4439) moves its cursor highlight through one
# controlValueEvent(value == v) + controlFocus("v") pair per row, stock v=0..8.
# Without a pair for 9.0 the cursor reaches row ten invisibly (camera, r4).
# Clone the v=8 pair as v=9 ("10" -> focus "9"), under a fresh key.  Space
# comes from the last empty summary Icon (Icon08), whose drawImage and
# animationClip capacities move to the two new event classes.
LIST_ID, LIST_RECORD = 4439, 0xC1A7498B
# False = popup row ten only (cursor pair + ListItem), no collapsed-summary
# label: the 240-freeze bisection needs the two halves separable.
WITH_SUMMARY = True
LAST_EVENT, LAST_FOCUS = 0xC1A75020, 0xC1A7504C
PAIR_KEY, EVENT_NAME, FOCUS_NAME = 0x14, 0x21C0, 0x5B7C   # pool "10", "9"
DROP_ID, DROP_START, DROP_END = 4465, 0xC1A776F2, 0xC1A77816


def _put(data: bytes, offset: int, value: int) -> bytes:
    out = bytearray(data)
    struct.pack_into(">I", out, offset, value)
    return bytes(out)


def rebuild(image: bytes) -> bytes:
    """Return the original-sized B2_5 slot, with exactly one new summary label."""
    original = image[SET_START - BASE:SET_END - BASE]
    if hashlib.sha256(original).hexdigest() != SET_SHA256:
        raise ValueError("B2_5 differs from the pinned stock set")
    pool = image[POOL_START - BASE:POOL_START - BASE + POOL_SIZE]
    for offset, name in ((0x47B4, "240"), (0x14938, "IconText10"),
                         (0x2541C, "drawText"), (0x253E4, "drawImage")):
        if N.string_at(pool, offset) != name:
            raise ValueError(f"NBU pool mismatch: {name}")
    records = N.split(original)
    by_address = {SET_START + r.offset: r for r in records}
    # Same component count and ID as the empty-image donor, but its new parent
    # is the text toggler. The parser appends it after the nine existing labels.
    donor = [r for r in records if DONOR_START <= SET_START+r.offset < DONOR_END]
    source = [r for r in records if BORROW_START <= SET_START+r.offset < BORROW_END]
    if [r.tag for r in donor] != [0x10003, 0x10004, 0x10005] or \
            [r.tag for r in source] != [0x10003, 0x10004, 0x10005, 0x1000A]:
        raise ValueError("summary/empty-icon donor shape changed")
    if source[0].words(7) != (3, 0, 0, BORROWED_ID, ICON_PARENT, 0x145D0, 0):
        raise ValueError("empty icon identity changed")
    if source[2].body[-4:] != bytes(4):
        raise ValueError("borrowed icon is no longer empty")
    obj = _put(source[0].body, 16, TEXT_PARENT)
    obj = _put(obj, 20, 0x14938)  # existing name pool: IconText10
    base = _put(donor[1].body, 12, BORROWED_ID)
    text = _put(donor[2].body, 12, BORROWED_ID)
    if struct.unpack_from(">I", text, 20)[0] != 0x40000001:
        raise ValueError("drawText property mask changed")
    text = _put(text, 20, 0x40002001)  # text + explicit color + rect
    text = _put(text, 24, 0x47B4)    # literal '240', not a localization ID
    text = text[:28] + b"\0" + struct.pack(">I", 0xFFFFFFFF) + text[29:]
    # animationClip body has a 20-byte prologue and four 40-byte properties.
    clip = source[3].body
    expected_alpha = struct.pack(">5I", 2, 1, 1, 0x24F08, 3) + \
        b"\0\0" + struct.pack(">If", 33, 1.0) + \
        b"\x01\0" + struct.pack(">If", 66, 1.0)
    if len(clip) != 180 or clip[-40:] != expected_alpha:
        raise ValueError("donor alpha is not the redundant opaque constant")
    clip = _put(clip[:-40], 4, 3)
    replacement = [N.Record(tag, 0, body) for tag, body in
                   ((0x10003, obj), (0x10004, base), (0x10005, text),
                    (0x1000A, clip))]

    summary = int(WITH_SUMMARY)
    for address, old_count, count in ((TEXT_PARENT_RECORD, 9, 9 + summary),
                                       (ICON_PARENT_RECORD, 8, 7 - summary)):
        r = by_address[address]
        if r.tag != 0x10003 or r.words(3)[2] != old_count:
            raise ValueError("summary parent child count changed")
        r.body = _put(r.body, 8, count)
    for address, owner, prop, at, stock, value in CONTROLLERS:
        if owner == 4434 and not summary:
            continue
        r = by_address[address]
        if r.tag != 0x1000E or r.words(6)[3:6:2] != (owner, prop) or \
                struct.unpack_from(">f", r.body, at)[0] != stock:
            raise ValueError(f"controller {address:#x} changed")
        r.body = r.body[:at] + struct.pack(">f", value) + r.body[at + 4:]
    # ---- tenth popup row: cursor event pair ------------------------------
    event, focus = by_address[LAST_EVENT], by_address[LAST_FOCUS]
    if event.words(9)[3:8] != (0x1C10, LIST_ID, 0x13, 3, 0x12) or \
            struct.unpack_from(">f", event.body, 32)[0] != 8.0 or \
            focus.words(10)[3:5] != (LIST_ID, 0x13) or focus.words(10)[9] != 0x5A18:
        raise ValueError("popup v=8 cursor pair changed")
    if N.string_at(pool, EVENT_NAME) != "10" or N.string_at(pool, FOCUS_NAME) != "9":
        raise ValueError("NBU pool mismatch: popup row names")
    list_obj = by_address[LIST_RECORD]
    if list_obj.tag != 0x10003 or list_obj.words(4)[::3] != (16, LIST_ID):
        raise ValueError("popup List component count changed")
    list_obj.body = _put(list_obj.body, 0, 17)
    new_event = _put(_put(event.body, 12, EVENT_NAME), 20, PAIR_KEY)
    new_event = new_event[:32] + struct.pack(">f", 9.0) + new_event[36:]
    new_focus = _put(_put(focus.body, 16, PAIR_KEY), 36, FOCUS_NAME)
    drop = [r for r in records if DROP_START <= SET_START+r.offset < DROP_END]
    if [r.tag for r in drop] != [0x10003, 0x10004, 0x10005, 0x1000A] or \
            drop[0].words(7)[3:5] != (DROP_ID, ICON_PARENT) or drop[2].body[-4:] != bytes(4):
        raise ValueError("last empty summary icon changed")
    freed = sum(r.size for r in drop) - (N.HEADER*2 + len(new_event) + len(new_focus))
    if freed < 0:
        raise ValueError("no room for the tenth popup cursor pair")
    new_focus += bytes(freed)   # stock interpreter epilogue skips the zero tail
    pair = [N.Record(0x10006, 0, new_event), N.Record(0x10009, 0, new_focus)]
    header = records[0]
    if header.tag != 0x10002:
        raise ValueError("missing allocation header")
    classes = struct.unpack_from(">I", header.body, 8)[0]
    seen = set()
    for i in range(classes):
        at = 12 + i * 8
        name, count = struct.unpack_from(">II", header.body, at)
        label = N.string_at(pool, name)
        moves = {"drawImage": (62, -1 - summary), "drawText": (61, summary),
                 "animationClip": (214, -1), "controlValueEvent": (85, 1),
                 "controlFocus": (93, 1)}
        if label in moves and moves[label][1]:
            expected, delta = moves[label]
            if count != expected:
                raise ValueError(f"{label} allocation capacity changed")
            header.body = _put(header.body, at + 4, count + delta)
            seen.add(name)
    if len(seen) != 4 + summary:
        raise ValueError("missing drawable allocation classes")
    out = []
    for r in records:
        address = SET_START + r.offset
        borrowed = summary and BORROW_START <= address < BORROW_END
        if address == BORROW_START and summary:
            out.extend(replacement)
        if not (borrowed or DROP_START <= address < DROP_END):
            out.append(r)
        if address == LAST_FOCUS:
            out.extend(pair)
    rebuilt = N.join(out)
    if len(rebuilt) != len(original) - 3 * summary:
        raise ValueError("summary patch no longer fits its original set")
    return rebuilt + bytes(3 * summary)


def popup_cursor_pairs(rows, pool) -> dict:
    """{List value: focused instance name} from List 4439's event/focus records."""
    events, focus, owner = {}, {}, None
    for r in rows:
        if r.tag == 0x10003:
            owner = r.words(7)[3]
            continue
        if owner != LIST_ID or r.tag not in (0x10006, 0x10009) or len(r.body) < 32:
            continue
        name = N.string_at(pool, r.words(1)[0])
        if name == 'controlValueEvent' and r.words(5)[4] == LIST_ID:
            kind = r.words(7)[6]
            if kind in (1, 3):
                value = 0.0 if kind == 1 else struct.unpack_from('>f', r.body, 32)[0]
                events[r.words(6)[5]] = value
        elif name == 'controlFocus' and r.words(4)[3] == LIST_ID:
            focus[r.words(5)[4]] = N.string_at(pool, r.words(10)[9])
    return {int(v): focus[k] for k, v in events.items() if k in focus}


def patches(image: bytes) -> list[tuple[int, int, str]]:
    """Return changed aligned words; shared stage2 journals every word."""
    rebuilt = rebuild(image)
    lo, hi = SET_START & ~3, (SET_END + 3) & ~3
    old = image[lo - BASE:hi - BASE]
    new = bytearray(old)
    new[SET_START-lo:SET_END-lo] = rebuilt
    return [(lo + at, struct.unpack_from("<I", new, at)[0],
             "240 fps Settings collapsed summary")
            for at in range(0, len(new), 4) if old[at:at+4] != new[at:at+4]]


@lru_cache(maxsize=1)
def _native_stock_services():
    """The stock stream defines the fixed construction-call allow-list."""
    import nbu_probe as P
    stock = P.load_firmware(ROOT / 'out/seg0_c0000000.bin')
    baseline = P.NbuProbe(stock)
    baseline.install_arena()
    baseline.map_set('B2_5')
    return tuple(sorted(baseline.discovered))


def _verify_summary_selector(probe, children):
    """Execute stock toggleVisible setter and its real visibility loop.

    Object lookup/count/enumeration and the final visibility write are bounded
    stubs for the parsed NBU children. The index clamp and iteration execute
    original instructions, including the stock range derived from child count.
    """
    from unicorn.arm_const import UC_ARM_REG_S0
    state, component, owner = probe.RAM+0x70000, probe.RAM+0x70100, probe.RAM+0x70200
    probe.write(state, bytes(0x40))
    ids = {probe.RAM+0x71000+i*0x100: oid for i, oid in enumerate(children)}
    handles = list(ids)
    visible = {}
    def point_state(p, args):
        p.write_words(args[1], state)
        return 0
    def point_owner(p, args):
        p.write_words(args[1], owner)
        return 0
    def count(p, args):
        p.write_words(args[1], len(handles))
        return 0
    def child(p, args):
        if args[0] != owner or not 0 <= args[1] < len(handles):
            raise ValueError('native toggleVisible enumerated outside parsed children')
        p.write_words(args[2], handles[args[1]])
        return 0
    def show(p, args):
        if args[0] not in ids or args[1] not in (0, 1):
            raise ValueError('invalid native child visibility request')
        visible[ids[args[0]]] = args[1]
        return 0
    probe.stub(0xC05D7148, 'toggleVisible component state', handler=point_state)
    probe.stub(0xC05D70E8, 'toggleVisible owner', handler=point_owner)
    probe.stub(0xC0600EA8, 'toggleVisible owner object', ret=owner)
    probe.stub(0xC05D1ED0, 'parsed child count', handler=count)
    probe.stub(0xC05D1EE8, 'parsed child at index', handler=child)
    probe.stub(0xC05DAEC8, 'owner active', ret=0)
    probe.stub(0xC05D02C8, 'set child visibility', handler=show)
    probe.allow(0xC05FB680, 0xC05FB6F8, 'stock toggleVisible select-value setter')
    probe.allow(0xC05FB548, 0xC05FB5B8, 'stock toggleVisible child visibility loop')
    probe.uc.reg_write(UC_ARM_REG_S0, struct.unpack('<I', struct.pack('<f', 9.0))[0])
    if probe._call(0xC05FB680, component) != 0:
        raise ValueError('native summary select-value setter failed')
    if probe.words(state+0x2C)[0] != 9:
        raise ValueError('native summary index was clamped below the tenth child')
    if probe._call(0xC05FB548, component) != 0:
        raise ValueError('native summary visibility update failed')
    if visible != {oid: int(oid == BORROWED_ID) for oid in children}:
        raise ValueError('native summary did not select only the 240 text child')
    return BORROWED_ID


def native_parse(image: bytes):
    """Run the original NBU interpreter over the installed B2_5, record by record."""
    import nbu_probe as P
    if len(image) < P.SEG0_SIZE:
        raise ValueError('native parsing requires the complete seg0 memory')
    rows = N.split(image[SET_START-BASE:SET_END-BASE])
    probe = P.NbuProbe(image[:P.SEG0_SIZE])
    probe.install_arena()
    probe.allow(*probe.OBJECT_FACTORY, 'stock object factory')
    for address in _native_stock_services():
        probe.stub(address, 'stock UI construction service')
    probe.open_set('B2_5')
    for record in rows:
        trace = probe.record()
        if (trace.token, trace.cursor_in, trace.consumed) != \
                (record.tag, record.offset, record.size) or probe.error_flag():
            raise ValueError('native parser disagrees with installed NBU records')
    if probe.traces[-1].result != 1 or probe.survey or probe.discovered:
        raise ValueError('native parse did not terminate under the fixed allow-list')
    return probe


def verify_installed(image_or_words, *, base_image: bytes | None = None,
                     native: bool = False) -> dict:
    """Verify the actual installed B2_5, including other product data edits.

    Accept either full firmware memory bytes or {address: word}/plan tuples
    applied to an explicitly provided base_image.  No whole-set stock hash is
    required here: that pin protects authoring in rebuild(), while this checks
    the installed structure.  native=True executes the original interpreter
    over these exact bytes, with stock UI construction services stubbed and
    no implicit acceptance of additional calls.  It does not render the GUI.
    """
    if isinstance(image_or_words, (bytes, bytearray)):
        image = bytes(image_or_words)
    else:
        if base_image is None:
            raise ValueError('word verification requires base_image')
        image = bytearray(base_image)
        rows = image_or_words.items() if isinstance(image_or_words, Mapping) else image_or_words
        for row in rows:
            address, value = row[:2]
            if BASE <= address <= BASE + len(image)-4:
                struct.pack_into('<I', image, address-BASE, value)
        image = bytes(image)
    if len(image) < SET_END-BASE:
        raise ValueError('installed image does not contain B2_5')
    pool = image[POOL_START-BASE:POOL_START-BASE+POOL_SIZE]
    rows = N.split(image[SET_START-BASE:SET_END-BASE])
    objs = {r.words(7)[3]: r for r in rows if r.tag == 0x10003}
    children = [r.words(7)[3] for r in rows if r.tag == 0x10003
                and r.words(7)[4] == TEXT_PARENT]
    if children != list(range(4449, 4457)) + [29946, BORROWED_ID] or \
            objs[TEXT_PARENT].words(7)[2] != 10:
        raise ValueError('installed Settings summary lacks the tenth child')
    if objs[ICON_PARENT].words(7)[2] != 6 or DROP_ID in objs:
        raise ValueError('installed empty-icon parent count is inconsistent')
    if popup_cursor_pairs(rows, pool) != {v: str(v) for v in range(10)}:
        raise ValueError('installed popup lacks the tenth cursor pair')
    texts = [r for r in rows if r.tag == 0x10005 and r.words(4)[3] == BORROWED_ID]
    if len(texts) != 1:
        raise ValueError('installed 240 text component missing or duplicated')
    text = texts[0].body
    if len(text) != 49 or struct.unpack_from('>I', text, 20)[0] != 0x40002001 or \
            N.string_at(pool, struct.unpack_from('>I', text, 24)[0]) != '240' or text[28] != 0:
        raise ValueError('installed 240 label is not literal native text')
    if struct.unpack_from('>I', text, 29)[0] != 0xFFFFFFFF:
        raise ValueError('installed 240 label has lost its opaque initial color')
    end = sum(r.size for r in rows)
    if end != SET_END-SET_START-3 or image[SET_START-BASE+end:SET_END-BASE] != bytes(3):
        raise ValueError('installed B2_5 no longer fits the original slot')
    result = {'summary_children': children, 'literal_text': '240',
              'record_count': len(rows), 'bytes_parsed': end,
              'native_interpreter_executed': False, 'gui_rendered': False}
    if native:
        probe = native_parse(image)
        result['native_interpreter_executed'] = True
        result['native_selected_summary_child'] = _verify_summary_selector(probe, children)
    return result
