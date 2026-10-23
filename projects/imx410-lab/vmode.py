#!/usr/bin/env python3
"""Virtual sensor modes: run the firmware's own mode switch (SetImgMode_s) on table rows we generate.

The IMX410 driver looks every mode up in 8 tables (notes/MODE_TABLES.md, MODE_TABLES_CONSUMERS.md). We copy all 8
into one allocation, replace the rows of one HOST mode id (default 10 = magnify) with our rows, point the descriptor
0xC2F1E654 (+ the REG table object 0xC343B67C) at the copies, and enter magnify: the firmware then programs the
sensor, receiver, DCLP, clocks, sync generator and statistics exactly as for a stock mode -- and the per-frame AE
callback keeps re-applying OUR DCLP row, which is why patching registers on top of mode 10 could never work.
Nothing is written to the settings area; restore() points everything back (a reboot does too).

    vmode.py apply DONOR [HOST]     put mode DONOR's rows under id HOST (test: 8 under 10 must equal native mode 8)
    vmode.py restore
    vmode.py test DONOR OUT         apply, capture a frame pair in magnify, restore
"""
import json, pathlib, struct, sys, time
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bufa_probe as B                                                # noqa: E402

DESC = 0xC2F1E654
REGOBJ = 0xC343B67C
TABLES = {  # name: (descriptor offset of the pointer, ROM address, stride, offset of the mode id word)
    'TIM': (0x00, 0xC0B59500, 0x20, 0), 'META': (0x08, 0xC0B59DC0, 100, 0), 'R10': (0x10, 0xC0B5B918, 8, 4),
    'R28': (0x24, 0xC0B5BB48, 0x28, 0), 'R38': (0x40, 0xC0B5C638, 0x38, 0), 'R14': (0x48, 0xC0B5D588, 0x14, 0),
    'R68': (0xF4, 0xC0B5DB00, 0x68, 0)}
REGDESC_ROM, REG_ROM, REG_STRIDE, N = 0xC0B5FDA4, 0xC0B5FDAC, 0x288, 70
STATE = HERE / 'captures' / 'vmode_state.json'
NOZOOM = 0xC2F1E770          # descriptor +0x11C, initially 1: 0 skips FUN_c031B3A0 / v32 (the magnify window that
                             # overwrote the donor's sensor window, MODE_TABLES_CONSUMERS §7) -- opt-in, KEEP_WINDOW
KEEP_WINDOW = False


def read(addr, n):
    out = b''
    while len(out) < n:
        k = min(0x400, n - len(out))
        words = B.P().mem_get(addr + len(out), (k + 3) // 4)
        if None in words or len(words) != (k + 3) // 4:
            raise SystemExit(f'read 0x{addr + len(out):08X} incomplete')
        out += struct.pack(f'<{len(words)}I', *words)[:k]
    return out


def check_stock():
    for name, (off, rom, st, key) in TABLES.items():
        p, n = B.P().mem_get(DESC + off, 2)
        if p != rom or n != N:
            raise SystemExit(f'{name}: descriptor has 0x{p:08X}/{n}, not stock -- restore first')
    if B.P().mem_get(REGOBJ)[0] != REGDESC_ROM:
        raise SystemExit('REG object is not stock -- restore first')


def row_index(tab, st, key, mode):
    for i in range(N):
        if struct.unpack_from('<I', tab, i * st + key)[0] == mode:
            return i
    raise SystemExit(f'mode {mode} not in table')


def build(rows, host):
    """rows: {table name or 'REG': bytes of one row (mode id word included, it is overwritten)} for the host id."""
    blobs, layout = {}, {}
    for name, (off, rom, st, key) in list(TABLES.items()) + [('REG', (None, REG_ROM, REG_STRIDE, 0))]:
        tab = bytearray(read(rom, st * N))
        if name in rows:
            i = row_index(tab, st, key, host)
            r = bytearray(rows[name]); struct.pack_into('<I', r, key, host)
            tab[i * st:(i + 1) * st] = r
        blobs[name] = bytes(tab)
    return blobs


def donor_rows(donor):
    out = {}
    for name, (off, rom, st, key) in list(TABLES.items()) + [('REG', (None, REG_ROM, REG_STRIDE, 0))]:
        tab = read(rom, st * N)
        i = row_index(tab, st, key, donor)
        out[name] = tab[i * st:(i + 1) * st]
    return out


def apply(rows, host=10, note=''):
    import imxl
    check_stock()
    blobs = build(rows, host)
    total = sum((len(b) + 15) // 16 * 16 for b in blobs.values()) + 16
    imxl.HEAP_CLASS = 0
    addr, desc = imxl.heap(0, total)
    if not addr:
        raise SystemExit('allocator refused')
    STATE.write_text(json.dumps(dict(addr=addr, desc=desc, host=host, note=note, t=time.time())))
    at, ptr = addr, {}
    for name, b in blobs.items():
        B.P().put(at, b, name[:6].ljust(6))
        ptr[name] = at
        at += (len(b) + 15) // 16 * 16
    regdesc = at
    B.P().put(regdesc, struct.pack('<II', ptr['REG'], N), 'regdsc')
    B.call(B.F_DCACHE)
    for name, (off, rom, st, key) in TABLES.items():
        B.wr(DESC + off, ptr[name])
    B.wr(REGOBJ, regdesc)
    if KEEP_WINDOW:
        B.wr(NOZOOM, 0)
    print(f'virtual rows under mode {host} ({note}); tables at 0x{addr:08X}, {total} B')


def restore():
    import imxl
    for name, (off, rom, st, key) in TABLES.items():
        B.wr(DESC + off, rom)
        B.wr(DESC + off + 4, N)
    B.wr(REGOBJ, REGDESC_ROM)
    if (B.P().mem_get(NOZOOM) or [1])[0] != 1:
        B.wr(NOZOOM, 1)
    if STATE.exists():
        s = json.loads(STATE.read_text())
        imxl.HEAP_CLASS = 0
        try:
            imxl.heap(1, 0, s['desc'])
        finally:
            STATE.unlink()
    print('descriptor back on the ROM tables')


def test(donor, out, rows=None, host=10):
    import fastsweep as F
    F.cached_assemble()
    B.not_recording()
    if ',0008,' not in B.P().sh('imager mode_now'):
        raise SystemExit('start from live view (mode 8)')
    apply(rows or donor_rows(donor), host, f'donor {donor}')
    try:
        s = F.Session(out, 0, True, host, min_alloc=24 << 20)
        try:
            ok = s.grab(out / f'v{donor}')
            st = {f'0x{0x301005D8:08X}': B.P().mem_get(0x301005D8)[0], f'0x{0x30100588:08X}': B.P().mem_get(0x30100588)[0],
                  'mode_now': B.P().sh('imager mode_now')[:400]}
            (out / f'v{donor}' / 'status.json').write_text(json.dumps(st, indent=1)) if ok else None
            print('frame', 'ok' if ok else 'NO FRAME')
        finally:
            s.close()
    finally:
        restore()


if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'apply':
        apply(donor_rows(int(sys.argv[2])), int(sys.argv[3]) if len(sys.argv) > 3 else 10, f'donor {sys.argv[2]}')
    elif cmd == 'restore':
        restore()
    elif cmd == 'test':
        o = pathlib.Path(sys.argv[3]); o.mkdir(parents=True, exist_ok=True)
        test(int(sys.argv[2]), o)
