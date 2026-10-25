#!/usr/bin/env python3
"""After a take: the CinemaDNG frames still sitting in the RAW class (10), read only.

Why this should work (notes/PUSH_CALLERS.md §3, offline):
  - every movie frame's RAW buffer is its own class-10 allocation (C037A990,
    frame+0x68), the DNG file starting at allocation+0x2000 (lossless-sup C1);
    each one goes back to the allocator once the card has it (C03777B8)
  - the allocator (FUN_c00104a8) is a first-fit chain of blocks headed
    0xDEADBEEF; a free does not clear the data
  - after a take `memmgr bufuse` shows RAW used 0 (lossless-sup 10-12)
So the last frames of the take should still be readable until the next take
allocates.  This tool tests that with no camera code: it reads the arena over
MEM1 in standby, keeps every buffer that starts like a DNG, and `match`
compares them with the take's files copied off the card.

    rawpool.py probe OUT_DIR           class table, chain, bufuse (a few words)
    rawpool.py scan OUT_DIR [--max 64]  the arena -> OUT_DIR/dng_<addr>.dng + scan.json
    rawpool.py match OUT_DIR CLIP_DIR   sha256 of each found DNG against the clip's files

Rules: never while recording, never in playback, ten seconds after the stop.
"""
import argparse, datetime as dt, hashlib, json, pathlib, re, struct, sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SHELL = ROOT / 'fpSup' / 'fp_usb_shell'

CLASS_TABLE = 0xC30739DC        # FUN_c001cf78: [table + 4*class] = the class object
RAW_CLASS = 10
BLOCK_MAGIC = 0xDEADBEEF        # FUN_c00104a8: "invalid chain code" otherwise
WIN_SLOT = 7
CHUNK = 16 << 20                # one window grant, one MEM1 read
ALIGN = 0x40                    # allocations are 0x40-aligned (FUN_c00104a8)
DNG_MAX = 64 << 20


def dng_size(b, at=0):
    """Size of a little-endian TIFF/DNG whose header is at b[at:], or None.
    The size is the end of the furthest strip or tile in IFD0 (CinemaDNG keeps
    the main image there, no SubIFD: memory cinemadng-ifd-layout)."""
    if b[at:at + 4] != b'II*\0':
        return None
    try:
        ifd, = struct.unpack_from('<I', b, at + 4)
        if not 8 <= ifd < 1 << 20:
            return None
        n, = struct.unpack_from('<H', b, at + ifd)
        if not 1 <= n <= 512:
            return None
        tags = {}
        for i in range(n):
            tag, typ, cnt, val = struct.unpack_from('<HHII', b, at + ifd + 2 + 12 * i)
            tags[tag] = (typ, cnt, val)
    except struct.error:
        return None
    end = at + ifd + 2 + 12 * n + 4

    def values(tag):
        if tag not in tags:
            return []
        typ, cnt, val = tags[tag]
        size = {3: 2, 4: 4}.get(typ)
        if size is None or cnt > 4096:
            return []
        if cnt * size <= 4:
            return list(struct.unpack_from('<' + 'HI'[size == 4] * cnt, struct.pack('<I', val)))
        return list(struct.unpack_from('<' + 'HI'[size == 4] * cnt, b, at + val))
    try:
        offs, cnts = values(273) or values(324), values(279) or values(325)
    except struct.error:
        return None
    if not offs or len(offs) != len(cnts) or 256 not in tags or 257 not in tags:
        return None
    size = max(o + c for o, c in zip(offs, cnts))
    size = max(size, end - at)
    return size if size <= DNG_MAX else None


def find_dngs(buf, base=0, align=ALIGN):
    """[(offset, size)] of every DNG header at an `align` boundary in buf."""
    found = []
    i = buf.find(b'II*\0')
    while i >= 0:
        if (base + i) % align == 0:
            n = dng_size(buf, i)
            if n:
                found.append((i, n))
        i = buf.find(b'II*\0', i + 1)
    return found


def api():
    sys.path.insert(0, str(SHELL))
    import putfile as p
    return p


def not_recording(p):
    if not p.sh('status get is_recording').strip().endswith('0'):
        raise SystemExit('recording: no USB during recording')


def bufuse(p):
    text = p.sh('memmgr bufuse', retries=3)
    mode = re.search(r'mem mode = (\S+)', text)
    raw = re.search(r'RAW\s+\(10\):\s*\[total:\s*(\d+)\]\[used:\s*(\d+)\]\[used\(max\):\s*(\d+)\]', text)
    return {'text': text, 'mode': mode and mode.group(1),
            'raw': raw and dict(zip(('total', 'used', 'used_max'), map(int, raw.groups())))}


def walk_chain(read_words, first, limit=4096):
    """Blocks of a class's chain: [{at, size, next}] from the first block.
    read_words(addr, n) -> list of n u32."""
    blocks, at = [], first
    while at and len(blocks) < limit:
        w = read_words(at, 4)
        if w[0] != BLOCK_MAGIC:
            blocks.append({'at': at, 'bad_magic': w[0]})
            break
        blocks.append({'at': at, 'size': w[1], 'w2': w[2], 'next': w[3]})
        at = w[3] & ~0x3F
    return blocks


def probe(p):
    not_recording(p)
    obj = p.mem_get(CLASS_TABLE + 4 * RAW_CLASS)[0]
    words = p.mem_get(obj, 16)
    # FUN_c001d038(obj): heap = obj + 8; FUN_c00104a8: chain starts at heap + 4
    first = words[3]
    chain = walk_chain(lambda a, n: p.mem_get(a, n), first)
    return {'class_obj': obj, 'obj_words': words, 'first_block': first, 'chain': chain,
            'bufuse': bufuse(p)}


def arena(rep):
    """[lo, hi) the chain covers (uncached alias)."""
    ok = [b for b in rep['chain'] if 'size' in b]
    if not ok:
        raise SystemExit('no chain: run probe and look at it first')
    lo = min(b['at'] for b in ok)
    hi = max(b['at'] + b['size'] for b in ok)
    return lo, hi


def read_span(p, at, n):
    caps = p.mem_caps(refresh=True)
    if tuple(caps['windows'][WIN_SLOT]) != (0, 0, 0):
        raise SystemExit('MEM1 window slot already owned')
    grant = (at, n, 1)
    try:
        p.mem_window(WIN_SLOT, *grant)
        return p.mem_read(at, n, sync=False, label='rawpool')
    finally:
        if tuple(p.mem_caps(refresh=True)['windows'][WIN_SLOT]) == grant:
            p.mem_window(WIN_SLOT, 0, 0, 0)


def scan(p, out, rep, max_dng):
    not_recording(p)
    use = bufuse(p)
    if not use['raw'] or use['raw']['used'] != 0:
        raise SystemExit(f'RAW class in use ({use["raw"]}): only after a take, in standby')
    lo, hi = arena(rep)
    out.mkdir(parents=True, exist_ok=True)
    found, at = [], lo
    while at < hi and len(found) < max_dng:
        n = min(CHUNK, hi - at)
        buf = read_span(p, at, n)
        for off, size in find_dngs(buf, at):
            a = at + off
            data = buf[off:off + size] if off + size <= len(buf) else read_span(p, a, size)
            name = f'dng_{a:08x}.dng'
            (out / name).write_bytes(data)
            found.append({'at': a, 'size': size, 'file': name, 'sha256': hashlib.sha256(data).hexdigest()})
            if len(found) >= max_dng:
                break
        at += n
    res = {'date_utc': dt.datetime.now(dt.timezone.utc).isoformat(), 'arena': [lo, hi],
           'bufuse_before': use, 'found': found,
           'tool_sha256': hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()}
    (out / 'scan.json').write_text(json.dumps(res, indent=1))
    return res


def match(out, clip):
    found = json.loads((out / 'scan.json').read_text())['found']
    card = {hashlib.sha256(f.read_bytes()).hexdigest(): f.name for f in sorted(clip.glob('*.dng')) + sorted(clip.glob('*.DNG'))}
    rows = [dict(f, card=card.get(f['sha256'])) for f in found]
    (out / 'match.json').write_text(json.dumps(rows, indent=1))
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    for c in ('probe', 'scan', 'match'):
        s = sub.add_parser(c); s.add_argument('out', type=pathlib.Path)
        if c == 'scan':
            s.add_argument('--max', type=int, default=64)
        if c == 'match':
            s.add_argument('clip', type=pathlib.Path)
    a = ap.parse_args()
    if a.cmd == 'match':
        rows = match(a.out, a.clip)
        print(f'{sum(1 for r in rows if r["card"])}/{len(rows)} found DNGs are byte-identical to a card file')
        return
    p = api()
    if a.cmd == 'probe':
        rep = probe(p)
        a.out.mkdir(parents=True, exist_ok=True)
        (a.out / 'probe.json').write_text(json.dumps(rep, indent=1))
        print(json.dumps({k: rep[k] for k in ('class_obj', 'first_block')} | {'blocks': len(rep['chain']),
                          'raw': rep['bufuse']['raw'], 'mode': rep['bufuse']['mode']}))
        return
    rep = json.loads((a.out / 'probe.json').read_text())
    res = scan(p, a.out, rep, a.max)
    print(f'arena {res["arena"][0]:#x}..{res["arena"][1]:#x}: {len(res["found"])} DNG')


if __name__ == '__main__':
    main()
