#!/usr/bin/env python3
"""Native text for the dedicated CINE frame-rate labels, including 240/15.

Rebuild only the four stock LV resource sets, within their original slots.
No new objects, strings, XCI resources or interpreter hooks.  The dedicated
FrameRate drawable changes from image to text; its original owner/component,
binding and animation property count remain.  The text curve has eleven
keys: the nine visible stock rates, then 240, then the original hidden 15.

Header key capacities of ten become eleven conservatively.  Width/offset
curves keep their property slots but use a constant full-width text box, and reserve the saved bytes as declared clip-tail padding. Every following
record keeps its original address; adjacent sets and index entries never move.
"""
from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache
import hashlib
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'research/ui/tools/nbu_probe'))
sys.path.insert(0, str(ROOT / 'research/ui/tools'))
import nbu_format as N
import native_ui_audit as A

BASE, POOL_START, POOL_SIZE = 0xC0000000, 0xC18C0474, 0x2B018
LABELS = ('23.98', '24', '25', '29.97', '48', '50', '59.94', '100', '119.88', '240', '15')
LABEL_OFFSETS = (0x473C, 0x47A8, 0x4894, 0x4ACC, 0x53BC, 0x54CC, 0x5614,
                 0x21D4, 0x29EC, 0x47B4, 0x3400)
TIMES = (0, 33, 66, 100, 133, 166, 200, 233, 266, 300, 333)
SETS = (
    dict(name='LV_CINE_LARGE', start=0xC1E0A87E, end=0xC1E59DAA,
         sha='512397247faa384a52085aa34eb99ba00f9b92d5753a188e876f792a31f65be2',
         owner=7356, draw=0xC1E40075, clip=0xC1E400A9, group=0xC1E4021D,
         images=325, texts=29, properties=2, width=164, height=43, shrink=67,
         font_donor=0xC1E49188, font_size=31, key_budgets=15, font_mask=0x40000014),
    dict(name='LV_CINE_MEDIUM', start=0xC1E59DAA, end=0xC1EAA1ED,
         sha='9e460497a3baabcdc8b2cd7a86fe5bb4148797d2796d7ad3137eb8c36463e58d',
         owner=926, draw=0xC1E8E924, clip=0xC1E8E95C, group=0xC1E8EB48,
         images=324, texts=29, properties=3, width=152, height=35, shrink=161,
         font_donor=0xC1E99617, font_size=25, key_budgets=19, font_mask=0x40000014),
    dict(name='LV_STILLlike_LARGE', start=0xC1F69EAE, end=0xC1FB9B35,
         sha='6b338994dc0861a093a269d9f261c5c43ebdbcee47de7d69e7acb5390d788689',
         owner=6324, draw=0xC1FA3E4B, clip=0xC1FA3E7F, group=0xC1FA4097,
         images=331, texts=28, properties=2, width=164, height=43, shrink=67,
         font_donor=0xC1FA900E, font_size=31, key_budgets=15, font_mask=0x40000004),
    dict(name='LV_STILLlike_MEDIUM', start=0xC1FB9B35, end=0xC200D526,
         sha='baf2690376fec332711ff1623e012ca5ec94ea2744dd9952493a4323aa524ae8',
         owner=926, draw=0xC1FF7A23, clip=0xC1FF7A5B, group=0xC1FF7C73,
         images=358, texts=28, properties=2, width=152, height=35, shrink=71,
         font_donor=0xC1FFC9E0, font_size=25, key_budgets=18, font_mask=0x40000004),
)
SET_SPANS = tuple(dict(name=s['name'], start=s['start'] & ~3,
                      end=(s['end']+3) & ~3) for s in SETS)


def _put(data, at, value):
    out = bytearray(data)
    struct.pack_into('>I', out, at, value)
    return bytes(out)


def _capacity_header(record, spec):
    raw = bytearray(record.body)
    n = struct.unpack_from('>I', raw, 8)[0]
    for i in range(n):
        at = 12+i*8
        name, count = struct.unpack_from('>II', raw, at)
        if name in (0x253E4, 0x2541C):
            wanted = spec['images'] if name == 0x253E4 else spec['texts']
            if count != wanted:
                raise ValueError('unexpected LV drawable allocation counts')
            struct.pack_into('>I', raw, at+4, count+(-1 if name == 0x253E4 else 1))
    cursor = 12+n*8
    # groups: count * three words, then clip property capacities.
    groups = struct.unpack_from('>I', raw, cursor)[0]
    cursor += 4+groups*12
    clips = struct.unpack_from('>I', raw, cursor)[0]
    cursor += 4+clips*4
    keys = struct.unpack_from('>I', raw, cursor)[0]
    cursor += 4
    # Original interpreter C05E687C..C05E6890 only accumulates the arena
    # budget: N*0x34 key bytes + 0x20 curve + N*4 vector pointers. It does
    # not initialize keys. C05E2738/C05D7430 separately creates count=0,
    # capacity=N. Kind 2 is already used by stock image AND text curves.
    grown = 0
    for i in range(keys):
        at = cursor+i*4
        if struct.unpack_from('>I', raw, at)[0] == 10:
            struct.pack_into('>I', raw, at, 11)
            grown += 1
    if grown != spec['key_budgets']:
        raise ValueError('LV key-capacity inventory changed')
    return bytes(raw)


def _property(kind, component, name, dimension, keys):
    keys = tuple(keys)
    out = struct.pack('>5I', len(keys), kind, component, name, dimension)
    for time, value in keys:
        out += b'\0\0' + struct.pack('>I', time)
        out += struct.pack('>f' if kind == 1 else '>I', value)
    return out


def rebuild(image, spec):
    raw = image[spec['start']-BASE:spec['end']-BASE]
    if hashlib.sha256(raw).hexdigest() != spec['sha']:
        raise ValueError('LV resource set differs from pinned stock: '+spec['name'])
    pool = image[POOL_START-BASE:POOL_START-BASE+POOL_SIZE]
    if tuple(N.string_at(pool, p) for p in LABEL_OFFSETS) != LABELS:
        raise ValueError('LV frame-rate literal string pool changed')
    text_name = pool.find(b'\0text\0')+1
    if text_name <= 0:
        raise ValueError('text property name missing')
    records = N.split(raw)
    by_address = {spec['start']+r.offset: r for r in records}
    draw, clip, group = [by_address[spec[k]] for k in ('draw', 'clip', 'group')]
    old_clip = A.parse_clip(A.Record(0, clip.to_bytes()), lambda p: N.string_at(pool, p))
    if old_clip['owner_id'] != spec['owner'] or old_clip['clip_id'] != 4 or \
            len(old_clip['properties']) != spec['properties'] or \
            [(p['name'], p['component_ref']) for p in old_clip['properties']] != \
            [('image', 3)] + [('rect', 3)]*(spec['properties']-1):
        raise ValueError('LV FrameRate is no longer the dedicated image drawable')
    decoded_group = N.decode_image_array(group, pool)
    if decoded_group['group'] != 'FrameRate' or decoded_group['owner'] != spec['owner'] or \
            decoded_group['pairs'] != [(spec['owner'], 4)] or decoded_group['entries'][0]['b'] != 300:
        raise ValueError('LV FrameRate group changed')
    # Same-page TC3_HighLight is a native numeric text donor, with explicit
    # font-size. Use the stock CINE TC3_HighLight left alignment (0) in all
    # four layouts; STILLlike donors leave the alignment implicit. Keep
    # FrameRate's original origin and maximum box.
    font = by_address[spec['font_donor']]
    if font.tag != 0x10005 or font.words(1)[0] != 0x2541C or \
            struct.unpack_from('>2I', font.body, 20) != (spec['font_mask'], spec['font_size']):
        raise ValueError('same-page numeric font donor changed')
    pair_size = draw.size + clip.size
    draw.body = struct.pack('>6I', 0x2541C, 32, 0xFFFFFFFF, spec['owner'], 3, 0x40002015) + \
        struct.pack('>I', LABEL_OFFSETS[0]) + b'\0' + font.body[24:28] + struct.pack('>I', 0) + struct.pack('>I4f', 0xFFFFFFFF,
            0, 0, spec['width'], spec['height'])
    props = [_property(2, 3, text_name, 0, zip(TIMES, LABEL_OFFSETS))]
    # Keep the same property slots/count to preserve allocation ordering.
    rect_name = pool.find(b'\0rect\0')+1
    props.append(_property(1, 3, rect_name, 2, [(0, float(spec['width']))]))
    if spec['properties'] == 3:
        props.append(_property(1, 3, rect_name, 0, [(0, 0.0)]))
    if rect_name <= 0:
        raise ValueError('rect property name changed')
    clip.body = struct.pack('>5I', 0x24974, spec['properties'], 0xFFFFFFFF,
                            spec['owner'], 4) + b''.join(props)
    # The original interpreter's common epilogue C05E7B06..C05E7B1A
    # skips declared bytes that the semantic handler did not consume.
    # Keep draw+clip's total size, so no subsequent record is relocated.
    padding = pair_size - draw.size - clip.size
    if padding != spec['shrink'] or padding < 0:
        raise ValueError('LV local pair no longer fits its original slot')
    clip.body += bytes(padding)
    group.body = _put(group.body, 28, 333)
    records[0].body = _capacity_header(records[0], spec)
    result = N.join(records)
    if len(result) != len(raw):
        raise ValueError('LV resource no longer fits the original slot')
    return result


def patches(image):
    """Local draw+clip pairs, group endpoint words and changed header words."""
    out = []
    for spec in SETS:
        lo, hi = spec['start'] & ~3, (spec['end']+3) & ~3
        old = image[lo-BASE:hi-BASE]
        new = bytearray(old)
        new[spec['start']-lo:spec['end']-lo] = rebuild(image, spec)
        stock_rows = N.split(image[spec['start']-BASE:spec['end']-BASE])
        old_clip = next(r for r in stock_rows if spec['start']+r.offset == spec['clip'])
        header_end = (spec['start']+stock_rows[0].size+3) & ~3
        ranges = [(at,at+4) for at in range(lo,header_end,4)
                  if old[at-lo:at-lo+4] != new[at-lo:at-lo+4]]
        ranges += [(spec['draw'] & ~3, (spec['clip']+old_clip.size+3) & ~3),
                   ((spec['group']+36) & ~3, (spec['group']+40+3) & ~3)]
        merged = []
        for start,end in sorted(ranges):
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0],max(end,merged[-1][1]))
            else:
                merged.append((start,end))
        out += [(at,struct.unpack_from('<I',new,at-lo)[0],'240/15 fps native LV text')
                for start,end in merged for at in range(start,end,4)]
    return out


def _parse_clip(record, resolve):
    """Strict semantic decode plus zero tail allowed by the stock interpreter."""
    cursor = 20
    for _ in range(record.words(2)[1]):
        count = struct.unpack_from('>I',record.body,cursor)[0]
        cursor += 20+count*10
    if cursor > len(record.body) or any(record.body[cursor:]):
        raise ValueError('nonzero or truncated LV clip-tail padding')
    semantic = N.Record(record.tag,record.offset,record.body[:cursor])
    return A.parse_clip(A.Record(0,semantic.to_bytes()),resolve)


@lru_cache(maxsize=4)
def _stock_services(name):
    import nbu_probe as P
    p = P.NbuProbe(P.load_firmware(ROOT/'out/seg0_c0000000.bin'))
    p.install_arena()
    p.map_set(name)
    return tuple(sorted(p.discovered))


@lru_cache(maxsize=4)
def _expected_set(name):
    stock = (ROOT/'out/MAIN_c0000000.bin').read_bytes()
    return rebuild(stock, next(s for s in SETS if s['name'] == name))


def verify_installed(image_or_words, *, base_image=None, native=False):
    if isinstance(image_or_words, (bytes, bytearray)):
        image = bytes(image_or_words)
    else:
        if base_image is None:
            raise ValueError('word verification requires base_image')
        image = bytearray(base_image)
        items = image_or_words.items() if isinstance(image_or_words, Mapping) else image_or_words
        for row in items:
            a, value = row[:2]
            if BASE <= a <= BASE+len(image)-4:
                struct.pack_into('<I', image, a-BASE, value)
        image = bytes(image)
    pool = image[POOL_START-BASE:POOL_START-BASE+POOL_SIZE]
    results = []
    for spec in SETS:
        installed = image[spec['start']-BASE:spec['end']-BASE]
        if installed != _expected_set(spec['name']):
            raise ValueError('installed LV set differs from exact guarded rebuild: '+spec['name'])
        rows = N.split(installed)
        clip = next(r for r in rows if r.tag == 0x1000A and r.words(5)[3:5] == (spec['owner'], 4))
        d = _parse_clip(clip, lambda p: N.string_at(pool, p))
        prop = d['properties'][0]
        labels = tuple(N.string_at(pool, k['value']) for k in prop['keys'])
        if prop['name'] != 'text' or labels != LABELS or tuple(k['time'] for k in prop['keys']) != TIMES:
            raise ValueError('installed LV state labels are incorrect')
        group = next(N.decode_image_array(r, pool) for r in rows
                     if r.tag == 0x1000B and r.words(5)[4] == spec['owner'])
        if group['entries'][0]['b'] != 333:
            raise ValueError('LV group cannot reach the preserved 15 fps state')
        draw = next(r for r in rows if r.tag == 0x10005 and r.words(4)[3] == spec['owner'])
        if draw.words(1)[0] != 0x2541C or draw.body[28] != 0:
            raise ValueError('LV label is not literal drawText')
        if sum(r.size for r in rows) != spec['end']-spec['start']:
            raise ValueError('LV set exceeded its slot')
        item = dict(set=spec['name'], row9=labels[9], row10=labels[10],
                    records=len(rows), native_interpreter_executed=False, gui_rendered=False)
        if native:
            import nbu_probe as P
            p = P.NbuProbe(image[:P.SEG0_SIZE])
            p.install_arena()
            p.allow(*p.OBJECT_FACTORY, 'stock object factory')
            for a in _stock_services(spec['name']):
                p.stub(a, 'stock UI construction service')
            p.open_set(spec['name'])
            for record in rows:
                t = p.record()
                if (t.token, t.cursor_in, t.consumed) != (record.tag, record.offset, record.size) or p.error_flag():
                    raise ValueError('native parser disagrees with LV records')
            if p.traces[-1].result != 1 or p.survey or p.discovered:
                raise ValueError('LV native parse did not terminate under fixed allow-list')
            item['native_interpreter_executed'] = True
            parsed = _verify_native_clip(image, clip.to_bytes(), clip.size-spec['shrink'])
            if parsed['labels'] != list(LABELS) or parsed['times'] != list(TIMES):
                raise ValueError('native clip parser disagrees with installed keys')
            native_keys = [dict(time=t,value=pointer-POOL_START)
                           for t,pointer in zip(parsed['times'],parsed['pointers'])]
            item['native_clip_parser'] = parsed
            item['native_curve_text_states'] = _verify_native_curve_and_text(
                P.NbuProbe(image[:P.SEG0_SIZE]), native_keys)
        results.append(item)
    return results


def _verify_native_curve_and_text(p, keys):
    """Execute stock kind-2 curve construction, key selection and drawText setter.

    Keys come from the installed NBU. The harness supplies key storage and
    duplicates strings, but does not choose the key or implement the setter.
    Original drawText metadata/vtable and dirty callback are used. Numeric
    int64-to-float conversion is the only arithmetic service stub (all times
    here are exactly representable); the interpolation/selection code is real.
    """
    from unicorn.arm_const import UC_ARM_REG_S0
    real = (
        (0xC05E2738, 0xC05E2776), (0xC05D7430, 0xC05D745C),
        (0xC05E28B8, 0xC05E2900), (0xC05D74D8, 0xC05D7534),
        (0xC05EDB08, 0xC05EDB10), (0xC05EDB38, 0xC05EDB3E),
        (0xC05E2280, 0xC05E2324), (0xC05E2970, 0xC05E2988),
        (0xC05D6990, 0xC05D6BA0), (0xC05D6BB8, 0xC05D6BE0),
        (0xC05D5670, 0xC05D56F2), (0xC05D54C8, 0xC05D5534),
        (0xC05EC910, 0xC05EC956), (0xC05D6FC0, 0xC05D6FC6),
        (0xC05FE518, 0xC05FE51C), (0xC05FE308, 0xC05FE318),
        (0xC05FDA20, 0xC05FDA38), (0xC05D7148, 0xC05D7160),
    )
    for lo, hi in real:
        p.allow(lo, hi, 'stock curve/drawText implementation')
    def convert(probe, args):
        value = args[0] | (args[1] << 32)
        probe.uc.reg_write(UC_ARM_REG_S0, struct.unpack('<I', struct.pack('<f', value))[0])
        return 0
    def duplicate(probe, args):
        data = probe.string(args[1]).encode()+b'\0'
        pointer = probe._allocate(len(data))
        probe.write(pointer, data)
        return pointer
    p.stub(0xC01F82CC, 'exact small timestamp int64-to-float', handler=convert)
    p.stub(0xC05D9B40, 'allocator string duplication', handler=duplicate)
    p.stub(0xC05D9D18, 'empty external property registry')
    p.stub(0xC05D9B80, 'allocator string release')
    # Use a fresh bounded arena for this independent native component probe.
    out, state = p._allocate(4), p._allocate(0x40)
    if p._call(0xC05E2738, p.ALLOCATOR, 2, len(keys), out):
        raise ValueError('native string curve allocation failed')
    curve = p.words(out)[0]
    if p.words(curve+0x10, 2) != (0, len(keys)):
        raise ValueError('native curve capacity unexpectedly initializes live keys')
    for key in keys:
        pointer = p._allocate(0x34)
        p.write(pointer, struct.pack('<Q', key['time']))
        p.write_words(pointer+8, 1, 0, p.ALLOCATOR, 0, POOL_START+key['value'])
        if p._call(0xC05E28C8, curve, pointer):
            raise ValueError('native string key append failed')
    if p.words(curve+0x10, 2) != (len(keys), len(keys)):
        raise ValueError('native curve did not receive all installed keys')
    component, context = p._allocate(0x100), p._allocate(0x100)
    indexes, data, private = p._allocate(0x100), p._allocate(0x400), p._allocate(0x100)
    p.write_words(component, context)
    p.write_words(context+0xC, p.ALLOCATOR)
    p.write_words(component+0x10, 0xC2E03A14, 32, 0xC2E035AC, indexes, data)
    p.write_words(component+0x34, private)
    labels = []
    # Exact endpoints and points between them exercise native step selection.
    for time, expected in [(t, s) for t, s in zip(TIMES, LABELS)] + [(316, '240'), (334, '15')]:
        p.write(state+0x1C, struct.pack('<f', time))
        value = p._call(0xC05E2970, curve, state)
        if p.string(value) != expected:
            raise ValueError('native text curve selected the wrong frame-rate key')
        p._call(0xC05D6BB8, component, 0, value)
        stored = p.words(data)[0]
        if p.string(stored) != expected or not p.words(private+8)[0] & 1 or p.words(data+8)[0] != 0:
            raise ValueError('native drawText setter did not store/dirty literal label')
        labels.append((time, p.string(stored)))
    if any(c.address in (0xC05EC220, 0xC05EC478) for c in p.calls):
        raise ValueError('numeric LV label unexpectedly used localization resolver')
    # Positive control proves the same real setter can detect and route markup;
    # numeric labels above must never reach either resolver service.
    marker = p._allocate(32)
    p.write(marker, b'<!positive-control>\0')
    resolver = p._allocate(32)
    p.stub(0xC05EC220, 'positive-control resolver creation', ret=resolver)
    p.stub(0xC05EC478, 'positive-control resolver assignment')
    before = len(p.calls)
    p._call(0xC05D6BB8, component, 0, marker)
    calls = [c.address for c in p.calls[before:] if c.address in (0xC05EC220, 0xC05EC478)]
    if calls != [0xC05EC220, 0xC05EC478] or p.words(data+12)[0] != resolver:
        raise ValueError('native literal/markup positive control failed')
    return labels


def _verify_native_clip(image, clip, semantic_length):
    """Run the complete original clip reader, then its declared-length skip.

    Object lookup, allocation and ownership services use bounded storage;
    field, key, timestamp and string-pool decoding executes original firmware.
    """
    import nbu_probe as P
    from unicorn import UC_HOOK_CODE
    from unicorn.arm_const import UC_ARM_REG_SP, UC_ARM_REG_R1
    p = P.NbuProbe(image[:P.SEG0_SIZE]); p.install_arena()
    p.allow(0xC05E5F10,0xC05E5F1E,'native object id converter')
    component, owner, klass = [p._allocate(0x80) for _ in range(3)]
    p.stub(0xC05D9E80,'known animation clip class lookup',ret=klass)
    p.stub(0xC05E82A0,'known existing owner lookup',ret=owner)
    def create(q,args):
        out=q.words(q.uc.reg_read(UC_ARM_REG_SP)+4)[0]
        q.write_words(out,component)
        return 0
    p.stub(0xC05D5968,'bounded clip component constructor',handler=create)
    for a in (0xC05D5DB8,0xC05E1A58,0xC05E2798,0xC05D1490,0xC05D5D08,0xC05EDB10):
        p.stub(a,'component/curve ownership service')
    curves, strings, skips = {}, [], []
    def curve(q,args):
        addr=q._allocate(0x40)
        q.write_words(addr+8,args[1])
        q.write_words(args[3],addr)
        curves[addr]={'kind':args[1],'capacity':args[2],'keys':[]}
        return 0
    p.stub(0xC05E2738,'bounded curve storage constructor',handler=curve)
    p.stub(0xC05EDB90,'bounded native key storage',handler=lambda q,a:q._allocate(0x40))
    def string(q,args):
        q.write_words(args[0]+0x18,args[1]);strings.append(q.string(args[1]));return 0
    p.stub(0xC05EDBE8,'string ownership storage',handler=string)
    def append(q,args):
        curves[args[0]]['keys'].append(q.words(args[1],13));return 0
    p.stub(0xC05E28C8,'curve key storage append',handler=append)
    def attach(q,args):
        curves[args[1]].update(component=args[2],property=q.string(args[3]));return 0
    p.stub(0xC05E1C28,'attach parsed curve to component',handler=attach)
    p.open(blob=clip,magic=False,cursor=0,pool=(0x2B018,0xC18C0474),owner=True)
    p.write_words(p.OWNER+0xC,p.ALLOCATOR)
    def capture(uc,a,size,_):
        if a==P.SKIP:
            skips.append((p.words(p.CTX+4)[0],uc.reg_read(UC_ARM_REG_R1)))
    p.uc.hook_add(UC_HOOK_CODE,capture)
    result=p.record()
    assert result.result==0 and result.consumed==len(clip) and not p.error_flag()
    assert len(curves)==struct.unpack_from('>I',clip,12)[0]
    for c in curves.values():assert len(c['keys'])==c['capacity']
    padding=len(clip)-semantic_length
    assert skips==([(semantic_length,padding)] if padding else []),skips
    text=next(c for c in curves.values() if c.get('property')=='text')
    assert text['kind']==2
    return {'labels':strings,'times':[k[0] for k in text['keys']],
            'pointers':[k[6] for k in text['keys']], 'skip':skips,
            'curves':len(curves),'consumed':result.consumed,
            'pool_parser_executed':True,'sp_restored':True}

