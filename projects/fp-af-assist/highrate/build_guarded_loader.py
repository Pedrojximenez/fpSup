"""Build a guarded derivative of the maintained cold-boot SD loader.

No installer and no card/USB access. Emits bytes only; callers must still verify
their VBIN sections, entry, owner/lifecycle, cache publication and recovery plan.
The existing maintained source is pinned rather than copied/forked silently.
"""
import hashlib
from pathlib import Path
import struct
import tempfile

if __package__:
    from . import build_publication
else:
    import build_publication

SOURCE_HASH = 'e43b274e571b8709ab88e4f2c62f2a85409ec8f071d681587c2cff8c6e0b1348'
LOADER_BASE = 0xC072DE64
LOADER_LIMIT = 0xC072F000  # dedicated image: no gyro/legacy worker in this span
FILE_BYTES = 32768
ECHO_SLOT = 0xC0BAC2F8
ECHO_ORIGINAL = 0xC03D99A0


def replace_once(source, before, after):
    if source.count(before) != 1:
        raise ValueError('maintained loader anchor changed')
    return source.replace(before, after, 1)


def guarded_source(source):
    if hashlib.sha256(source.encode()).hexdigest() != SOURCE_HASH:
        raise ValueError('maintained loader source identity changed')
    source = replace_once(source,
        '    ldr     r4, [r0]                    @ pool\n',
        '''    ldr     r4, [r0]                    @ pool
    LDA     r1, EXPECTED_POOL
    cmp     r4, r1
    bne     load_stop
    ldr     r1, [r0, #4]                @ actual allocation size
    mov     r2, #0x100000
    cmp     r1, r2
    blo     load_stop
    ldr     r1, [r0, #8]                @ allocator type 0
    cmp     r1, #0
    bne     load_stop
''')
    source = replace_once(source,
        '''    LDA     r2, MAXLEN
    mov     r3, #0
    CALL    F_READ
''',
        '''    sub     sp, sp, #16                @ aligned actual-count storage
    mov     r3, #0
    str     r3, [sp]
    str     r3, [sp, #4]
    LDA     r2, VERIFIED_FILE_BYTES
    mov     r3, sp
    CALL    F_READ
    mov     r8, r0                     @ boolean return, not a byte count
''')
    source = replace_once(source,
        '    ldr     r0, [r6]                    @ nothing runs until the file says it is\n',
        '''    ldr     r0, [sp]                   @ exact actual count, C0366060 ABI
    ldr     r1, [sp, #4]
    add     sp, sp, #16
    cmp     r8, #1
    bne     load_stop
    cmp     r1, #0
    bne     load_stop
    LDA     r1, VERIFIED_FILE_BYTES
    cmp     r0, r1
    bne     load_stop

    @ Verify the entire fixed-size VBIN BEFORE executing its stage2 instructions.
    mvn     r0, #0
    mov     r1, r6
    LDA     r2, VERIFIED_FILE_BYTES
    LDA     r8, 0xEDB88320
loader_crc_byte:
    ldrb    r3, [r1], #1
    eor     r0, r0, r3
    mov     r7, #8
loader_crc_bit:
    lsrs    r0, r0, #1
    eorcs   r0, r0, r8
    subs    r7, r7, #1
    bne     loader_crc_bit
    subs    r2, r2, #1
    bne     loader_crc_byte
    mvn     r0, r0
    LDA     r1, VERIFIED_FILE_CRC
    cmp     r0, r1
    bne     load_stop

    ldr     r0, [r6]                    @ magic after full-file CRC
''')
    source = replace_once(source,
        '    CALL    F_CACHE\n    ldr     r1, [r6, #4]',
        '    CALL    F_CACHE\n    CALL    0xC000EABC\n    ldr     r1, [r6, #4]')
    return source


def build(*, expected_pool, file_crc):
    if (type(expected_pool) is not int or expected_pool & 0x1FF or
            not 0x40000000 <= expected_pool <= 0x7FF00000):
        raise ValueError('unsupported exact cold-boot pool base')
    if type(file_crc) is not int or not 0 <= file_crc <= 0xFFFFFFFF:
        raise ValueError('invalid fixed-file CRC')
    original = build_publication.root() / 'fpSup/fp_usb_shell/asm/loader.S'
    source = guarded_source(original.read_text())
    defines = (f'LOADER_BASE={LOADER_BASE}', 'NOTASK=1',
               f'EXPECTED_POOL={expected_pool}', f'VERIFIED_FILE_BYTES={FILE_BYTES}',
               f'VERIFIED_FILE_CRC={file_crc}')
    assembler = build_publication._assembler()
    with tempfile.TemporaryDirectory(prefix='fp-guarded-loader-') as temp:
        path = Path(temp) / 'loader.S'
        path.write_text(source)
        code = assembler.assemble(path, defines)
        symbols = assembler.symbols(path, defines)
    if not code or LOADER_BASE + len(code) > LOADER_LIMIT:
        raise ValueError('guarded loader exceeds its dedicated cold-boot code lease')
    return code, source, {
        'source_sha256': SOURCE_HASH, 'code_sha256': hashlib.sha256(code).hexdigest(),
        'load_base': LOADER_BASE, 'code_bytes': len(code),
        'entry': LOADER_BASE + symbols['boot'], 'file_bytes': FILE_BYTES,
        'file_crc32': file_crc, 'expected_pool': expected_pool,
        'file_crc_checked_before_stage2': True, 'file_actual_count_checked': True,
        'task_created': False, 'legacy_worker_started': False,
        'd_then_i_before_stage2': True, 'deployment_ready': False,
        'bootstrap_ram_readback_verified': False,
    }


def autorun_review_script(code, *, entry):
    """Review artifact only; not written to a mounted card by this function."""
    if not code or len(code) % 4 or LOADER_BASE + len(code) > LOADER_LIMIT or entry != LOADER_BASE:
        raise ValueError('unexpected guarded loader layout')
    lines = ['# EP83 COLD-BOOT REVIEW ONLY — NOT AN AF BETA',
             '# USB unplugged. Dedicated test card. No legacy worker or gyro payload.',
             '# Requires completed deployment review and a verified off-card backup.',
             'memmgr bufmem get 0 1048576']
    for i, (word,) in enumerate(struct.iter_unpack('<I', code)):
        lines.append(f'mem set 0x{LOADER_BASE + i*4:08X} 0x{word:08X}')
    lines += ['# Publish loader data/instructions using existing no-argument ROM routines.']
    for target in (0xC000E91C, 0xC000EABC, entry):
        lines.extend((f'mem set 0x{ECHO_SLOT:08X} 0x{target:08X}', 'echo'))
    lines += [f'mem set 0x{ECHO_SLOT:08X} 0x{ECHO_ORIGINAL:08X}'] * 3
    return '\n'.join(lines) + '\n'
