"""Build pagelru.bin and patch.json.

    python3 -B build.py

Two Thumb code words change: the screen switch's `bl C05D90F0` (load next) at
C05DD5CA and `bl C05D91A0` (unload old current) at C05DD670.  Each becomes a
Thumb BLX to an 8-byte ARM veneer (`ldr pc,[pc,#-4]; .word entry`) within
+-16 MiB.  The body is position-independent ARM.
"""
import hashlib, json, pathlib, struct, sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'fpSup' / 'fp_usb_shell'))
from armasm import assemble, symbols  # noqa: E402

SRC = HERE / 'pagelru.S'
SEG0 = ROOT / 'out' / 'seg0_c0000000.bin'
B = 0xC0000000
SITES = [('load', 0xC05DD5CA, 0xC05D90F0, 'pl_load'),
         ('unload', 0xC05DD670, 0xC05D91A0, 'pl_unload')]


def thumb_bl_target(h1, h2, at):
    s = (h1 >> 10) & 1
    j1, j2 = (h2 >> 13) & 1, (h2 >> 11) & 1
    i1, i2 = 1 - (j1 ^ s), 1 - (j2 ^ s)
    imm = (s << 24) | (i1 << 23) | (i2 << 22) | ((h1 & 0x3FF) << 12) | ((h2 & 0x7FF) << 1)
    if s:
        imm -= 1 << 25
    pc = at + 4
    return (pc + imm) if h2 & 0x1000 else ((pc & ~3) + imm)


def thumb_blx(at, to):
    """Thumb BLX imm (to ARM): returns the two halfwords."""
    assert to % 4 == 0
    imm = to - ((at + 4) & ~3)
    assert -(1 << 24) <= imm < (1 << 24), 'blx out of range'
    imm &= (1 << 25) - 1
    s = (imm >> 24) & 1
    i1, i2 = (imm >> 23) & 1, (imm >> 22) & 1
    j1, j2 = (1 - i1) ^ s, (1 - i2) ^ s
    h1 = 0xF000 | (s << 10) | ((imm >> 12) & 0x3FF)
    h2 = 0xC000 | (j1 << 13) | (j2 << 11) | ((imm >> 2) & 0x3FF) << 1
    assert thumb_bl_target(h1, h2 & ~0x1000, at) == to
    return h1, h2


def veneer(entry_addr):
    return struct.pack('<II', 0xE51FF004, entry_addr)


def build(defines=()):
    return assemble(SRC, defines), symbols(SRC, defines)


def main():
    code, sym = build()
    rom = SEG0.read_bytes()
    sites = []
    for name, at, fw, entry in SITES:
        h1, h2 = struct.unpack_from('<HH', rom, at - B)
        if (h1 & 0xF800) != 0xF000 or (h2 & 0xD000) != 0xD000 or thumb_bl_target(h1, h2, at) != fw:
            raise SystemExit(f'{at:#x}: not `bl {fw:#x}`')
        sites.append({'name': name, 'address': f'{at:#X}', 'isa': 'Thumb',
                      'orig_halfwords': [f'{h1:04X}', f'{h2:04X}'],
                      'orig_word': f'{h1 | h2 << 16:08X}',
                      'orig_insn': f'bl {fw:#x}', 'orig_check': True,
                      'new_insn': f'blx <veneer.{name}> (Thumb -> ARM)',
                      'veneer_target': f'<body+{entry}> = +{sym[entry]}',
                      'power_off_restore': 'declare as a 4-byte section with orig_word'})
    (HERE / 'pagelru.bin').write_bytes(code)
    patch = {
        'firmware': f'Ver.5.02, out/seg0_c0000000.bin sha256 {hashlib.sha256(rom).hexdigest()[:16]}',
        'body': {'source': 'pagelru.S', 'file': 'pagelru.bin', 'bytes': len(code),
                 'sha256': hashlib.sha256(code).hexdigest(),
                 'isa': 'ARM, position independent, integer only', 'alignment': 8,
                 'entries': {k: sym[k] for k in ('pl_ctl', 'pl_load', 'pl_unload')},
                 'control': {'magic': 0, 'enable': 4, 'capacity': 8, 'count': 12, 'hits': 16,
                             'kept': 20, 'evictions': 24, 'bypass': 28, 'why': 32,
                             'flushed': 36, 'slots': 40},
                 'control_note': 'ships enable=0 (stock). capacity 0..4 (default 2). '
                                 'why: 1 disabled 2 recording 3 null 4 no tree 5 refcount!=1 '
                                 '6 QS_ layout 7 already held 8 capacity 0'},
        'veneers': {'bytes': 16, 'placement': 'cave.claim("pagelru.veneer", 16); within +-16 MiB '
                    'of C05DD5CA/C05DD670 (Thumb BLX range); cave arena C072E064..C072EFB4 is',
                    'layout': [{'name': 'load', 'offset': 0, 'words': ['E51FF004', '<body+pl_load>']},
                               {'name': 'unload', 'offset': 8, 'words': ['E51FF004', '<body+pl_unload>']}]},
        'sites': sites,
        'arm_order': ['write body + veneers, read back', 'C000E91C() then C000EABC()',
                      'patch unload site first, then load site (each: write, read back, '
                      'C000E91C + C000EABC)', 'set enable=1 last (data word)'],
        'disarm_order': ['set enable=0: the next screen switch releases every held layout',
                         'then restore both sites (load site last), C000E91C + C000EABC',
                         'keep body until reboot'],
        'firmware_calls_from_body': ['C05D90F0 load (Thumb)', 'C05D91A0 unload (Thumb)',
                                     'C00178D8 system status (ARM), byte +0x9C = is_recording'],
        'reads': ['[L+8] layout name', '[L+0xC] tree', '[tree+0xC] tree refcount'],
        'conflicts_to_check': 'nobody else may patch C05DD5CA / C05DD670; sups hooking C05D90F0/'
                              'C05D91A0 entry (uishare/OG) still run: we call those functions, '
                              'not around them',
    }
    (HERE / 'patch.json').write_text(json.dumps(patch, indent=1) + '\n')
    print(len(code), 'bytes', hashlib.sha256(code).hexdigest()[:16])


if __name__ == '__main__':
    main()
