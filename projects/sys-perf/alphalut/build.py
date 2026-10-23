"""Build alphalut.bin and patch.json.

    python3 -B build.py

alphalut.bin is position-independent ARM code (8-byte alignment).  The patch
is one CODE word: the `bl C0563BA8` at C0561734 (the only caller) becomes a
`bl` to an 8-byte veneer `ldr pc,[pc,#-4]; .word al_unpremul`, so the veneer
must sit within +-32 MiB of C0561734 (the cave arena C072E064..C072EFB4 does).
"""
import hashlib, json, pathlib, struct, sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'fpSup' / 'fp_usb_shell'))
from armasm import assemble, symbols  # noqa: E402

SRC = HERE / 'alphalut.S'
SEG0 = ROOT / 'out' / 'seg0_c0000000.bin'
B = 0xC0000000
CALLSITE = 0xC0561734
STOCK_FN = 0xC0563BA8
TBL = 0xC0D0D684
K = [0, 3840, 1920, 1280, 960, 768, 640, 549, 480, 427, 384, 350, 320, 296, 275, 256]


def bl(frm, to):
    return 0xEB000000 | (((to - (frm + 8)) >> 2) & 0xFFFFFF)


def main():
    rom = SEG0.read_bytes()
    word = struct.unpack_from('<I', rom, CALLSITE - B)[0]
    if word != bl(CALLSITE, STOCK_FN):
        raise SystemExit(f'{CALLSITE:#x}: {word:#010x} is not bl {STOCK_FN:#x}')
    tbl = rom[TBL - B:TBL - B + 256]
    if not all(tbl[a * 16 + c] == min(15, (c * K[a]) >> 8) for a in range(16) for c in range(16)):
        raise SystemExit('K does not reproduce the image table')
    code = assemble(SRC)
    sym = symbols(SRC)
    if code[0x20:0x40] != bytes(k & 0xFF for k in K) + bytes(k >> 8 for k in K):
        raise SystemExit('ktab in alphalut.S does not match K')
    (HERE / 'alphalut.bin').write_bytes(code)
    patch = {
        'version': 1,
        'code': 'alphalut.bin',
        'code_size': len(code),
        'code_sha256': hashlib.sha256(code).hexdigest(),
        'code_isa': 'ARM',
        'alignment': 8,
        'symbols': {k: v for k, v in sym.items() if k in ('al_ctl', 'al_unpremul')},
        'control': {'+00': "'ALUT'", '+04': 'version', '+08': 'enable (default 1; 0 = stock)',
                    '+0C': 'calls', '+10': 'NEON 8-px blocks', '+14': 'all-zero blocks skipped',
                    '+18': 'fallbacks to stock (w<=0, h<=0, or disabled)'},
        'publish_before_arm': ['C000E91C (D-cache clean+inv)', 'C000EABC (I-cache inv)'],
        'veneer': {'size': 8, 'words': ['0xE51FF004 (ldr pc,[pc,#-4])', 'load_base + al_unpremul'],
                   'range': f'within +-32 MiB of {CALLSITE:#x}'},
        'patches': [{
            'addr': f'{CALLSITE:#010x}', 'stock': f'{word:#010x}',
            'new': 'bl veneer (0xEB000000 | ((veneer - (0xC0561734 + 8)) >> 2 & 0xFFFFFF))',
            'kind': 'code word (ARM bl); needs D-clean + I-inv after writing',
            'what': 'UIC drawer C0561198: un-premultiply of the round\'s dirty-rect union',
        }],
        'callers_of_stock': ['C0561734 (only one; scan of ARM BL, Thumb BL/BLX and literal pointers)'],
        'sibling_not_patched': 'C0563D50 (premultiply, table C0D0D784, called once from C0560F08); '
                               'not hot in the profile',
        'calling_convention': 'r0 = layer buffer (u16), r1 = rect {x, y, w, h} (s32), r2 = stride (pixels)',
        'vfp': 'd0-d15 only; saves d8-d15; TK-OS saves d0-d15 + FPSCR per task/IRQ, never d16-d31',
        'context': 'DrawMgr task (DrawThread -> UIC drawer C0561198)',
        'unpatch': 'write the stock word back, D-clean + I-inv; keep the code block allocated',
    }
    (HERE / 'patch.json').write_text(json.dumps(patch, indent=2) + '\n')
    print(f'alphalut.bin {len(code)} B sha256 {patch["code_sha256"][:16]}; '
          f'call site {CALLSITE:#x} stock {word:#010x}; K matches the image table')


if __name__ == '__main__':
    main()
