"""Build lz4fast.bin and patch.json.

    python3 -B build.py

lz4fast.bin is position-independent ARM code (8-byte alignment is enough).
One code word changes: the only call to the stock block decoder, the
`bl C05A7630` at C05A7EE0, is pointed at an 8-byte veneer
(`ldr pc,[pc,#-4]; .word lz_block`) that must sit within +-32 MiB of it.
"""
import hashlib, json, pathlib, struct, sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'fpSup' / 'fp_usb_shell'))
from armasm import assemble, symbols  # noqa: E402

SRC = HERE / 'lz4fast.S'
SEG0 = ROOT / 'out' / 'seg0_c0000000.bin'
B = 0xC0000000
SITE = 0xC05A7EE0
STOCK_FN = 0xC05A7630


def bl(at, to):
    d = to - at - 8
    assert d % 4 == 0 and -(1 << 25) <= d < (1 << 25), 'bl out of range'
    return 0xEB000000 | ((d >> 2) & 0xFFFFFF)


def main():
    code = assemble(SRC)
    sym = symbols(SRC)
    rom = SEG0.read_bytes()
    seg_sha = hashlib.sha256(rom).hexdigest()
    orig = struct.unpack_from('<I', rom, SITE - B)[0]
    if orig != bl(SITE, STOCK_FN):
        raise SystemExit(f'{SITE:#x}: image has {orig:#x}, not bl {STOCK_FN:#x}')
    if struct.unpack_from('<I', rom, STOCK_FN - B)[0] != 0xE92D4DF0:
        raise SystemExit('stock decoder prologue changed')
    (HERE / 'lz4fast.bin').write_bytes(code)
    patch = {
        'firmware': f'Ver.5.02, out/seg0_c0000000.bin sha256 {seg_sha[:16]}',
        'body': {
            'source': 'lz4fast.S',
            'file': 'lz4fast.bin',
            'bytes': len(code),
            'sha256': hashlib.sha256(code).hexdigest(),
            'isa': 'ARM, position independent, integer only (no VFP/NEON)',
            'alignment': 8,
            'entries': {'lz_block': sym['lz_block']},
            'control': {'enable': 0, 'calls': 4, 'out_bytes': 8},
            'control_note': 'enable=0 makes lz_block jump straight to the stock C05A7630 '
                            '(same args, nothing touched); calls/out_bytes are statistics',
        },
        'veneers': {
            'bytes': 8,
            'placement': 'cave.claim("lz4fast.veneer", 8); must be within +-32 MiB of '
                         'C05A7EE0 (cave arena C072E064..C072EFB4 is)',
            'layout': [{'name': 'decode', 'offset': 0, 'words': ['E51FF004', '<body+lz_block>']}],
        },
        'sites': [{
            'name': 'decode',
            'address': f'{SITE:#010X}',
            'isa': 'ARM',
            'orig_word': f'{orig:08X}',
            'orig_insn': f'bl {STOCK_FN:#x}',
            'orig_check': True,
            'new_insn': 'bl <veneer+0>',
            'only_caller': 'C05A7630 has exactly one caller (this bl) and no pointer references',
            'regs_relied_on': 'none beyond the stock ABI (r0 ctx, r1 out stream, r2 in stream, r3 FLG ptr)',
            'power_off_restore': 'declare as a 4-byte section with orig_word (SUP_BUILD_RULES §4)',
        }],
        'arm_order': [
            'write body + veneer, read back',
            'C000E91C() then C000EABC()',
            'patch site (write, read back, C000E91C + C000EABC)',
        ],
        'disarm_order': [
            'restore site word, C000E91C + C000EABC',
            'or just set enable=0 (data word, takes effect on the next call)',
            'keep body until reboot (a decode may be inside it)',
        ],
        'firmware_calls_from_body': ['tail jump to C05A7630 when disabled'],
        'conflicts_to_check': 'nobody else may patch C05A7EE0 or C05A7630 (integration line checks)',
    }
    (HERE / 'patch.json').write_text(json.dumps(patch, indent=1) + '\n')
    print(f'lz4fast.bin {len(code)} bytes, lz_block at +{sym["lz_block"]:#x}, site {SITE:#x} orig {orig:#010x}')


if __name__ == '__main__':
    main()
