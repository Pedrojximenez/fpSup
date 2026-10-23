"""Build iconcache.bin and patch.json.

    python3 -B build.py

iconcache.bin is position-independent ARM code with its control block and
entry table at offset 0.  The arena (decoded pixels) is NOT inside it: the
installer gives an 8-aligned block and writes ARENA / ARENA_SZ.  The two
hooks are aligned Thumb32 words (single 32-bit writes), each a b.w to an
8-byte Thumb veneer `ldr.w pc, [pc, #0] ; .word body+entry` (even target =
ARM).
"""
import hashlib, json, pathlib, struct, sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'fpSup' / 'fp_usb_shell'))
from armasm import assemble, symbols  # noqa: E402

SRC = HERE / 'iconcache.S'
SEG0 = ROOT / 'out' / 'seg0_c0000000.bin'
B = 0xC0000000

# (name, site, stock word, stock insns, entry symbol, return)
SITES = [
    ('h1', 0xC060219C, 0x46586B71, 'ldr r1,[r6,#0x34] ; mov r0,fp', 'ic_h1',
     'miss: C06021A0 (blx r2, stock decode) / hit: C060235A (ldr.w fp,[sp,#0x48])'),
    ('h2', 0xC060234C, 0x92243204, 'adds r2,#4 ; str r2,[sp,#0x90]', 'ic_h2', 'C0602350'),
]
VENEER = (0xF8DF, 0xF000)          # ldr.w pc, [pc, #0]  (veneer must be 4-aligned)
CTL = {'magic': 0x00, 'enable': 0x04, 'arena': 0x08, 'arena_size': 0x0C, 'max_entry': 0x10,
       'hits': 0x14, 'misses': 0x18, 'inserts': 0x1C, 'evicts': 0x20, 'skips': 0x24,
       'alloc_fail': 0x28, 'pending_sp': 0x2C, 'clock': 0x40, 'rejects': 0x48, 'table': 0x50}


def thumb_bw(at, to):
    """T4 b.w from `at` to `to`, as the 32-bit word stored at `at` (aligned)."""
    off = to - (at + 4)
    assert -(1 << 24) <= off < (1 << 24) and not off & 1
    s = (off >> 24) & 1
    i1, i2 = (off >> 23) & 1, (off >> 22) & 1
    j1, j2 = (~(i1 ^ s)) & 1, (~(i2 ^ s)) & 1
    hw1 = 0xF000 | (s << 10) | ((off >> 12) & 0x3FF)
    hw2 = 0x9000 | (j1 << 13) | (j2 << 11) | ((off >> 1) & 0x7FF)
    return hw1 | (hw2 << 16)


def veneer(target):
    assert not target & 1, 'ARM entry must be even'
    return struct.pack('<HHI', VENEER[0], VENEER[1], target)


def main():
    code = assemble(SRC)
    sym = symbols(SRC)
    rom = SEG0.read_bytes()
    for name, site, stock, *_ in SITES:
        assert not site & 3, name
        got = struct.unpack_from('<I', rom, site - B)[0]
        if got != stock:
            raise SystemExit(f'{name} {site:#x}: image has {got:#010x}, expected {stock:#010x}')
    assert struct.unpack_from('<I', code, 0)[0] == 0x48434349
    (HERE / 'iconcache.bin').write_bytes(code)
    patch = {
        'firmware': 'Ver.5.02, out/seg0_c0000000.bin',
        'body': {
            'file': 'iconcache.bin', 'bytes': len(code),
            'sha256': hashlib.sha256(code).hexdigest(),
            'isa': 'ARM, position independent, integer only (no VFP/NEON)',
            'alignment': 8,
            'entries': {k: sym[k] for k in ('ic_h1', 'ic_h2')},
            'control': CTL,
            'control_note': 'enable=0: both hooks only redo their two stock instructions. '
                            'arena/arena_size: the installer writes an 8-aligned block (suggest 1-2 MiB '
                            'of the sup block BSS, class-0 USER heap like every v3 sup block). '
                            'max_entry: icons decoding larger than this are not cached.',
        },
        'veneers': {
            'bytes': 8, 'count': 2, 'alignment': 4,
            'layout': 'F8DF F000 (ldr.w pc,[pc,#0]) then body+entry (even = ARM)',
            'placement': 'cave_alloc / cave.claim, 4-aligned, within +-16 MiB of the sites (cave arena is)',
        },
        'sites': [
            {'name': n, 'address': f'{a:#010x}', 'isa': 'Thumb (aligned Thumb32 word)',
             'orig_word': f'{w:#010x}', 'orig_insns': i, 'new': 'b.w <veneer> (thumb_bw in build.py)',
             'entry': e, 'returns_to': r,
             'branch_targets_inside': 'none (checked: no branch in C0601F98 lands on the word or its 2nd half)',
             'power_off_restore': 'declare/claim as a 4-byte section with orig_word (SUP_BUILD_RULES s4)'}
            for n, a, w, i, e, r in SITES],
        'arm_order': ['write body + veneers, read back', 'write ARENA/ARENA_SZ (EN still 0)',
                      'C000E91C then C000EABC', 'patch h2, then h1 (each a single aligned word; '
                      'C000E91C + C000EABC after each)', 'enable=1'],
        'disarm_order': ['enable=0 (data, next call)', 'or restore h1 then h2 + cache maintenance',
                         'keep body and arena until reboot'],
        'firmware_calls_from_body': ['C001510C memcpy', 'the UIC alloc [r6+0] (hit path, same args as stock)'],
        'context': 'DrawMgr (UIC image node load). Table edits mask IRQ/FIQ briefly; copies run with the '
                   'entry pinned. A second task loading images concurrently only loses caching '
                   '(pending key is tied to the frame sp).',
        'behaviour_difference': 'only when the UIC allocator returns 0 on a hit: stock would decode into '
                                'address 0; the hit path leaves [sp+0x48]=0 and the stock error path runs.',
    }
    (HERE / 'patch.json').write_text(json.dumps(patch, indent=1) + '\n')
    print(f'iconcache.bin {len(code)} B, sites ok, sha256 {patch["body"]["sha256"][:16]}')


if __name__ == '__main__':
    main()
