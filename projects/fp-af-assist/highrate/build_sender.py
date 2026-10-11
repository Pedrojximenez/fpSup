#!/usr/bin/env python3
"""Compile the freestanding sender core for ARM; no installer or USB I/O."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile

if __package__:
    from . import build_publication
else:
    import build_publication

SOURCE = Path(__file__).with_name('af_sender.c')
HEADER = SOURCE.with_suffix('.h')
FLAGS = ('-target', 'armv7-none-eabi', '-marm', '-mfloat-abi=soft', '-Oz',
         '-ffreestanding', '-fno-builtin', '-fno-stack-protector',
         '-fno-unwind-tables', '-fno-asynchronous-unwind-tables',
         '-fno-vectorize', '-fno-slp-vectorize', '-std=c11',
         '-Wall', '-Wextra', '-Werror')


def assemble():
    assembler = build_publication._assembler()
    with tempfile.TemporaryDirectory(prefix='fp-af-sender-') as temp:
        source = Path(temp) / 'sender.S'
        subprocess.run(['clang', *FLAGS, '-S', str(SOURCE), '-o', str(source)],
                       check=True, capture_output=True, text=True)
        # Reuse the maintained ELF parser/relocator. Fail if the C compiler
        # introduces external runtime calls or non-text data dependencies.
        elf, _, sections = assembler._parse(assembler._compile(source))
        for name, (_, section) in sections.items():
            if section[2] & 2 and section[5] and name not in ('.text', '.ARM.exidx'):
                raise ValueError(f'unsupported allocated section {name}')
        _, symtab = sections['.symtab']
        for pos in range(symtab[4], symtab[4] + symtab[5], symtab[9]):
            name, _, _, _, _, section = struct.unpack_from('<IIIBBH', elf, pos)
            if name and section == 0:
                raise ValueError('sender depends on an external runtime symbol')
        code = assembler.assemble(source)
        symbols = assembler.symbols(source)
        emitted_assembly = source.read_text()
    if not {'af_tx_send', 'af_crc32', 'af_ep83_completion_ok'} <= symbols.keys():
        raise ValueError('required sender symbols missing')
    return code, emitted_assembly, dict(
        offline_only=True, deployment_ready=False, firmware_adapter_complete=False,
        ownership_verified=False, lifecycle_verified=False,
        compiled_bytes=len(code), af_tx_send_offset=symbols['af_tx_send'],
        af_crc32_offset=symbols['af_crc32'], required_stack_alignment=8,
        completion_check_offset=symbols['af_ep83_completion_ok'],
        runtime='freestanding ARMv7 soft-float, no libc; no unwind metadata',
        compiler_flags=list(FLAGS),
        c_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        header_sha256=hashlib.sha256(HEADER.read_bytes()).hexdigest(),
        code_sha256=hashlib.sha256(code).hexdigest())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error('--output must not exist')
    code, assembly, manifest = assemble()
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'sender-core.bin').write_bytes(code)
    (args.output / 'sender-core.S').write_text(assembly)
    (args.output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
