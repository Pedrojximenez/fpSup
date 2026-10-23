"""Offline ARM execution of old/new trailer bytes, with bounded memory IO.

Actual camera JPEG tiles and original header are inputs. Only read/write
callbacks are substitutes; no camera transport is imported. Instruction and
transaction counts are not a wall-clock CPU benchmark.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn import UC_PROT_READ, UC_PROT_WRITE, UC_PROT_EXEC
from unicorn.arm_const import *

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
NATIVE = ROOT / 'fpSup/lossless/native'
spec = importlib.util.spec_from_file_location('checked_trailer_text',
    ROOT / 'research/ui/tools/arm_text/elf_text.py')
elf = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = elf
spec.loader.exec_module(elf)
sys.path.insert(0, str(ROOT / 'projects/lossless-sup/tools'))
import trailing_ifd

CODE, FILE, WORK, TABLE, OUT = 0x30000000, 0x45100000, 0x45600000, 0x45610000, 0x45620000
STACK, STOP, READ, WRITE = 0x46100000, 0x47000000, 0x47000100, 0x47000200


def compile_source(source, label):
    obj = HERE / (label + '.o')
    # Same internal-linkage rule as the production unity builder. Keep these
    # standalone probe entries so the checked extractor needs no relocations.
    import re
    tree = HERE / (label + '-sources')
    pattern = re.compile(r'^(uint32_t\s+fpl_trailer_\w+\s*\()', re.M)
    expected = {tree / 'native' / path.name: pattern.sub(
        r'static __attribute__((used)) \1', path.read_text())
        for path in (source, source.with_name('trailer.h'))}
    expected[tree / 'control.h'] = (NATIVE.parent / 'control.h').read_text()
    if obj.exists():
        assert all(path.read_text() == value for path, value in expected.items())
        return elf.load_text(obj)
    (tree / 'native').mkdir(parents=True)
    for path, value in expected.items(): path.write_text(value)
    subprocess.run([shutil.which('clang') or 'clang', '--target=armv7-none-eabi',
        '-mcpu=cortex-a9', '-mthumb', '-mfloat-abi=soft', '-mfpu=none', '-std=c11',
        '-O2', '-ffreestanding', '-fno-builtin', '-fno-unwind-tables',
        '-fno-asynchronous-unwind-tables', '-fno-addrsig', '-Wall', '-Wextra', '-Werror',
        '-I', str(tree / 'native'), '-c', str(tree / 'native/trailer.c'), '-o', str(obj)],
        check=True, capture_output=True, timeout=30)
    return elf.load_text(obj)


def invoke(text, initial, payload, counts, cached=False, scratch_words=1024):
    mu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    extent = (len(text.code) + 4095) & ~4095
    mu.mem_map(CODE, extent, UC_PROT_READ | UC_PROT_WRITE)
    mu.mem_write(CODE, text.code)
    mu.mem_protect(CODE, extent, UC_PROT_READ | UC_PROT_EXEC)
    mu.mem_map(0x45000000, 0x1000000, UC_PROT_READ | UC_PROT_WRITE)
    mu.mem_map(STACK - 0x10000, 0x10000, UC_PROT_READ | UC_PROT_WRITE)
    mu.mem_map(STOP, 0x1000, UC_PROT_READ | UC_PROT_EXEC)
    mu.mem_write(FILE, initial)
    mu.mem_write(TABLE, struct.pack('<' + 'I' * len(counts), *counts))
    mu.mem_write(WORK - 4, bytes([0xa5]) * (4104))
    stats = {'instructions': 0, 'reads': 0, 'writes': 0, 'root_write_indices': []}
    def instruction(_mu, pc, size, _data):
        if CODE <= pc and pc + size <= CODE + len(text.code):
            stats['instructions'] += 1
            return
        if pc == STOP:
            mu.emu_stop()
            return
        assert pc in (READ, WRITE), f'unapproved execution {pc:#x}'
        assert not mu.reg_read(UC_ARM_REG_SP) & 7, 'unaligned external-call SP'
        a = mu.reg_read(UC_ARM_REG_R0)
        assert not a & 3 and FILE <= a <= FILE + len(initial) - 4
        if pc == READ:
            stats['reads'] += 1
            mu.reg_write(UC_ARM_REG_R0, struct.unpack('<I', mu.mem_read(a, 4))[0])
        else:
            stats['writes'] += 1
            if a == FILE + 4: stats['root_write_indices'].append(stats['writes'])
            mu.mem_write(a, struct.pack('<I', mu.reg_read(UC_ARM_REG_R1)))
        mu.reg_write(UC_ARM_REG_PC, mu.reg_read(UC_ARM_REG_LR))
    mu.hook_add(UC_HOOK_CODE, instruction)
    saved = {register: 0xabcd0000 + n for n, register in enumerate(
        (UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7,
         UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11))}
    for register, value in saved.items(): mu.reg_write(register, value)
    sp = STACK - 0x100
    args = [FILE, len(payload), TABLE, len(counts), 512, 368, len(initial), READ, WRITE]
    args += [WORK, scratch_words, OUT] if cached else [OUT]
    for register, value in zip((UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3), args):
        mu.reg_write(register, value)
    mu.mem_write(sp, struct.pack('<' + 'I' * (len(args) - 4), *args[4:]))
    mu.reg_write(UC_ARM_REG_SP, sp)
    mu.reg_write(UC_ARM_REG_LR, STOP)
    name = 'fpl_trailer_write_cached' if cached else 'fpl_trailer_write_all'
    mu.emu_start(CODE + text.functions[name], STOP, count=200000)
    assert mu.reg_read(UC_ARM_REG_PC) == STOP, 'execution bound exhausted'
    assert mu.reg_read(UC_ARM_REG_R0) == 0
    assert mu.reg_read(UC_ARM_REG_SP) == sp
    for register, value in saved.items(): assert mu.reg_read(register) == value
    result = struct.unpack('<7I', mu.mem_read(OUT, 28))
    final = bytes(mu.mem_read(FILE, len(initial)))
    assert stats['root_write_indices'] == [stats['writes']], 'root published before data'
    assert bytes(mu.mem_read(WORK - 4, 4)) == bytes([0xa5]) * 4
    assert bytes(mu.mem_read(WORK + 4 * scratch_words, 4)) == bytes([0xa5]) * 4
    stats.update(file_bytes=result[5], cache_used=result[6], code_sha256=hashlib.sha256(text.code).hexdigest())
    return stats, final


if __name__ == '__main__':
    # F2 contains its original RAW IFD at offset 8 and its own metadata.
    dng = (ROOT / 'projects/lossless-sup/validation/20261012-pipeline-cost/final-normal-60p-frames/000002.DNG').read_bytes()
    root, = struct.unpack_from('<I', dng, 4)
    entries, = struct.unpack_from('<H', dng, root)
    sizes = None
    for n in range(entries):
        tag, typ, count, offset = struct.unpack_from('<HHII', dng, root + 2 + 12 * n)
        if tag == 325:
            assert typ == 4
            sizes = list(struct.unpack_from('<' + 'I' * count, dng, offset))
    assert sizes and sum(sizes) == root - 0x13400
    payload = dng[0x13400:root]
    header = bytearray(dng[:0x13400]); struct.pack_into('<I', header, 4, 8)
    original = (ROOT / 'projects/lossless-sup/validation/20261012-pipeline-cost/final-normal-60p-frames/000001.DNG').stat().st_size
    initial = bytes(header) + payload + bytes([0x6d]) * (original - len(header) - len(payload))
    reference, _ = trailing_ifd.assemble(header, payload, sizes, 512, 368)
    old = compile_source(HERE / 'before/trailer.c', 'arm-before-local')
    new = compile_source(NATIVE / 'trailer.c', 'arm-cached-local')
    results = {}
    for label, code, cached, words in [('before', old, False, 1024),
                                     ('after', new, True, 1024),
                                     ('fallback', new, True, 1)]:
        stats, final = invoke(code, initial, payload, sizes, cached, words)
        assert final[:len(reference)] == reference
        assert final[len(reference):] == initial[len(reference):]
        results[label] = stats
    assert results['after']['cache_used'] == 1 and results['fallback']['cache_used'] == 0
    assert results['after']['reads'] < results['before']['reads'] * .65
    assert results['after']['writes'] < results['before']['writes']
    (HERE / 'arm-trailer-results.json').write_text(json.dumps(results, indent=2) + '\n')
    print(json.dumps(results, indent=2))
