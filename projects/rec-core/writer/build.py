#!/usr/bin/env python3
"""ULWR (Unlocked Writer) -- the rec-core writer (O2 + O3) as a Loader v3 sup.

    python3 -B build.py [--out DIR] -> build/20ULWR.BIN, build/build.json (or DIR/)

[header][patch_sup: claim C063F140 + C063F220 + C03A549C][wr_card.S inner][C text][...]
                                                         block: [state wr_t]
bq.c + wr.c + wr_card.c are one unit, every function static (the wr_ entries
`used`), compiled -fropi Thumb and loaded by elf_text, which refuses any
relocation or writable data: the text runs wherever the block lands.
"""
import hashlib, json, pathlib, re, shutil, struct, subprocess, sys, tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
V3 = ROOT / 'fpSup' / 'fp_usb_shell' / 'v3'
sys.path[:0] = [str(V3), str(V3.parent), str(ROOT / 'research/ui/tools/arm_text')]
import build_v3 as B                         # noqa: E402  (read-only use)
from armasm import assemble, symbols         # noqa: E402
import elf_text                              # noqa: E402

SUP_ID, VERSION = 'ULWR', 1
OUT = HERE / 'build' / '20ULWR.BIN'
SL_EXCL = 2
SITES = {0xC063F140: '2de9f04584b00446', 0xC063F220: '2de9f04107460d46',
         0xC03A549C: '0d30dbe5000053e3'}
ENTRIES = {'OFF_INIT': 'wr_card_init', 'OFF_SEND': 'wr_send', 'OFF_INSTALLED': 'wr_installed',
           'OFF_COOKIE': 'wr_cb_cookie', 'OFF_ACQ': 'wr_cb_acquire', 'OFF_ADD': 'wr_cb_add',
           'OFF_CKPT': 'wr_cb_ckpt', 'OFF_RB': 'wr_cb_rollback', 'OFF_REL': 'wr_cb_release',
           'OFF_TASK': 'wr_task', 'OFF_START': 'wr_take_start', 'OFF_LATE': 'wr_late_frame',
           'OFF_SERVICE': 'wr_service'}   # not used by wr_card.S: test_card.py runs the writer through it
CFLAGS = ['--target=armv7a-none-eabi', '-mcpu=cortex-a9', '-mthumb', '-mfloat-abi=soft',
          '-mfpu=none', '-mstackrealign', '-ffreestanding', '-fno-builtin', '-nostdlib',
          '-fno-jump-tables', '-fropi', '-fno-addrsig', '-O2', '-std=c11', '-Wall', '-Wextra',
          '-Werror', '-Wno-unused-function']
API = re.compile(r'^((?:int|void|uint32_t|bq_block)\s*\*?\s*((?:bq|wr)_\w+)\s*\()', re.M)


class BuildError(RuntimeError):
    pass


def unity(tree):
    for f in ('bq.h', 'bq.c', 'wr.h', 'wr.c', 'wr_card.c'):
        text = (HERE / f).read_text()
        text = API.sub(lambda m: ('static __attribute__((used)) ' if m.group(2) in ENTRIES.values()
                                  else 'static ') + m.group(1), text)
        (tree / f).write_text(text)
    u = tree / 'unity.c'
    u.write_text('#include "bq.c"\n#include "wr.c"\n#include "wr_card.c"\n')
    return u


def compile_c(tree, src, defines=()):
    obj = tree / (src.stem + '.o')
    r = subprocess.run(['clang', *CFLAGS, *[f'-D{d}' for d in defines], '-I', str(tree), '-c', str(src), '-o', str(obj)],
                       capture_output=True, text=True)
    if r.returncode:
        raise BuildError('compile failed:\n' + r.stderr)
    return obj


def sizeof_state(tree):
    probe = tree / 'probe.c'
    probe.write_text('#include "wr.h"\nchar wr_state_size_probe[sizeof(wr_t)];\n')
    d = compile_c(tree, probe).read_bytes()
    shoff, = struct.unpack_from('<I', d, 0x20)
    _, shnum, _ = struct.unpack_from('<HHH', d, 0x2E)
    secs = [struct.unpack_from('<10I', d, shoff + 40 * i) for i in range(shnum)]
    sym = next(s for s in secs if s[1] == 2)
    strs = secs[sym[6]]
    for i in range(sym[5] // 16):
        n, _v, size, *_ = struct.unpack_from('<IIIBBH', d, sym[4] + 16 * i)
        if d[strs[4] + n:d.index(b'\0', strs[4] + n)] == b'wr_state_size_probe':
            return size
    raise BuildError('size probe missing')


def check_sites():
    img = B.IMAGE.read_bytes()
    for a, hexs in SITES.items():
        if img[a - 0xC0000000:a - 0xC0000000 + 8].hex() != hexs:
            raise BuildError(f'0x{a:08X} is not the stock prologue in the reference image')


def build(defines=()):
    """defines: test mutants only (test_card.py); a release build passes none."""
    check_sites()
    with tempfile.TemporaryDirectory() as tmp:
        tree = pathlib.Path(tmp)
        text = elf_text.load_text(compile_c(tree, unity(tree), defines))
        state_bytes = sizeof_state(tree)
    missing = [f for f in ENTRIES.values() if f not in text.functions]
    if missing:
        raise BuildError(f'entries missing: {missing}')
    if any(not text.functions[f] & 1 for f in ENTRIES.values()):
        raise BuildError('an entry is not Thumb')
    src = HERE / 'wr_card.S'
    defs = lambda rel: [f'STATE_REL=0x{rel:X}'] + [f'{k}=0x{text.functions[v]:X}' for k, v in ENTRIES.items()]
    c_base = symbols(src, defs(0))['c_base']
    inner = lambda rel: (lambda code: code[:c_base] + text.code)(assemble(src, defs(rel)))
    rows = [(a, bytes(8), SL_EXCL, 'claim') for a in SITES]
    probe = B.patch_sup(SUP_ID, rows, inner(0), inner_entry=0, version=VERSION)
    file_len = len(probe)
    inner_at = probe.index(inner(0)[:64])          # the inner blob ends the body
    state_at = (file_len + 63) & ~63
    block = state_at + state_bytes
    sup = B.patch_sup(SUP_ID, rows, inner(state_at - inner_at), inner_entry=0,
                      version=VERSION, block_size=block)
    if len(sup) != file_len or sup.index(inner(state_at - inner_at)[:64]) != inner_at:
        raise BuildError('layout moved between passes')
    info = {'file_len': file_len, 'block_size': block, 'inner_at': inner_at, 'c_base': c_base,
            'c_text': len(text.code), 'state_at': state_at, 'state_bytes': state_bytes,
            'entries': {v: text.functions[v] for v in ENTRIES.values()},
            'sha256': hashlib.sha256(sup).hexdigest()}
    return sup, info


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=pathlib.Path, help='directory (fpSup/tools/release_v3.py)')
    out = ap.parse_args().out
    out = out / OUT.name if out else OUT
    sup, info = build()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(sup)
    (out.parent / 'build.json').write_text(json.dumps(info, indent=1))
    print(f'{OUT.name}: {info["file_len"]} B, block {info["block_size"]} B, C {info["c_text"]} B, '
          f'state {info["state_bytes"]} B, sha256 {info["sha256"][:16]}')


if __name__ == '__main__':
    main()
