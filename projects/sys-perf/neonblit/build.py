"""Build neonblit.bin and patch.json.

    python3 -B build.py

neonblit.bin is position-independent ARM code (load it anywhere the allocator
gives; 8-byte alignment is enough).  patch.json lists every firmware word to
change, its stock value (checked here against out/seg0_c0000000.bin) and the
symbol whose run-time address replaces it.  All patched words are DATA
(function-pointer slots), so no I-cache work is needed for the patch itself;
the code block still needs the usual C000E91C -> C000EABC before first use.
"""
import hashlib, json, pathlib, struct, sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'fpSup' / 'fp_usb_shell'))
from armasm import assemble, symbols  # noqa: E402

SRC = HERE / 'neonblit.S'
SEG0 = ROOT / 'out' / 'seg0_c0000000.bin'
B = 0xC0000000
VERSION = 2              # 2: + idx 7 (ARGB4444 source, timecode glyphs)

TBL1 = 0xC2EB3F5C          # driver 6 (ARGB4444 dest) span table 1 = 1:1 path
SLOTS = [
    # (address, stock value, symbol, what)
    (TBL1 + 0 * 4, 0xC06FB9A9, 'nb_p32_blend', 'idx0 RGBA8888-pre source-over (fmt 0x10021, 0x10028...)'),
    (TBL1 + 1 * 4, 0xC06FBBA9, 'nb_p32_opaque', 'idx1 RGBA8888 opaque (fmt 0x10022; opaque runs of 0x10021)'),
    (TBL1 + 2 * 4, 0xC06FC039, 'nb_565_opaque', 'idx2 RGB565 (fmt 0x10013)'),
    (TBL1 + 3 * 4, 0xC06FBC09, 'nb_lut8_blend', 'idx3 8bpp LUT (fmt 0x1000C)'),
    (TBL1 + 6 * 4, 0xC06FBC09, 'nb_lut8_blend', 'idx6 8bpp LUT (fmt 0x1000F)'),
    (TBL1 + 7 * 4, 0xC06FBCD9, 'nb_a4_blend', 'idx7 ARGB4444 source-over (fmt 0x10011; font_M_* glyphs)'),
    (TBL1 + 11 * 4, 0xC06FBC09, 'nb_lut8_blend', 'idx11 LUT, colour transform'),
    (TBL1 + 12 * 4, 0xC06FBC09, 'nb_lut8_blend', 'idx12 LUT, colour transform'),
    (TBL1 + 13 * 4, 0xC06FBC09, 'nb_lut8_blend', 'idx13 LUT, colour transform'),
    (TBL1 + 14 * 4, 0xC06FBC09, 'nb_lut8_blend', 'idx14 LUT, colour transform'),
    (0xC2E38E7C, 0xC0721480, 'nb_layer_fill', 'layer vtable fill slot (vtable A)'),
    (0xC2EF62A0, 0xC0721480, 'nb_layer_fill', 'layer vtable fill slot (vtable B)'),
]


def main():
    code = assemble(SRC)
    sym = symbols(SRC)
    rom = SEG0.read_bytes()
    for addr, stock, name, _ in SLOTS:
        got = struct.unpack_from('<I', rom, addr - B)[0]
        if got != stock:
            raise SystemExit(f'{addr:#x}: image has {got:#x}, expected {stock:#x}')
        if name not in sym:
            raise SystemExit(f'missing symbol {name}')
    (HERE / 'neonblit.bin').write_bytes(code)
    patch = {
        'version': VERSION,
        'code': 'neonblit.bin',
        'code_size': len(code),
        'code_sha256': hashlib.sha256(code).hexdigest(),
        'code_isa': 'ARM (entry addresses even, no Thumb bit)',
        'alignment': 8,
        'symbols': {k: v for k, v in sym.items() if not k.startswith('$')},
        'publish_before_arm': ['C000E91C (D-cache clean+inv)', 'C000EABC (I-cache inv)'],
        'patches': [
            {'addr': f'{a:#010x}', 'stock': f'{s:#010x}', 'new': f'load_base + {sym[n]:#x}',
             'symbol': n, 'kind': 'data word (function pointer)', 'what': w}
            for a, s, n, w in SLOTS],
        'calling_convention': 'stock span: r0 dst row, r1 src desc ([+0x24] ptr, [+0x1c] stride), '
                              'r2 width, r3 params ([+4] LUT, [+8] dst stride, [+0xc] rows); '
                              'fill: r0 layer, r1 value; called with blx from Thumb/ARM',
        'vfp': 'uses d0-d13 only; saves d8-d13; TK-OS saves d0-d15+FPSCR per task and per IRQ '
               '(C0000D24 / C0000E78) and never d16-d31, so d16-d31 are never touched',
        'context': 'DrawMgr task (DrawThread -> UIC). Not interrupt-safe by design; not needed.',
        'unpatch': 'write each stock value back; do not free the code block while a draw may be '
                   'inside it (leave it allocated until power-off)',
    }
    (HERE / 'patch.json').write_text(json.dumps(patch, indent=2) + '\n')
    print(f'neonblit v{VERSION}: neonblit.bin {len(code)} bytes, {len(SLOTS)} patch words, all stock values match the image')


if __name__ == '__main__':
    main()
