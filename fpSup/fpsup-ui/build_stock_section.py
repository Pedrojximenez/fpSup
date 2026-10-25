#!/usr/bin/env python3
"""An FPUI block as a ready section for a v4 sup written in assembly.

    from build_stock_section import section
    blob, info = section(fpui_bytes)

uishare/build_section.py's shape -- [uishare/section.S][compiled C][the block]
-- with fpui_stock.c in place of ui_pool.c + ui_apply.c.  info['uia_apply'] is
fpui_stock_apply_plain's offset: uia_apply's signature, (block, bytes,
&outcome), no service table, so only for a block whose strings are all stock
or names (refused here otherwise); a C sup calls fpui_stock_apply(svc, ...).
info['sites']: the firmware words the block changes at run time (the
file-redirect site, when it hooks it), to claim SHARED_UI with their stock
words.  Never the string sites: under loader v4 they are the core's.
"""
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
FPSUP = HERE.parent
ROOT = FPSUP.parent
UISHARE = FPSUP / 'uishare'
sys.path.insert(0, str(FPSUP / 'fp_usb_shell'))
sys.path.insert(0, str(ROOT / 'research' / 'ui' / 'tools' / 'arm_text'))
sys.path.insert(0, str(UISHARE))

import build_section as US                               # noqa: E402  (CFLAGS, section.S)


class SectionError(RuntimeError):
    pass


def compile_text(tmp):
    import elf_text
    unit = tmp / 'unity.c'
    unit.write_text('#include "fpui_stock.c"\n'
                    'void *fpui_section_keep(void) { return (void *)fpui_stock_apply_plain; }\n')
    obj = tmp / 'unity.o'
    clang = shutil.which('clang') or 'clang'
    r = subprocess.run([clang] + US.CFLAGS + ['-c', '-I', str(HERE), '-I', str(FPSUP / 'loader-v4'),
                        str(unit), '-o', str(obj)], capture_output=True, text=True)
    if r.returncode:
        raise SectionError('compile failed:\n' + r.stderr)
    text = elf_text.load_text(obj)
    fn = text.functions.get('fpui_stock_apply_plain', 0)
    if not fn & 1:
        raise SectionError('fpui_stock_apply_plain missing or not Thumb')
    return text


def sites(block):
    from ui import fpui
    strings, ops, _ = fpui.decode(block)
    if any(at != fpui.NAME and at == fpui.NOT_STOCK for _, at in strings):
        raise SectionError('a private string needs fpui_stock_apply(svc, ...) and a cached block')
    return sorted({(a[0], a[1]) for code, a in ops if code == fpui.OP_HOOK_FV})


def section(block):
    from armasm import assemble, symbols
    with tempfile.TemporaryDirectory(prefix='fpuisec-') as t:
        text = compile_text(pathlib.Path(t))
    src = UISHARE / 'section.S'
    c_base = symbols(src, ['BLOCK_OFF=0', 'BLOCK_LEN=0', 'OFF_APPLY=1'])['c_base']
    code_len = c_base + len(text.code)
    block_off = (code_len + 3) & ~3
    apply_off = c_base + text.functions['fpui_stock_apply_plain']
    defines = [f'BLOCK_OFF={block_off}', f'BLOCK_LEN={len(block)}', f'OFF_APPLY={apply_off}']
    stub = assemble(src, defines)
    if symbols(src, defines)['c_base'] != c_base or len(stub) != c_base:
        raise SectionError('the entry moved when the offsets went in')
    blob = stub + text.code + b'\0' * (block_off - code_len) + block
    blob += b'\0' * (-len(blob) % 4)
    return blob, {'c_base': c_base, 'c_text': len(text.code), 'block_off': block_off,
                  'block_len': len(block), 'bytes': len(blob), 'sites': sites(block),
                  'uia_apply': apply_off}
