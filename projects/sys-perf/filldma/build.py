"""Assemble filldma.S, check every firmware word it depends on against the
image, and write filldma.bin + patch.json.   python3 -B build.py
"""
import hashlib, json, pathlib, struct, sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'fpSup' / 'fp_usb_shell'))
from armasm import assemble, symbols  # noqa: E402

SRC = HERE / 'filldma.S'
IMAGE = (ROOT / 'out' / 'MAIN_c0000000.bin').read_bytes()


def word(a):
    return struct.unpack_from('<I', IMAGE, a - 0xC0000000)[0]


# (address, expected first word, what) -- read back on the camera before enabling
FW_CHECKS = [
    (0xC00DB188, 0x4170E92D, 'Fill DMA driver C00DB188 (Thumb push.w)'),
    (0xC00DAFF8, 0x4FF0E92D, 'Fill DMA core C00DAFF8 (Thumb)'),
    (0xC00DB7E0, 0x4100E92D, 'Fill DMA IRQ 0x24 handler C00DB7E0 (sig_sem done)'),
    (0xC000EB28, 0xE10FC000, 'range invalidate C000EB28 (mrs ip, cpsr)'),
    (0xC00178D8, 0xE92D4010, 'system status object C00178D8'),
    (0xC0721328, 0xE92D4010, 'layer getBuffer (vt+0x10) C0721328'),
    (0xC0721CC8, 0xE1A0C000, 'back buffer read C0721CC8'),
    (0xC0698C08, 0xE1A0C000, 'layer valid (vt+0x30) C0698C08, returns 1'),
    (0xC0721F98, 0xE1A0C000, 'layer valid (vt+0x30) C0721F98, returns 1'),
    (0xC0721480, 0xE92D40F0, 'stock layer fill C0721480'),
    (0xC0722490, 0xE92D44F0, 'stock 16bpp whole-buffer fill C0722490'),
]
VTABLE_SLOTS = [(0xC2E38E7C, 'DisplayOsdLayer_ARGB_Idx256 vt 0xC2E38E5C +0x20'),
                (0xC2EF62A0, 'DisplayOsdFrameBufferCore vt 0xC2EF6280 +0x20')]


def main():
    code = assemble(SRC)
    sym = symbols(SRC)
    bad = [(hex(a), hex(word(a)), hex(v), w) for a, v, w in FW_CHECKS if word(a) != v]
    for a, _ in VTABLE_SLOTS:
        if word(a) != 0xC0721480:
            bad.append((hex(a), hex(word(a)), '0xc0721480', 'vtable fill slot'))
    if bad:
        raise SystemExit(f'image differs: {bad}')
    assert struct.unpack_from('<I', code, 0)[0] == 0x414D4446
    assert sym['fd_layer_fill'] == 0x40
    (HERE / 'filldma.bin').write_bytes(code)
    hdr = {k: hex(sym[k]) for k in ('fd_enable', 'fd_thresh', 'fd_rec_ok', 'fd_calls', 'fd_dma_ok',
                                    'fd_dma_bytes', 'fd_declined', 'fd_cpu_done', 'fd_last_code',
                                    'fd_last_base', 'fd_last_size')}
    out = {
        'name': 'filldma',
        'image_sha256': hashlib.sha256(IMAGE).hexdigest(),
        'bin': 'filldma.bin',
        'bin_size': len(code),
        'bin_sha256': hashlib.sha256(code).hexdigest(),
        'load': 'any 8-byte aligned block (position independent); C000E91C then C000EABC before first call',
        'entry': {'offset': hex(sym['fd_layer_fill']), 'mode': 'ARM',
                  'args': 'r0 = layer, r1 = value (same as C0721480)',
                  'returns': '0 = filled; non-zero = not taken, nothing written, no cache op '
                             '(1 disabled, 2 not 16bpp, 3 invalid, 4 small, 5 driver not inited, '
                             '6 align/range, 7 recording)',
                  'context': 'task only (it sleeps on the driver semaphores); never from IRQ/cyclic',
                  'clobbers': 'r0-r3, ip (AAPCS); no VFP/NEON'},
        'header': hdr,
        'tunables': {'fd_enable': 1, 'fd_thresh': 0x4000, 'fd_rec_ok': 0},
        'patches': [],
        'vtable_slots_owned_by_dispatcher': [
            {'addr': hex(a), 'orig': '0xc0721480', 'what': w,
             'note': 'NOT written by filldma; the sys-perf dispatcher owns these and calls fd_layer_fill'}
            for a, w in VTABLE_SLOTS],
        'fw_checks': [{'addr': hex(a), 'word': hex(v), 'what': w} for a, v, w in FW_CHECKS],
        'runtime_checks': [
            {'addr': '0xc31d25b4', 'expect': 1, 'what': 'driver initialised at boot (C00DBC80 via LCD init C0308078)'},
            {'addr': '0xc301fec4', 'expect': 'non-zero', 'what': 'driver mutex semaphore id'},
            {'addr': '0xc301fec0', 'expect': 'non-zero', 'what': 'driver done semaphore id'},
        ],
    }
    (HERE / 'patch.json').write_text(json.dumps(out, indent=1) + '\n')
    print(f'filldma.bin {len(code)} B, entry +{sym["fd_layer_fill"]:#x}; {len(FW_CHECKS)} firmware words match')


if __name__ == '__main__':
    main()
