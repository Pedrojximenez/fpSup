#!/usr/bin/env python3
"""Build Gyro2 as a loader v3 sup.

    python3 -B build.py            -> build/40GYR2.BIN

Uses fpSup's v3 helpers read-only (make_sup, the reference image) and its
assembler; nothing in fpSup is written.
"""
import pathlib, re, struct, sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
V3 = ROOT / 'fpSup' / 'fp_usb_shell' / 'v3'
sys.path.insert(0, str(V3))
sys.path.insert(0, str(V3.parent))

import build_v3 as B                       # noqa: E402
from armasm import assemble, symbols       # noqa: E402

SRC = HERE / 'src' / 'gyr2.S'
OUT = HERE / 'build' / '40GYR2.BIN'
SUP_ID = 'GYR2'
VERSION = 0x00000006                       # frames written from the tag observer, no DMA patch

ACCEL_SITE = 0xC050D4C8


class BuildError(RuntimeError):
    pass


def equ(name, src=SRC):
    m = re.search(rf'^\.equ\s+{name},\s*(0x[0-9A-Fa-f]+|\d+)', pathlib.Path(src).read_text(), re.M)
    if not m:
        raise BuildError(f'{name} not found in {SRC.name}')
    return int(m.group(1), 0)


def build(src=SRC):
    """(file bytes, info).  `src`: another copy of the source (mutation tests)."""
    code = assemble(src)
    image = B.IMAGE.read_bytes()
    # The header DMA (0xC038C77C) is not patched any more: the frames are
    # written from the firmware's own tag-observer notify.
    accel = struct.pack('<I', 0xE3A02000)
    if B.stock(ACCEL_SITE, 4, image) != accel:
        raise BuildError(f'the image has {B.stock(ACCEL_SITE, 4, image).hex()} at {ACCEL_SITE:#x}, not mov r2, #0')
    if equ('WRITER', src) != VERSION:
        raise BuildError('WRITER in the source is not the build VERSION')
    if equ('ACCEL_SITE', src) != ACCEL_SITE:
        raise BuildError('ACCEL_SITE in the source and the build disagree')
    # Position independence: no word in the code may point into the code as
    # if it sat at 0 -- armasm already refuses relocations other than local
    # bl and pc-relative ldr, so absolute self-pointers cannot be emitted.
    body = code
    # The gyro and level buffers sit past the file; the loader zeroes them.
    file_len = B.SL_HEADER_LEN + len(body)
    file_len += -file_len % 4
    try:
        bss = equ('GLOG_N', src) * 6 + equ('ELOG_N', src) * 12
        try:
            bss += equ('VLOG_N', src) * 8           # the Vd ring
            bss += equ('GTAG_MAX', src)            # zeros for the tag observer
        except BuildError:
            pass
    except BuildError:                       # an older stage (P0-P3): no buffers
        bss = None
    block = None if bss is None else file_len + 8 + bss   # + 8: gbuf is 8-aligned
    sup = B.make_sup(body, B.SL_HEADER_LEN, SUP_ID, version=VERSION, block_size=block)
    return sup, {'code': len(code), 'file': len(sup), 'block': block or len(sup)}


ROW4 = HERE / 'src' / 'gyr2_row4.c'
def v4_name():
    """The card file (fpSup/loader-v4/names_v4.py): Gyro2_v0.1.0.BIN."""
    sys.path.insert(0, str(ROOT / 'fpSup' / 'loader-v4'))
    import names_v4
    return names_v4.file_name('GYR2')


def row4_code():
    """(Thumb code, g2_install's offset | 1) of src/gyr2_row4.c, -fropi, no data."""
    import shutil, subprocess, tempfile
    fpsup = ROOT / 'fpSup'
    sys.path.insert(0, str(fpsup / 'uishare'))
    sys.path.insert(0, str(ROOT / 'research' / 'ui' / 'tools' / 'arm_text'))
    import build_section as US                 # noqa: E402
    import elf_text                            # noqa: E402
    with tempfile.TemporaryDirectory(prefix='g2row-') as t:
        o = pathlib.Path(t) / 'row.o'
        r = subprocess.run([shutil.which('clang') or 'clang'] + US.CFLAGS +
                           ['-c', '-I', str(fpsup / 'loader-v4'), str(ROW4), '-o', str(o)],
                           capture_output=True, text=True)
        if r.returncode:
            raise BuildError('gyr2_row4.c: ' + r.stderr)
        text = elf_text.load_text(o)
    fn = text.functions.get('g2_install', 0)
    if not fn & 1:
        raise BuildError('g2_install missing or not Thumb')
    return text.code, fn


def build_v4(src=SRC):
    """Gyro2 for Loader v4 with its fpSup-page row (-DGYR2_V4): (file bytes, info).
    The v3 build above is unchanged: every v4 line is under #ifdef GYR2_V4."""
    import tempfile
    sys.path.insert(0, str(ROOT / 'fpSup' / 'loader-v4'))
    import build_v4 as B4                      # noqa: E402
    code4, fn = row4_code()
    with tempfile.TemporaryDirectory(prefix='g2v4-') as t:
        blob = pathlib.Path(t) / 'row4.bin'
        blob.write_bytes(code4)
        defines = ['GYR2_V4', f'G2_BIN="{blob}"', f'G2_INSTALL={fn:#x}']
        code = assemble(src, defines=defines)
        syms = symbols(src, defines=defines)
    image = B.IMAGE.read_bytes()
    if B.stock(ACCEL_SITE, 4, image) != struct.pack('<I', 0xE3A02000):
        raise BuildError('the image does not have mov r2, #0 at the accel site')
    if equ('WRITER', src) != VERSION:
        raise BuildError('WRITER in the source is not the build VERSION')
    # The name is in the code (g2_name), not after it: gbuf starts where the
    # code ends, and the loader zeroes only from the file's end.
    file_len = B4.SL4_HEADER_LEN + len(code)
    if file_len % 8:
        raise BuildError('code does not end 8-aligned: gbuf would start inside the file')
    bss = (equ('GLOG_N', src) * 6 + equ('ELOG_N', src) * 12 + equ('VLOG_N', src) * 8 +
           equ('GTAG_MAX', src) + equ('G2_FOBJ_BYTES', src))
    sup = B4.make_sup(code, B4.SL4_HEADER_LEN, SUP_ID, version=VERSION, min_svc=B4.SL4_SVC_VERSION,
                      flags=B4.SL_F_CACHED_OK, block_size=file_len + 8 + bss)
    if len(sup) != file_len:
        raise BuildError(f'file length {len(sup)} != {file_len}: the BSS would start inside the file')
    name_off = B4.SL4_HEADER_LEN + syms['g2_name']
    if sup[name_off:name_off + 6] != b'Gyro2\0':
        raise BuildError('g2_name not where the symbol says')
    sup = sup[:44] + struct.pack('<I', name_off) + sup[48:]
    return sup, {'code': len(code), 'row4': len(code4), 'g2_install': fn, 'file': len(sup),
                 'block': struct.unpack_from('<I', sup, 12)[0]}


def main():
    import argparse, hashlib, json
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=pathlib.Path, help='write DIR/40GYR2.BIN and DIR/build.json (for fpSup/tools/release_v3.py)')
    ap.add_argument('--v4', action='store_true', help='Loader v4 with the fpSup-page row: DIR/GYR2.BIN')
    a = ap.parse_args()
    if a.v4:
        sup, info = build_v4()
        out = (a.out or OUT.parent) / v4_name()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(sup)
        print(f'{out}: {info}')
        return
    sup, info = build()
    out = a.out / OUT.name if a.out else OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(sup)
    if a.out:
        root = HERE.parents[1]
        sources = [HERE / 'build.py', SRC]
        (a.out / 'build.json').write_text(json.dumps({
            'product': 'fpSup-Gyro2, Loader v3 sup', 'file': OUT.name, 'sup_id': SUP_ID,
            'version': VERSION, 'sha256': hashlib.sha256(sup).hexdigest(), 'facts': info,
            'sources': {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        }, indent=1) + '\n')
    print(f'{out}: {info["file"]} bytes (code {info["code"]}), block {info["block"]}')


if __name__ == '__main__':
    main()
