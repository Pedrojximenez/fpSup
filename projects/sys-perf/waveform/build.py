"""Build waveform.bin and patch.json.

    python3 -B build.py

waveform.bin is position-independent ARM code (8-byte alignment is enough).
patch.json lists the three vtable slots that hold the stock waveform method
C05A3728; each is a DATA word (function pointer), so the patch itself needs
no I-cache work.  The code block needs C000E91C -> C000EABC before first use.
"""
import hashlib, json, pathlib, struct, sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'fpSup' / 'fp_usb_shell'))
from armasm import assemble, symbols  # noqa: E402

SRC = HERE / 'waveform.S'
SEG0 = ROOT / 'out' / 'seg0_c0000000.bin'
B = 0xC0000000
VERSION = 1
STOCK = 0xC05A3728
SLOTS = [  # (address, stock value, symbol, what)
    (0xC2DF8F4C, STOCK, 'wf_method', 'waveform drawer vtable 1 (LCD?)'),
    (0xC2DF8FE4, STOCK, 'wf_method', 'waveform drawer vtable 2'),
    (0xC2DF9220, STOCK, 'wf_method', 'waveform drawer vtable 3'),
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
    (HERE / 'waveform.bin').write_bytes(code)
    ctl = sym['wf_ctl']
    patch = {
        'version': VERSION,
        'code': 'waveform.bin',
        'code_size': len(code),
        'code_sha256': hashlib.sha256(code).hexdigest(),
        'code_isa': 'ARM (entry addresses even, no Thumb bit)',
        'alignment': 8,
        'symbols': {k: v for k, v in sym.items() if not k.startswith('$')},
        'control': {'base': f'load_base + {ctl:#x}', '+0': "'WAVE'", '+4': 'enable (ships 1; 0 = stock)',
                    '+8': 'fast calls', '+12': 'fallbacks (V outside 1..256 or H > 330)'},
        'publish_before_arm': ['C000E91C (D-cache clean+inv)', 'C000EABC (I-cache inv)'],
        'patches': [
            {'addr': f'{a:#010x}', 'stock': f'{s:#010x}', 'new': f'load_base + {sym[n]:#x}',
             'symbol': n, 'kind': 'data word (function pointer)', 'what': w}
            for a, s, n, w in SLOTS],
        'calling_convention': 'stock method: r0 this, r1 draw ctx, r2 image descriptor; '
                              'returns 0x528 like stock; called through the vtable',
        'calls': ['C0529D98 setup', 'C001510C memcpy', 'C0023030 addr map', 'C0529D10 point (per plot)',
                  'C05A3728 (fallback, tail call)'],
        'vfp': 's0-s3 / q0 only (d0-d1), same as stock; d16-d31 never touched',
        'stack': 'method 16+0x528 (= stock); sample 40 (stock 24); draw 36+2320 (stock 28+0x408); '
                 'sp parity at every callee equals stock',
        'context': 'DrawMgr task. Not interrupt-safe; not needed.',
        'assumption': 'thresholds [this+0x34..0x70] do not change while one frame is drawn '
                      '(level is memoised per call; stock re-reads them per plot)',
        'unpatch': 'write each stock value back; leave the code block allocated until power-off',
    }
    (HERE / 'patch.json').write_text(json.dumps(patch, indent=2) + '\n')
    print(f'waveform v{VERSION}: waveform.bin {len(code)} bytes, {len(SLOTS)} patch words, stock values match')


if __name__ == '__main__':
    main()
