#!/usr/bin/env python3
"""Build the Sensor Lab B2_5 installer blob: sl_menu_launch.S + the compiled C.

The C (sl_menu.c and fpSup/uishare/ui_pool.c, one translation unit with each
module's private names prefixed, as fpSup/lossless/build_card.py does) is
compiled freestanding Thumb, position independent, no relocations, and
appended to the launcher at c_base. The relocated variant runs in place as a
--late-boot-bin section after the core USER launcher; see sl_menu_launch.S.
Offline only.
"""
from __future__ import annotations

import pathlib
import re
import shutil
import struct
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SHELL = ROOT / 'fpSup/fp_usb_shell'
UISHARE = ROOT / 'fpSup/uishare'
sys.path[:0] = [str(SHELL), str(ROOT / 'research/ui/tools/arm_text'), str(HERE.parent)]
from armasm import assemble, symbols  # noqa: E402
import elf_text  # noqa: E402

LAUNCH = HERE / 'sl_menu_launch.S'
UNITS = [UISHARE / 'ui_pool.c', HERE / 'sl_menu.c', HERE / 'sl_modes.c']
HOOK_UNIT = HERE / 'sl_ui_hooks.c'
MARK = 0xC0730380                  # legacy plan address; relocated builds use core_offsets['mark']
SLMP_BYTES = 0x30000               # sl_b25_page.SLMP_BYTES
FILE_OBJECT = 0x1000               # sl_menu.c FILE_OBJECT
# the installer reads the block into area+FILE_OBJECT and needs the read to
# come up short of its room (else it cannot know it has all of it)
AREA_BYTES = FILE_OBJECT + SLMP_BYTES + 0x1000
CFLAGS = ['--target=armv7a-none-eabi', '-mcpu=cortex-a9', '-mthumb', '-mfloat-abi=soft',
          '-mfpu=none', '-ffreestanding', '-fno-builtin', '-nostdlib', '-fno-jump-tables',
          '-fropi', '-fno-addrsig', '-O2', '-std=c11', '-Wall', '-Wextra', '-Werror',
          '-Wno-unused-function']
CFLAGS_DYNAMIC = ['-Os' if flag == '-O2' else flag for flag in CFLAGS]




CORE_FIELDS = ('axis', 'gtab', 'flag', 'coltab', 'asptab', 'recipe',
               'ratetab', 'tmgtab', 'rate240', 'binfilt', 'mark', 'fmt_code', 'core_magic')


def plan_defines(core_offsets=None):
    """The mode tables' legacy addresses or the relocated core's offsets."""
    import imx410_plan as PL
    import imx410_block as K
    common = [f'-DSL_MAPPING_SLOT={PL.MAPPING + PL.PRIVATE_PROFILE * 4:#x}u',
              f'-DSL_NRATE={len(K.RATE_KEYS)}u', f'-DSL_LAB_FOCUS0={lab_focus0()}u']
    if core_offsets is not None:
        missing = set(CORE_FIELDS) - set(core_offsets)
        if missing:
            raise BuildError(f'missing relocated core offsets: {sorted(missing)}')
        if any(not isinstance(core_offsets[k], int) or core_offsets[k] < 0 or core_offsets[k] & 3
               for k in CORE_FIELDS):
            raise BuildError('relocated core offsets must be nonnegative aligned words')
        return common + ['-DSL_DYNAMIC_CORE=1'] + [f'-DSL_OFF_{k.upper()}={core_offsets[k]:#x}u'
                                                   for k in CORE_FIELDS]
    import imx410_rate_native as RN
    return common + [f'-DSL_AXIS={PL.AXIS:#x}u', f'-DSL_GTAB={PL.GTAB:#x}u', f'-DSL_FLAG=0xC0731C08u',
                     f'-DSL_COLTAB={PL.COLTAB:#x}u', f'-DSL_ASPTAB={PL.ASPTAB:#x}u',
                     f'-DSL_RECIPE={PL.RECIPE:#x}u', f'-DSL_RATETAB={PL.RATETAB:#x}u',
                     f'-DSL_TMGTAB={PL.TMGTAB:#x}u', f'-DSL_RATE240={RN.RATE240:#x}u', f'-DSL_MARK={MARK:#x}u',
                     f'-DSL_BINFILT={PL.BINFILT.BINFILT:#x}u']


def lab_focus0():
    import sl_lab_page as LAB
    return LAB.TAB_ITEM


class BuildError(RuntimeError):
    pass


PUBLIC = re.compile(r'^(?!typedef\b|static\b|extern\b|#|enum\b|union\b|struct\s+\w+\s*\{)'
                    r'((?:const\s+)?(?:struct\s+\w+|u?int\w*_t|void|uintptr_t)'
                    r'\s*\**\s*(?:sl_menu|uis)_\w+\s*\()', re.M)


def unity(tree: pathlib.Path, dynamic: bool = False, calc: bool = False) -> pathlib.Path:
    """Copies with every public function made internal (calls between the
    modules then need no relocation), one unit including them all, each
    module's private names prefixed -- fpSup/lossless/build_card.py unity()."""
    copies = []
    for src in UNITS + ([HOOK_UNIT] if dynamic and not calc else []) + [UISHARE / 'ui_pool.h',
                                                       UISHARE / 'ui_strings_code.h', HERE / 'sl_menu.h']:
        text = PUBLIC.sub(r'static \1', src.read_text())
        if src.name == 'sl_menu.c':           # the launcher's entry: keep it
            text = text.replace('static uint32_t sl_menu_install(struct sl_menu *m,',
                                'static __attribute__((used)) uint32_t sl_menu_install(struct sl_menu *m,', 1)
        if src.name == 'sl_modes.c':          # called through MARK+0x50 / +0x54 (sl_excl.S)
            text = text.replace('static uint32_t sl_menu_ui(struct sl_menu *m, uint32_t custom) {',
                                'static __attribute__((used)) uint32_t sl_menu_ui(struct sl_menu *m, uint32_t custom) {', 1)
            text = text.replace('static uint32_t sl_menu_live(struct sl_menu *m) {',
                                'static __attribute__((used)) uint32_t sl_menu_live(struct sl_menu *m) {', 1)
        if src.name == 'sl_ui_hooks.c':
            text = text.replace('static uint32_t sl_menu_arm(uintptr_t core_base,',
                                'static __attribute__((used)) uint32_t sl_menu_arm(uintptr_t core_base,', 1)
        (tree / src.name).write_text(text)
        if src.suffix == '.c':
            copies.append(tree / src.name)
    lines = ['/* generated by build_sl_menu.py */']
    for path in copies:
        text = path.read_text()
        private = sorted({s for s in re.findall(r'^(?:static|INLINE)\s[^(=;]*?\b(\w+)\s*\(', text, re.M)
                          if not s.startswith(('sl_menu_', 'uis_', '__'))})
        macros = sorted(set(re.findall(r'^\s*#\s*define\s+(\w+)', text, re.M)))
        lines += [f'#define {s} {path.stem}__{s}' for s in private]
        lines.append(f'#include "{path}"')
        lines += [f'#undef {s}' for s in private] + [f'#undef {m}' for m in macros]
    out = tree / 'unity.c'
    out.write_text('\n'.join(lines) + '\n')
    return out


def compile_c(tree, unit, extra='', core_offsets=None):
    source = unit
    if extra:
        source = tree / 'probe.c'
        source.write_text(unit.read_text() + extra)
    obj = tree / (source.stem + '.o')
    flags = CFLAGS_DYNAMIC if core_offsets is not None else CFLAGS
    r = subprocess.run([shutil.which('clang') or 'clang'] + flags +
                       plan_defines(core_offsets) + ['-c', '-I', str(tree), str(source), '-o', str(obj)],
                       capture_output=True, text=True)
    if r.returncode:
        raise BuildError('compile failed:\n' + r.stderr)
    return obj


def symbol_size(obj: pathlib.Path, name: str) -> int:
    d = obj.read_bytes()
    shoff, = struct.unpack_from('<I', d, 0x20)
    shentsize, shnum, _ = struct.unpack_from('<HHH', d, 0x2E)
    secs = [struct.unpack_from('<IIIIIIIIII', d, shoff + i * shentsize) for i in range(shnum)]
    symtab = next(s for s in secs if s[1] == 2)
    strtab = secs[symtab[6]]
    for i in range(symtab[5] // 16):
        n, _v, size, _info, _o, _s = struct.unpack_from('<IIIBBH', d, symtab[4] + 16 * i)
        if d[strtab[4] + n:d.index(b'\0', strtab[4] + n)].decode() == name:
            return size
    raise BuildError(f'{name} not in {obj.name}')


HOOK_KINDS = {'arm_b': 0, 'arm_bl': 1, 'thumb_bw': 2}


def validate_hook_plan(hooks, core_bytes, journal_gate_off, journal_max):
    """A complete, stock-word-checked late arm plan; returns numeric kinds."""
    import imx410_plan as PL
    import sl_excl as SLX
    expected = {site: 'arm_b' for site, _, _ in SLX.HOOKS + SLX.SETTER_HOOKS}
    expected[SLX.DNG_SITE] = 'arm_b'
    expected[SLX.GUI_SITE] = 'arm_bl'
    expected[SLX.PAGE_SITE] = 'thumb_bw'
    if not isinstance(core_bytes, int) or core_bytes <= 0 or core_bytes & 3:
        raise BuildError('USER core length must be a positive aligned byte count')
    if not isinstance(journal_gate_off, int) or journal_gate_off <= 0 or journal_gate_off >= core_bytes:
        raise BuildError('journal gate offset is outside the USER core')
    if not isinstance(journal_max, int) or not 1 <= journal_max <= 512:
        raise BuildError('invalid journal record bound')
    if not hooks or len(hooks) != len(expected) or {h[0] for h in hooks} != set(expected):
        raise BuildError('late UI hook plan must cover exactly ten sites')
    image = PL.FIRMWARE.read_bytes()
    out = []
    for site, stock, offset, kind in hooks:
        if kind != expected[site]:
            raise BuildError(f'late UI hook kind mismatch at {site:#x}')
        if stock != struct.unpack_from('<I', image, site - PL.B)[0]:
            raise BuildError(f'late UI hook {site:#x} does not carry the factory word')
        if not isinstance(offset, int) or offset <= 0 or offset & 3 or offset >= core_bytes:
            raise BuildError(f'late UI hook {site:#x} has invalid USER target')
        # CAVE_BUMP may be at either end of its arena when UI runs.  Ensure
        # each stock site reaches every possible eight-byte veneer position.
        for veneer in (0xC072E064, 0xC072EFB4 - 8):
            delta = veneer - site - (4 if kind == 'thumb_bw' else 8)
            limit = 1 << (24 if kind == 'thumb_bw' else 25)
            if delta & 3 or not -limit <= delta < limit:
                raise BuildError(f'late UI hook {site:#x} cannot reach CAVE_BUMP')
        out.append((site, stock, offset, HOOK_KINDS[kind]))
    return tuple(out)


def build_blob(slmp_bytes: int | None = None, *, core_offsets=None, core_bytes=None,
               ui_hooks=None, journal_gate_off=None, journal_max=None):
    """slmp_bytes: the largest SLMP block the installer must take (default
    SLMP_BYTES); the area it asks the allocator for grows with it."""
    if core_offsets is not None:
        ui_hooks = validate_hook_plan(ui_hooks, core_bytes, journal_gate_off, journal_max)
        bad = {key: off for key, off in core_offsets.items()
               if key in CORE_FIELDS and (not isinstance(off, int) or off < 0 or off >= core_bytes)}
        if bad:
            raise BuildError(f'USER core offsets outside image: {bad}')
    area_bytes = FILE_OBJECT + (slmp_bytes or SLMP_BYTES) + 0x1000
    with tempfile.TemporaryDirectory(prefix='sl-menu-') as t:
        tree = pathlib.Path(t)
        unit = unity(tree, dynamic=core_offsets is not None)
        text = elf_text.load_text(compile_c(tree, unit, core_offsets=core_offsets))
        install = text.functions.get('sl_menu_install')
        if install is None or not install & 1:
            raise BuildError('sl_menu_install missing or not Thumb')
        ui = text.functions.get('sl_menu_ui')
        live = text.functions.get('sl_menu_live')
        if ui is None or not ui & 1 or live is None or not live & 1:
            raise BuildError('sl_menu_ui / sl_menu_live missing or not Thumb')
        arm = text.functions.get('sl_menu_arm') if core_offsets is not None else None
        if core_offsets is not None and (arm is None or not arm & 1):
            raise BuildError('sl_menu_arm missing or not Thumb')
        fields = ('nbr', 'nbr_len', 'reader', 'excl_rate', 'excl_bit', 'core_base')
        probed = compile_c(tree, unit, '\nchar sl_state_probe[sizeof(struct sl_menu)];\n' + ''.join(
            f'char sl_off_{f}[__builtin_offsetof(struct sl_menu, {f}) + 1];\n' for f in fields),
            core_offsets=core_offsets)
        state = symbol_size(probed, 'sl_state_probe')
        offs = {f: symbol_size(probed, f'sl_off_{f}') - 1 for f in fields}
    common = ([f'MARK={MARK:#x}'] if core_offsets is None else
              ['CORE_DYNAMIC=1', f"OFF_MARK={core_offsets['mark']:#x}",
               f"OFF_FMT_CODE={core_offsets['fmt_code']:#x}",
               f"OFF_CORE_MAGIC={core_offsets['core_magic']:#x}"])
    if core_offsets is not None:
        common += [f'OFF_JOURNAL_GATE={journal_gate_off:#x}',
                   f'JOURNAL_MAX={journal_max}']
        for i, (site, stock, offset, kind) in enumerate(ui_hooks):
            common += [f'HOOK{i}_SITE={site:#x}', f'HOOK{i}_STOCK={stock:#x}',
                       f'HOOK{i}_OFFSET={offset:#x}', f'HOOK{i}_KIND={kind}']
    common += [f"OFF_CORE_BASE={offs['core_base']}", f"OFF_NBR={offs['nbr']}", f"OFF_NBRLEN={offs['nbr_len']}",
              f"OFF_READER={offs['reader']}", f"OFF_EXCLRATE={offs['excl_rate']}",
              f"OFF_EXCLBIT={offs['excl_bit']}"]
    probe = ['BLOB_LEN=0x4', 'BLOCK_BYTES=0x4', 'STATE_OFF=0x4', 'AREA_OFF=0x4', 'AREA_BYTES=0x4',
             'OFF_INSTALL=0x1', 'OFF_UI=0x1', 'OFF_LIVE=0x1', 'OFF_ARM=0x1'] + common
    c_base = symbols(LAUNCH, probe)['c_base']
    blob_len = c_base + len(text.code)
    blob_len += -blob_len % 8
    state_off = (blob_len + 63) & ~63
    area_off = (state_off + state + 0xFF) & ~0xFF
    block = (area_off + area_bytes + 0xFFF) & ~0xFFF
    defines = [f'BLOB_LEN={blob_len:#x}', f'BLOCK_BYTES={block:#x}', f'STATE_OFF={state_off:#x}',
               f'AREA_OFF={area_off:#x}', f'AREA_BYTES={block - area_off:#x}',
               f'OFF_INSTALL={install:#x}', f'OFF_UI={ui:#x}', f'OFF_LIVE={live:#x}',
               f'OFF_ARM={arm:#x}' if arm is not None else 'OFF_ARM=0x1'] + common
    launcher = assemble(LAUNCH, defines)
    if symbols(LAUNCH, defines)['c_base'] != c_base or len(launcher) < c_base:
        raise BuildError('sl_menu_launch.S moved between passes')
    blob = launcher[:c_base] + text.code
    blob += b'\0' * (blob_len - len(blob))
    return blob, dict(c_base=c_base, c_text=len(text.code), blob_len=blob_len, state_off=state_off,
                      state_bytes=state, area_off=area_off, area_bytes=block - area_off,
                      block_bytes=block, install=install, ui=ui, live=live, arm=arm,
                      mark=MARK if core_offsets is None else core_offsets['mark'],
                      core_offsets=core_offsets, offsets=offs, defines=defines)


if __name__ == '__main__':
    import json
    blob, facts = build_blob()
    if len(sys.argv) > 1:
        pathlib.Path(sys.argv[1]).write_bytes(blob)
    print(json.dumps({k: v for k, v in facts.items() if k != 'defines'}, indent=1))
