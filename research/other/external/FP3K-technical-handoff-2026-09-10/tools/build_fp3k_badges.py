"""Create new 3K glyph assets and a separate native resource pack.

No stock image or resource descriptor is overwritten. Run with the bundled
Python runtime (Pillow). The native decoder verification is a separate step.
"""
from pathlib import Path
import hashlib
import json
import struct
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'prototype/development/native-ui'

def lz4_block(raw):
    out = bytearray()
    seen = {}
    anchor = i = 0
    def length(n):
        while n >= 255:
            out.append(255)
            n -= 255
        out.append(n)
    while i + 12 < len(raw):
        key = raw[i:i+4]
        previous = seen.get(key)
        seen[key] = i
        if previous is None or i-previous > 65535:
            i += 1
            continue
        n = 4
        while i+n < len(raw)-5 and raw[previous+n] == raw[i+n]:
            n += 1
        literal = i-anchor
        out.append((min(literal, 15) << 4) | min(n-4, 15))
        if literal >= 15:
            length(literal-15)
        out.extend(raw[anchor:i])
        out.extend(struct.pack('<H', i-previous))
        if n-4 >= 15:
            length(n-19)
        i += n
        anchor = i
    literal = len(raw)-anchor
    out.append(min(literal, 15) << 4)
    if literal >= 15:
        length(literal-15)
    out.extend(raw[anchor:])
    return bytes(out)

def xci(w, h, raw):
    payload = lz4_block(raw)
    # Sigma's frame variant has version bits 2 and no enforced header checksum.
    # Its content-size field measures the encoded frame after the magic.
    frame = bytes.fromhex('04224d188810') + struct.pack('<Q', len(payload)+19)
    frame += b'\0' + struct.pack('<I', len(payload)) + payload + bytes(4)
    header = bytearray(32)
    header[:4] = b'XC\0\0'
    struct.pack_into('<IHH', header, 4, len(frame), w, h)
    header[12:20] = bytes.fromhex('0004000002020000')
    return bytes(header)+frame

def glyph(w, h, font_size, stroke):
    scale = 4
    font = ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial Bold.ttf', font_size*scale)
    ink = Image.new('L', (w*scale, h*scale))
    alpha = Image.new('L', ink.size)
    box = font.getbbox('3K')
    pos = ((w*scale-(box[2]-box[0]))//2-box[0], (h*scale-(box[3]-box[1]))//2-box[1])
    ImageDraw.Draw(ink).text(pos, '3K', font=font, fill=255)
    ImageDraw.Draw(alpha).text(pos, '3K', font=font, fill=255,
                               stroke_width=stroke*scale, stroke_fill=255)
    ink = ink.resize((w, h), Image.Resampling.LANCZOS)
    alpha = alpha.resize((w, h), Image.Resampling.LANCZOS)
    values = [((a*15+127)//255 << 12) | (((v*15+127)//255)*0x111)
              for v, a in zip(ink.get_flattened_data(), alpha.get_flattened_data())]
    preview = Image.new('RGBA', (w, h))
    preview.putdata([(255*v//max(a,1),)*3+(a,) for v,a in zip(ink.get_flattened_data(),alpha.get_flattened_data())])
    return struct.pack('<'+'H'*len(values), *values), preview

def fnv(name):
    value = 0x811c9dc5
    for x in name.encode():
        value = ((value ^ x)*0x1000193) & 0xffffffff
    return value

def resource_pack(assets):
    """NBR 1.5: string pool, files, named xcimage resources, property records."""
    strings = bytearray(4)
    offsets = {}
    def string(value):
        if value not in offsets:
            offsets[value] = len(strings)
            strings.extend(value.encode()+b'\0')
            strings.extend(bytes((-len(strings)) % 4))
        return offsets[value]
    string('xcimage')
    for name, data in assets:
        string(name)
        string(name+'.xci')
    result = bytearray(b'NBR\0\x01\x05'+bytes(6))
    result.extend(struct.pack('>II', 1, 8+len(strings))+strings)
    start = len(result)
    result.extend(bytes(12+16*len(assets)))
    entries = []
    for name, data in assets:
        entries.append((fnv(name+'.xci'),string(name+'.xci'),len(result),len(data)))
        result.extend(data)
        result.extend(bytes((-len(result)) % 4))
    struct.pack_into('>III',result,start,2,len(result)-start,len(assets))
    for i, entry in enumerate(sorted(entries)):
        struct.pack_into('>4I',result,start+12+16*i,*entry)
    start = len(result)
    result.extend(struct.pack('>4I',0x20001,16+36*len(assets),len(assets),len(assets)))
    definitions = len(result)
    result.extend(bytes(36*len(assets)))
    result.extend(struct.pack('>II',0xffffffff,8))
    for i,(name,data) in enumerate(assets):
        struct.pack_into('>9I',result,definitions+36*i,string(name),string('xcimage'),
                         0,0xffffffff,0,1,0xffffffff,0xffffffff,len(result))
        result.extend(struct.pack('>12I',0x20002,48,5,31,string(name+'.xci'),0,0,0,0,0,0,0))
    result.extend(struct.pack('>II',0xffffffff,8))
    return bytes(result)

def build():
    OUT.mkdir(parents=True,exist_ok=True)
    assets=[]; rows=[]
    for name,w,h,size,stroke in [('FP3K_L',93,43,32,1),('FP3K_M',78,35,27,1),('FP3K_QS',86,49,34,0),('FP3K_SET',86,74,34,0),('FP3K_FONT',150,38,32,0)]:
        raw,preview=glyph(w,h,size,stroke)
        data=xci(w,h,raw)
        (OUT/(name+'.raw')).write_bytes(raw)
        (OUT/(name+'.xci')).write_bytes(data)
        preview.save(OUT/(name+'.png'))
        assets.append((name,data))
        rows.append(dict(name=name,width=w,height=h,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
    pack=resource_pack(assets)
    (OUT/'FP3KUI.NBR').write_bytes(pack)
    report=dict(status='Offline resource candidate; not installed',assets=rows,pack_bytes=len(pack),
                pack_sha256=hashlib.sha256(pack).hexdigest())
    (OUT/'badges.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':
    build()
