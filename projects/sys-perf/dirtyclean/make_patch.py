"""Write patch.json: what an installer (or a v3 sup) must place, in order."""
import hashlib, json, pathlib, struct, sys
HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'fpSup' / 'fp_usb_shell'))
from armasm import assemble, symbols  # noqa: E402
SRC = HERE / 'dirtyclean.S'
rom = (ROOT / 'out' / 'seg0_c0000000.bin').read_bytes()
word = lambda a: struct.unpack_from('<I', rom, a - 0xC0000000)[0]
bl = lambda at, to: 0xEB000000 | (((to - (at + 8)) >> 2) & 0xFFFFFF)
code = assemble(SRC); sym = symbols(SRC)
sites = [('copy', 0xC0528AE0, 0xC0528BA0, 'dc_copy_hook', 'r6 = slot'),
         ('clear', 0xC05287F4, 0xC0528B40, 'dc_clear_hook', 'r5 = slot'),
         ('clean', 0xC0528954, 0xC000E91C, 'dc_clean', 'r4 = DrawController, [sp+0x18..0x1B] drew')]
out = {
  'firmware': 'Ver.5.02, out/seg0_c0000000.bin sha256 ' + hashlib.sha256(rom).hexdigest()[:16],
  'body': {'source': 'dirtyclean.S', 'bytes': len(code), 'sha256': hashlib.sha256(code).hexdigest(),
           'placement': 'own allocation (allocator class 0 or the v3 sup block); position independent; ARM',
           'entries': {k: sym[k] for k in ('dc_ctl', 'dc_clean', 'dc_clear_hook', 'dc_copy_hook')},
           'control': {'C_EN': 4, 'C_CLEAR': 8, 'C_COPY': 12, 'C_CALLS': 16, 'C_FAST': 20, 'C_FALL': 24,
                       'C_LINES': 28, 'C_WHY': 32, 'C_FULLS': 36},
           'init_before_arming': {'C_EN': 1, 'C_CLEAR': 0, 'C_COPY': 15}},
  'veneers': {'bytes': 24, 'placement': 'cave.claim("dirtyclean.veneers", 24); must be within +-32 MiB of '
              'C0528954 (cave arena C072E064..C072EFB4 is)',
              'layout': [{'name': n, 'offset': 8 * i, 'words': ['E51FF004', f'<body+{sym[e]:#x}>']}
                         for i, (n, _, _, e, _) in enumerate(sites)]},
  'sites': [{'name': n, 'address': f'{a:#010X}', 'isa': 'ARM', 'orig_word': f'{word(a):08X}',
             'orig_insn': f'bl {t:#010x}', 'orig_check': word(a) == bl(a, t),
             'new_insn': f'bl <veneer+{8 * i}>', 'regs_relied_on': note,
             'power_off_restore': 'declare as a 4-byte section with orig_word (SUP_BUILD_RULES §4)'}
            for i, (n, a, t, e, note) in enumerate(sites)],
  'arm_order': ['write body + veneers, read back', 'write control init (C_COPY=0xF)',
                'C000E91C() then C000EABC()', 'patch copy, clear, then clean site (each: write, read back, '
                'C000E91C + C000EABC)'],
  'disarm_order': ['restore clean site first, then clear and copy', 'C000E91C + C000EABC',
                   'keep body until reboot (DrawThread may be inside it)'],
  'firmware_calls_from_body': ['layer vtable +0x10 getBuffer (C0721328)', 'layer vtable +0x28 (C0721638)',
                               'C0721110 bytes(pixels, fmt)', 'tail: C000E91C / C0528B40 / C0528BA0'],
  'fixed_addresses_read': {'UIC manager records': '0xC37B7048 + 0x18 (UIC object = C055F0F0() = 0xC37B7034+0x14), 10 x 0x20 (+4 base, +8 x,y,w,h, +0x18 mode)',
                           'UIC drawer vptrs': ['0xC0D17780', '0xC2E45DF8'],
                           'SurfacePixel vptrs': ['0xC2EF6280', '0xC2E38E5C'],
                           'return site checked': '0xC0528958'},
  'filldma_interface': 'If a fill of a layer goes to the Fill DMA (projects/sys-perf/filldma): (1) clean+invalidate '
                       'the target range BEFORE starting the DMA; (2) reach it through C0528B40 (so dc_clear_hook '
                       'marks the slot) or set the slot bit in C_CLEAR yourself; dirtyclean then cleans the whole '
                       'back buffer for that slot, and never invalidates anything.',
}
assert all(s['orig_check'] for s in out['sites'])
(HERE / 'patch.json').write_text(json.dumps(out, indent=1, ensure_ascii=False))
print(len(code), 'bytes;', {k: hex(v) for k, v in out['body']['entries'].items()})
