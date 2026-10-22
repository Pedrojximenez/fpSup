#!/usr/bin/env python3
"""Build an OFFLINE fp 5.02 publication-hook candidate; never deploys anything."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

if __package__:
    from . import af_batch as fmt
else:
    import af_batch as fmt

SOURCE = Path(__file__).with_name('af_publication.S')
ROM_SHA256 = 'aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622'
# Known live ranges are exclusions, NOT a complete memory map or RAM lease.
# Producer extent is verified in HOOK_ABI_AUDIT: final POP at C023EC20.
LIVE_SOURCE_WORDS = (
    0xC32044D8, 0xC32985E8, 0xC32986B4, 0xC3476418, 0xC32914E0,
    0xC31F8CB4, 0xC31F8CB8, 0xC3291514, 0xC3291534, 0xC32915B0,
    0xC343B5A0, 0xC343B5A8, 0xC343B5B4, 0xC343B5BC, 0xC32915B4,
    0xC3291694, 0xC329169C, 0xC32916B0, 0xC30338C8, 0xC30338D0,
    0xC3033A6C, 0xC32046A4, 0xC32065A0, 0xC3298918, 0xC343B7BC,
    0xC343B7C0, 0xC3476408, 0xC3476414,
)
PROTECTED_RANGES = ((fmt.CALLSITE - 12, fmt.CONTINUATION + 12),
                    (fmt.PRODUCER, 0xC023EC24)) + tuple(
                    (address, address + 4) for address in LIVE_SOURCE_WORDS)


def root():
    for parent in SOURCE.parents:
        if (parent / 'fpSup/fp_usb_shell/armasm.py').is_file():
            return parent
    raise ValueError('maintained USB assembler not found')


def _assembler():
    spec = importlib.util.spec_from_file_location('fp_maintained_armasm', root() / 'fpSup/fp_usb_shell/armasm.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def defines(*, state_base, records_base, capacity):
    """The assembler defines, in one place: schema and level cannot drift."""
    return (f'AF_STATE={state_base}', f'AF_RECORDS={records_base}',
            f'AF_CAPACITY={capacity}', f'AF_SCHEMA={fmt.SCHEMA}',
            f'AF_LEVEL_COUNT={fmt.LEVEL_COUNT}',
            f'AF_LEVEL_RECORD={fmt.LEVEL_RECORD}')


def branch_word(code_base):
    disp = code_base - fmt.CALLSITE - 8
    if code_base & 3 or disp & 3 or not -(1 << 25) <= disp < (1 << 25):
        raise ValueError('ARM BL alignment/range failure')
    return 0xeb000000 | ((disp >> 2) & 0xffffff)


def assemble(*, code_base, state_base, records_base, capacity=256, nonce,
             veneer_base=None, level=fmt.LEVEL_COUNT):
    initial = fmt.initial_capture(capacity, nonce, level)
    for name, addr, align in (('code', code_base, 4), ('state', state_base, 64),
                              ('records', records_base, 128)):
        if type(addr) is not int or not 0 < addr <= 0xffffffff or addr % align:
            raise ValueError(f'invalid {name} address/alignment')
    # State and records need not be adjacent on camera; dump format concatenates
    # them only after finite capture completes.
    code = _assembler().assemble(SOURCE, defines=defines(
        state_base=state_base, records_base=records_base, capacity=capacity))
    spans = [('code', code_base, len(code)), ('state', state_base, fmt.HEADER_BYTES),
             ('records', records_base, capacity * fmt.RECORD_BYTES)]
    # A 0x4... pool is outside this native ARM BL's +/-32 MiB reach. An optional
    # near veneer uses LDR pc,[pc,#-4] + absolute target, preserves LR/registers,
    # and has its OWN lease/cache/quiescence requirements. Never guess a slot.
    veneer = b''
    if veneer_base is not None:
        if type(veneer_base) is not int or not 0 < veneer_base <= 0xffffffff or veneer_base & 3:
            raise ValueError('invalid veneer address/alignment')
        veneer = struct.pack('<2I', 0xe51ff004, code_base)
        spans.append(('veneer', veneer_base, len(veneer)))
    for name, begin, size in spans:
        if begin + size > 0x100000000:
            raise ValueError(f'{name} wraps address space')
        if any(begin < end and begin + size > start for start, end in PROTECTED_RANGES):
            raise ValueError(f'{name} overlaps known live firmware code/source')
    for i, (name, begin, size) in enumerate(spans):
        for other, start, length in spans[i + 1:]:
            if begin < start + length and start < begin + size:
                raise ValueError(f'{name} overlaps {other}')
    return code, initial, dict(offline_only=True, deployment_ready=False,
                ownership_verified=False, lifecycle_verified=False,
                code_base=code_base, state_base=state_base, records_base=records_base,
                code_bytes=len(code), capacity=capacity, record_bytes=fmt.RECORD_BYTES,
                nonce=nonce, level=level, schema=fmt.SCHEMA,
                callsite=fmt.CALLSITE, original_word=fmt.ORIGINAL_WORD,
                candidate_branch_word=branch_word(code_base if veneer_base is None else veneer_base),
                veneer_base=veneer_base, veneer_bytes=len(veneer), veneer_hex=veneer.hex(),
                source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                code_sha256=hashlib.sha256(code).hexdigest())


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('code-base', 'state-base', 'records-base', 'nonce'):
        p.add_argument('--' + name, required=True, type=lambda n: int(n, 0))
    p.add_argument('--capacity', type=int, default=256)
    p.add_argument('--veneer-base', type=lambda n: int(n, 0))
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--rom', type=Path)
    a = p.parse_args(argv)
    if a.output.exists():
        p.error('--output must not exist')
    rom = (a.rom or root() / 'out/seg0_c0000000.bin').read_bytes()
    if hashlib.sha256(rom).hexdigest() != ROM_SHA256:
        p.error('unsupported ROM hash')
    if struct.unpack_from('<I', rom, fmt.CALLSITE - 0xc0000000)[0] != fmt.ORIGINAL_WORD:
        p.error('unexpected original callsite word')
    code, initial, manifest = assemble(code_base=a.code_base, state_base=a.state_base,
                    records_base=a.records_base, capacity=a.capacity, nonce=a.nonce,
                    veneer_base=a.veneer_base)
    manifest['rom_sha256'] = ROM_SHA256
    a.output.mkdir(parents=True, exist_ok=False)
    (a.output / 'publication.bin').write_bytes(code)
    if manifest['veneer_bytes']:
        (a.output / 'veneer.bin').write_bytes(bytes.fromhex(manifest['veneer_hex']))
    (a.output / 'initial-capture.bin').write_bytes(initial)
    (a.output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
