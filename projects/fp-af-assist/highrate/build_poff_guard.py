#!/usr/bin/env python3
"""RETIRED 2026-09-28: superseded by the shared loader journal.

Power-off restoration is the loader's job. A run-time hook site is declared as a
four-byte card section holding the firmware's own word (see hook_site_section.py
and fpSup/HOOKS_AT_POWER_OFF.md); a sup no longer registers a power-off routine,
and this one also spent one of the ordinary list's ten slots -- the firmware
already fills eight. Kept as a record of the manager ABI it modelled; nothing
imports it in the live path.
"""

import argparse
import hashlib
import json
from pathlib import Path
import struct

if __package__:
    from . import af_batch as fmt, build_publication as build
else:
    import af_batch as fmt
    import build_publication as build

SOURCE = Path(__file__).with_name('af_poff_guard.S')
ECHO, ECHO_ORIGINAL = 0xC0BAC2F8, 0xC03D99A0
DCACHE, ICACHE = 0xC000E91C, 0xC000EABC
HEADER_WORDS = 6
ENTRY_BYTES = 0x18
ALLOWED_SLOTS = 4
MAX_BYTES = 1024
# status bits, mirrored from af_poff_guard.S
ORDINARY, FORCED, NO_MANAGER, ORDINARY_FULL, FORCED_FULL, ATTEMPTED = 1, 2, 4, 8, 16, 32
REGISTERED = ORDINARY | FORCED


def _pairs(*, armed_branch, helper, register_entry):
    """The words this trial borrows, with every value it is allowed to hold.

    A power-off finding anything else at one of these addresses leaves it alone:
    an unknown owner is reported, never overwritten. The echo carries the two
    cache routines, the capture helper and this object's own register entry --
    the installer reaches all four through the same borrow.
    """
    return ((fmt.CALLSITE, fmt.ORIGINAL_WORD, (armed_branch,)),
            (ECHO, ECHO_ORIGINAL, (DCACHE, ICACHE, helper, register_entry)))


def assemble(*, block_base, armed_branch, helper):
    for name, value, align in (('block', block_base, 4), ('helper', helper, 4)):
        if type(value) is not int or not 0 < value <= 0xffffffff or value % align:
            raise ValueError(f'invalid {name} address/alignment')
    if type(armed_branch) is not int or not 0 <= armed_branch <= 0xffffffff:
        raise ValueError('invalid armed branch word')
    if armed_branch == fmt.ORIGINAL_WORD:
        raise ValueError('armed branch equals the stock word: nothing to restore')
    # The block is assembled at its final address; a relocated copy would carry
    # the wrong absolute header words.
    asm = build._assembler()
    defines = (f'AF_POFF_BLOCK={block_base}',
               f'AF_POFF_SITE={fmt.CALLSITE}', f'AF_POFF_SITE_ORIG={fmt.ORIGINAL_WORD}',
               f'AF_POFF_SITE_ARMED={armed_branch}',
               f'AF_POFF_ECHO={ECHO}', f'AF_POFF_ECHO_ORIG={ECHO_ORIGINAL}',
               f'AF_POFF_ECHO_A1={DCACHE}', f'AF_POFF_ECHO_A2={ICACHE}',
               f'AF_POFF_ECHO_A3={helper}')
    code = asm.assemble(SOURCE, defines=defines)
    symbols = asm.symbols(SOURCE, defines=defines)
    if len(code) > MAX_BYTES or len(code) % 4:
        raise ValueError('guard object size rejected')
    for name in ('block', 'pg_register', 'pg_restore', 'pairs', 'block_end'):
        if name not in symbols:
            raise ValueError(f'missing symbol {name}')
    if symbols['block'] or symbols['block_end'] != len(code):
        raise ValueError('block does not span the assembled image')
    header = struct.unpack_from('<%dI' % HEADER_WORDS, code)
    expected = (block_base - 8, block_base + symbols['pg_restore'],
                block_base + symbols['pairs'], 0, 0, 0)
    if header != expected:
        raise ValueError(f'header words {header} != {expected}')
    pairs = _pairs(armed_branch=armed_branch, helper=helper,
                   register_entry=block_base + symbols['pg_register'])
    for address, original, allowed in pairs:
        if len(allowed) > ALLOWED_SLOTS or 0 in allowed or original in allowed:
            raise ValueError(f'invalid allowed set for {address:08X}')
        if len(set(allowed)) != len(allowed):
            raise ValueError(f'duplicate allowed value for {address:08X}')
    table = decode_table(code[symbols['pairs']:], base=block_base + symbols['pairs'])
    if table != [dict(address=a, original=o, allowed=list(w)) for a, o, w in pairs]:
        raise ValueError('assembled table does not match the requested words')
    if any(begin <= address < begin + size
           for address, _, _ in pairs
           for begin, size in ((block_base, len(code)),)):
        raise ValueError('a restored word lies inside the guard object')
    manifest = dict(offline_only=True, deployment_ready=False, registered=False,
                    block_base=block_base, block_bytes=len(code),
                    register_entry=block_base + symbols['pg_register'],
                    routine=block_base + symbols['pg_restore'],
                    pairs=block_base + symbols['pairs'],
                    vtable=block_base - 8, entries=table,
                    armed_branch=armed_branch, helper=helper,
                    poff_manager=0xC30756C4, ordinary_list=0xC30756D0,
                    forced_list=0xC30756F8, list_slots=10,
                    source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                    block_sha256=hashlib.sha256(code).hexdigest())
    return code, manifest


_BLOB_BYTES = None


def blob_bytes():
    """The object's size, which every base produces: for sizing a cave claim.

    Assembles once per process, on demand -- importing this module runs nothing.
    The caller re-assembles at the address the allocator gives it and compares.
    """
    global _BLOB_BYTES
    if _BLOB_BYTES is None:
        code, _ = assemble(block_base=0xC072E100, helper=0xC072E400,
                           armed_branch=0xEA000000)
        _BLOB_BYTES = len(code)
    return _BLOB_BYTES


def decode_table(data, *, base=None, limit=8):
    """Decode { address, original, allowed[4] } entries up to the terminator."""
    out = []
    for index in range(limit + 1):
        offset = index * ENTRY_BYTES
        if offset + 4 > len(data):
            raise ValueError('table is not terminated inside the object')
        address = struct.unpack_from('<I', data, offset)[0]
        if not address:
            return out
        if index == limit:
            raise ValueError('table exceeds the walk bound the routine enforces')
        if offset + ENTRY_BYTES > len(data):
            raise ValueError('truncated table entry')
        words = struct.unpack_from('<%dI' % (ENTRY_BYTES // 4), data, offset)
        allowed = []
        for value in words[2:]:
            if not value:
                break
            allowed.append(value)
        if address & 3 or not allowed or words[1] in allowed:
            raise ValueError(f'invalid entry for {address:08X}')
        if base is not None and base <= address < base + len(data):
            raise ValueError('entry points inside the table')
        out.append(dict(address=address, original=words[1], allowed=allowed))
    raise ValueError('unreachable')


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('block-base', 'armed-branch', 'helper'):
        p.add_argument('--' + name, required=True, type=lambda n: int(n, 0))
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(argv)
    if a.output.exists():
        p.error('--output must not exist')
    code, manifest = assemble(block_base=a.block_base, armed_branch=a.armed_branch,
                              helper=a.helper)
    a.output.mkdir(parents=True, exist_ok=False)
    (a.output / 'poff-guard.bin').write_bytes(code)
    (a.output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
