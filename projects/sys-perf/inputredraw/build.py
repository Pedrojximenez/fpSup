"""Assemble inputredraw.S, check the firmware site, write inputredraw.bin + patch.json."""
import hashlib, json, pathlib, struct, sys
HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'fpSup' / 'fp_usb_shell'))
from armasm import assemble, symbols  # noqa: E402

SRC = HERE / 'inputredraw.S'
SITE, ORIG = 0xC06D1418, 0xC055E1E8
rom = (ROOT / 'out' / 'seg0_c0000000.bin').read_bytes()
word = lambda a: struct.unpack_from('<I', rom, a - 0xC0000000)[0]
bl = lambda at, to: 0xEB000000 | (((to - (at + 8)) >> 2) & 0xFFFFFF)


def main():
    code = assemble(SRC); sym = symbols(SRC)
    assert word(SITE) == bl(SITE, ORIG), 'site is not bl C055E1E8'
    assert rom[0xC2E45DB0 - 0xC0000000:][:12] == bytes([1, 1, 0, 0]) + b'\xff' * 4 + b'\0' * 4
    (HERE / 'inputredraw.bin').write_bytes(code)
    out = {
        'firmware': 'Ver.5.02, out/seg0_c0000000.bin sha256 ' + hashlib.sha256(rom).hexdigest()[:16],
        'changes_stock_behaviour': True,
        'body': {'source': 'inputredraw.S', 'bytes': len(code), 'sha256': hashlib.sha256(code).hexdigest(),
                 'placement': 'own allocation or the v3 sup block; position independent; ARM',
                 'entries': {'ir_base': sym['ir_base'], 'ir_enq_hook': sym['ir_enq_hook']},
                 'control': {'enable': 0x08, 'rec_ok': 0x0C, 'min_ms': 0x10, 'calls': 0x14, 'kicks': 0x18,
                             'preloads': 0x1C, 'skip_rec': 0x20, 'skip_pending': 0x24, 'last_ms': 0x28},
                 'defaults': {'enable': 1, 'rec_ok': 0, 'min_ms': 16}},
        'veneers': {'bytes': 8, 'placement': 'cave arena (within +-32 MiB of C06D1418)',
                    'words': ['E51FF004', f'<body+{sym["ir_enq_hook"]:#x}>']},
        'sites': [{'name': 'gui_key_enqueue', 'address': f'{SITE:#010X}', 'isa': 'ARM',
                   'orig_word': f'{word(SITE):08X}', 'orig_insn': f'bl {ORIG:#010x}',
                   'new_insn': 'bl <veneer>', 'caller': 'UicContentsIfBase::v1 C06D13A0 (every key, down and up)',
                   'regs_relied_on': 'none after the call (caller tests r6 next); r0/r1 passed through',
                   'power_off_restore': 'declare as a 4-byte section with orig_word (SUP_BUILD_RULES §4)'}],
        'firmware_calls_from_body': ['C055E1E8 enqueue (first, unchanged)', 'C00178D8 sysstat (+0x9C recording)',
                                     'C05278F8 DrawMgr', 'C0527F30 force pending?', 'C0527E68 ReqForceDraw'],
        'fixed_addresses': {'current_time_ms': '0xC301EAE4', 'CYC_DRAW counters': '0xC3782F98 (+0,+4 cnt; +8,+C div)'},
        'arm_order': ['write body + veneer, read back', 'C000E91C then C000EABC',
                      'patch C06D1418, read back, C000E91C + C000EABC'],
        'disarm': 'enable=0 (stock path from the next key); or write orig_word back + cache maintenance',
    }
    (HERE / 'patch.json').write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(len(code), 'bytes', out['body']['sha256'][:16], {k: hex(v) for k, v in out['body']['entries'].items()})


if __name__ == '__main__':
    main()
