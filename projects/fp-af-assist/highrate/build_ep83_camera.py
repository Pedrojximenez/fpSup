#!/usr/bin/env python3
"""Build a review-only EP83 camera core; never install it or access USB.

The compiler sees one translation unit containing the sender, direct event
wait, camera adapter, and any explicitly named extra C sources.  The emitted
raw image is accepted only when every runtime dependency is internal to
``.text`` and the image has no allocated data/rodata dependency.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile

if __package__:
    from . import build_publication
    from . import build_sender
    from . import ep83_boot_plan
else:
    import build_publication
    import build_sender
    import ep83_boot_plan


HERE = Path(__file__).resolve().parent
BASE_SOURCES = (
    HERE / 'af_sender.c',
    HERE / 'af_ep83_wait.c',
)
CAMERA_SOURCE = HERE / 'af_ep83_camera.c'
CONTROL_SOURCE = HERE / 'af_ep83_control.c'
OPTIONAL_INTEGRATED_SOURCES = (
    HERE / 'af_ep83_memory.c',
)

COMPILE_DEFINES = (
    'AF_EP83_ENABLE_FIXED_BINDING',
    'AF_EP83_OMIT_FIXED_OPS_FACTORY',
)
# The maintained raw-image relocator intentionally supports ARM CALL but not
# tail-call JUMP24 relocations, and this image forbids compiler data tables.
CAMERA_FLAGS = build_sender.FLAGS + (
    '-fno-optimize-sibling-calls',
    '-fno-jump-tables',
)

RUNTIME_CODE_BEGIN = 0x50000
RUNTIME_CODE_LIMIT = 0x54000
RUNTIME_STATE = 0x54000
RUNTIME_RECORDS = 0x54080
RUNTIME_DMA = 0x5C400
RUNTIME_CONFIG = 0x64800
RUNTIME_PRIVATE = 0x64900
RUNTIME_CONTROL = 0x64A00
RUNTIME_WINDOW_END = 0x65000

MAX_RECORDS = 256
RECORD_BYTES = 128
CAPTURE_HEADER_BYTES = 64
BATCH_HEADER_BYTES = 64
DMA_CAPACITY = BATCH_HEADER_BYTES + CAPTURE_HEADER_BYTES + MAX_RECORDS * RECORD_BYTES

CONFIG_MAGIC = 0x31434641       # 'AFC1'
CONFIG_SCHEMA = 1
CONFIG_BYTES = 256
PRIVATE_MAGIC = 0x31504641      # 'AFP1'
PRIVATE_SCHEMA = 1
PRIVATE_BYTES = 256
CONTROL_MAGIC = 0x314E4641      # 'AFN1'
CONTROL_SCHEMA = 1
CONTROL_BYTES = 256

CONFIG_OFFSET_SYMBOLS = (
    'af_ep83_camera_preflight',
    'af_ep83_camera_publish',
    'af_ep83_camera_start',
    'af_ep83_camera_wait',
    'af_ep83_camera_completion',
    'af_ep83_camera_native_start',
    'af_ep83_fixed_clear',
    'af_ep83_fixed_enter',
    'af_ep83_fixed_exit',
    'af_ep83_fixed_interest_load',
    'af_ep83_fixed_interest_store',
    'af_ep83_fixed_irq_reenable',
    'af_ep83_fixed_wait',
)
REQUIRED_SYMBOLS = frozenset(CONFIG_OFFSET_SYMBOLS + (
    'af_ep83_camera_entry',
    'af_tx_send',
    'af_crc32',
    'af_ep83_wait_start',
    'af_ep83_wait_once',
    'af_ep83_completion_ok',
))


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _hex32(value):
    return f'0x{value:08X}'


def _u32(name, value, *, nonzero=True, alignment=1, span=0):
    if (type(value) is not int or value < int(nonzero) or value > 0xFFFFFFFF or
            value % alignment or value + span > 0x100000000):
        raise ValueError(f'invalid {name}')


def _source_list(extra_sources):
    extras = tuple(Path(path).resolve() for path in extra_sources)
    integrated = tuple(path for path in OPTIONAL_INTEGRATED_SOURCES if path.is_file())
    sources = BASE_SOURCES + integrated + extras + (CAMERA_SOURCE,)
    if len(set(sources)) != len(sources):
        raise ValueError('duplicate C source')
    for source in sources:
        if source.suffix != '.c' or not source.is_file():
            raise ValueError(f'missing C source: {source}')
    return sources


def _translation_unit(sources):
    lines = [
        '/* Generated offline single translation unit; do not install. */',
    ]
    for source in sources:
        escaped = str(source).replace('\\', '\\\\').replace('"', '\\"')
        lines.append(f'#include "{escaped}"')
    return '\n'.join(lines) + '\n'


def _symbol_name(elf, strtab, name_offset):
    if not name_offset:
        return ''
    begin = strtab[4] + name_offset
    end = elf.index(b'\0', begin)
    return elf[begin:end].decode()


def _audit_object(assembler, assembly_path):
    elf, _, sections = assembler._parse(assembler._compile(assembly_path))
    text_index, _ = sections['.text']

    allocated = {}
    for name, (_, section) in sections.items():
        size, flags = section[5], section[2]
        if flags & 2 and size:
            allocated[name] = size
            if name not in ('.text', '.ARM.exidx'):
                raise ValueError(f'unsupported allocated section {name}')
        # ARM EH index metadata is not copied into the raw image; its PREL31
        # relocations therefore cannot become runtime dependencies.  This is
        # the same non-emitted section tolerated by build_sender.FLAGS.
        if (name.startswith('.rel') and size and
                name not in ('.rel.text', '.rel.ARM.exidx')):
            raise ValueError(f'unsupported relocation section {name}')

    _, symtab = sections['.symtab']
    _, strtab = sections['.strtab']
    globals_in_text = {}
    undefined = []
    for pos in range(symtab[4], symtab[4] + symtab[5], symtab[9]):
        name_offset, value, size, info, _, section = struct.unpack_from(
            '<IIIBBH', elf, pos)
        name = _symbol_name(elf, strtab, name_offset)
        binding, symbol_type = info >> 4, info & 0xF
        if name and section == 0:
            undefined.append(name)
        if name and section == text_index and binding in (1, 2) and symbol_type == 2:
            globals_in_text[name] = value
    if undefined:
        raise ValueError('external runtime symbols: ' + ', '.join(sorted(undefined)))
    return allocated, globals_in_text


def _compile(sources):
    assembler = build_publication._assembler()
    unit_text = _translation_unit(sources)
    with tempfile.TemporaryDirectory(prefix='fp-af-ep83-camera-') as temp:
        temp_path = Path(temp)
        unit = temp_path / 'ep83_camera_all.c'
        assembly_path = temp_path / 'ep83_camera_all.S'
        unit.write_text(unit_text)
        command = [
            'clang', *CAMERA_FLAGS,
            *(f'-D{define}' for define in COMPILE_DEFINES),
            '-I', str(HERE), '-S', str(unit), '-o', str(assembly_path),
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode:
            raise ValueError('camera core compile failed: ' + result.stderr.strip())
        allocated, global_symbols = _audit_object(assembler, assembly_path)
        # The maintained assembler resolves only audited intra-.text ARM
        # relocations and deliberately rejects every outside target/type.
        try:
            code = assembler.assemble(assembly_path)
            all_symbols = assembler.symbols(assembly_path)
        except SystemExit as exc:
            raise ValueError(f'camera core relocation rejected: {exc}') from exc
        assembly = assembly_path.read_text()
    required = set(REQUIRED_SYMBOLS)
    if HERE / 'af_ep83_memory.c' in sources:
        required.add('af_ep83_memory_ok')
    if CONTROL_SOURCE in sources:
        required.update(('af_ep83_control_entry', 'af_ep83_control_snapshot_ok'))
    if not required <= global_symbols.keys():
        missing = sorted(required - global_symbols.keys())
        raise ValueError('required camera symbols missing: ' + ', '.join(missing))
    for name in required:
        if all_symbols.get(name) != global_symbols[name]:
            raise ValueError(f'inconsistent symbol offset: {name}')
    return code, assembly, global_symbols, allocated, unit_text


def _templates(*, runtime_pool_expected_base, dma_bus, expected_count, wait_ms,
               symbols):
    _u32('runtime pool expected base', runtime_pool_expected_base,
         alignment=0x200, span=RUNTIME_WINDOW_END)
    _u32('DMA bus', dma_bus, alignment=64, span=DMA_CAPACITY)
    if type(expected_count) is not int or not 1 <= expected_count <= MAX_RECORDS:
        raise ValueError('expected count must be 1..256')
    if type(wait_ms) is not int or not 1 <= wait_ms <= 2000:
        raise ValueError('wait_ms must be 1..2000')

    address = lambda offset: runtime_pool_expected_base + offset
    dma_cpu = address(RUNTIME_DMA)
    if dma_cpu < 0x40000000 or dma_bus != dma_cpu - 0x40000000:
        raise ValueError('explicit DMA bus does not match the audited native conversion')
    code_base, code_limit = address(RUNTIME_CODE_BEGIN), address(RUNTIME_CODE_LIMIT)
    offsets = []
    for name in CONFIG_OFFSET_SYMBOLS:
        value = symbols[name]
        if not 0 < value < RUNTIME_CODE_LIMIT - RUNTIME_CODE_BEGIN or value & 3:
            raise ValueError(f'invalid relocatable offset for {name}')
        offsets.append(value)

    words = [
        CONFIG_MAGIC, CONFIG_SCHEMA, CONFIG_BYTES,
        runtime_pool_expected_base, code_base, code_limit,
        address(RUNTIME_STATE), address(RUNTIME_RECORDS), dma_cpu,
        dma_bus, DMA_CAPACITY, address(RUNTIME_CONFIG), address(RUNTIME_PRIVATE),
        expected_count, wait_ms,
        0, 0, 0,                 # armed nonce, mapping epoch, owner epoch
        0, 0, 0, 0, 0,           # expected TRB and its four idle words
        *offsets,
    ]
    if len(words) != 36:
        raise RuntimeError('camera config prefix layout changed')
    words.extend([0] * (64 - len(words)))
    private = [PRIVATE_MAGIC, PRIVATE_SCHEMA, PRIVATE_BYTES] + [0] * 61
    return struct.pack('<64I', *words), struct.pack('<64I', *private)


def build(*, rom, runtime_pool_expected_base, dma_bus, expected_count, wait_ms,
          extra_sources=()):
    """Return ``(artifacts, manifest)`` without writing or device access."""
    rom_bytes = Path(rom).read_bytes()
    boot_plan = ep83_boot_plan.build_plan(rom_bytes)
    explicit_extras = tuple(Path(path).resolve() for path in extra_sources)
    sources = _source_list(explicit_extras)
    code, assembly, symbols, allocated, unit_text = _compile(sources)

    code_capacity = RUNTIME_CODE_LIMIT - RUNTIME_CODE_BEGIN
    if not code or len(code) > code_capacity:
        raise ValueError('camera core exceeds pool +0x50000..+0x54000')
    config, private = _templates(
        runtime_pool_expected_base=runtime_pool_expected_base,
        dma_bus=dma_bus, expected_count=expected_count, wait_ms=wait_ms,
        symbols=symbols)
    code_base = runtime_pool_expected_base + RUNTIME_CODE_BEGIN
    code_limit = runtime_pool_expected_base + RUNTIME_CODE_LIMIT
    exported = {name: symbols[name] for name in sorted(symbols)}
    symbol_document = {
        'schema': 'fp-af-ep83-camera-symbols-v1',
        'code_base_expected': code_base,
        'code_base_expected_hex': _hex32(code_base),
        'offsets': exported,
        'expected_addresses': {
            name: code_base + offset for name, offset in exported.items()
        },
    }
    symbols_bytes = (json.dumps(symbol_document, indent=2, sort_keys=True) + '\n').encode()

    artifacts = {
        'ep83-camera.bin': code,
        'ep83-camera.S': assembly.encode(),
        'ep83-camera-config.bin': config,
        'ep83-camera-private.bin': private,
        'ep83-camera-symbols.json': symbols_bytes,
    }
    has_control = CONTROL_SOURCE in sources
    if has_control:
        control = [CONTROL_MAGIC, CONTROL_SCHEMA, 0] + [0] * 61
        artifacts['ep83-control-state.bin'] = struct.pack('<64I', *control)
    manifest = {
        'schema': 'fp-af-ep83-camera-offline-build-v1',
        'kind': 'review_only_camera_core',
        'offline_only': True,
        'deployment_ready': False,
        'adapter_complete': False,
        'hardware_validated': False,
        'cold_boot_required': True,
        'autorun_generated': False,
        'native_control_installed': False,
        'native_control_candidate_compiled': has_control,
        'loader_integration_complete': False,
        'cache_publication_verified': False,
        'pool_lease_verified': False,
        'card_write_performed': False,
        'usb_access_performed': False,
        'single_usb_owner_verified': False,
        'usb_client_races_closed': False,
        'dma_mapping_verified': False,
        'runtime_pool_is_expected_not_observed_by_builder': True,
        'rom_sha256': boot_plan['rom_sha256'],
        'boot_patch_before_images_verified': True,
        'boot_patch_plan': boot_plan['patch_order'],
        'compiler_flags': list(CAMERA_FLAGS),
        'compiler_defines': list(COMPILE_DEFINES),
        'single_translation_unit': True,
        'translation_unit_sha256': _sha256(unit_text.encode()),
        'allocated_sections': allocated,
        'external_runtime_symbols': [],
        'runtime_pool': {
            'expected_base': runtime_pool_expected_base,
            'expected_base_hex': _hex32(runtime_pool_expected_base),
            'actual_base_claimed': False,
            'code_offset': RUNTIME_CODE_BEGIN,
            'code_limit_offset': RUNTIME_CODE_LIMIT,
            'code_base_expected': code_base,
            'code_limit_expected': code_limit,
            'code_bytes': len(code),
            'code_capacity': code_capacity,
            'state_offset': RUNTIME_STATE,
            'records_offset': RUNTIME_RECORDS,
            'dma_offset': RUNTIME_DMA,
            'config_offset': RUNTIME_CONFIG,
            'private_offset': RUNTIME_PRIVATE,
            'control_offset': RUNTIME_CONTROL if has_control else None,
            'window_end_offset': RUNTIME_WINDOW_END,
        },
        'camera_config': {
            'bytes': CONFIG_BYTES,
            'magic': CONFIG_MAGIC,
            'schema': CONFIG_SCHEMA,
            'expected_count': expected_count,
            'wait_ms': wait_ms,
            'dma_cpu_expected': runtime_pool_expected_base + RUNTIME_DMA,
            'dma_bus_candidate': dma_bus,
            'dma_capacity': DMA_CAPACITY,
            'armed_nonce': 0,
            'mapping_epoch': 0,
            'owner_epoch': 0,
            'expected_trb': 0,
            'expected_idle_trb': [0, 0, 0, 0],
            'preflight_failclosed': True,
            'offset_words_23_35': {
                name: symbols[name] for name in CONFIG_OFFSET_SYMBOLS
            },
        },
        'private_template': {
            'bytes': PRIVATE_BYTES,
            'magic': PRIVATE_MAGIC,
            'schema': PRIVATE_SCHEMA,
            'phase': 0,
            'remaining_words_zero': True,
        },
        'control_template': ({
            'bytes': CONTROL_BYTES,
            'magic': CONTROL_MAGIC,
            'schema': CONTROL_SCHEMA,
            'phase': 0,
            'offset': RUNTIME_CONTROL,
            'installed': False,
        } if has_control else None),
        'entry_offset': symbols['af_ep83_camera_entry'],
        'entry_expected_address': code_base + symbols['af_ep83_camera_entry'],
        'sources': {
            str(source): _sha256(source.read_bytes()) for source in sources
        },
        'explicit_extra_sources': [str(source) for source in explicit_extras],
        'symbols': exported,
        'warnings': [
            'This is not an AutoRun installer and must not be written to a card.',
            'The runtime pool address is an expected candidate, not a live observation or lease.',
            'Proof epochs, nonce and TRB identity are intentionally zero, so preflight must fail.',
            'No USB-client race, DMA mapping, endpoint ownership or loader cache issue is closed.',
        ],
    }
    manifest['artifacts'] = {
        name: {'bytes': len(data), 'sha256': _sha256(data)}
        for name, data in sorted(artifacts.items())
    }
    return artifacts, manifest


def write_build(output, **kwargs):
    output = Path(output)
    if os.path.lexists(output):
        raise FileExistsError(f'output already exists: {output}')
    artifacts, manifest = build(**kwargs)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir(exist_ok=False)
    for name, data in sorted(artifacts.items()):
        (output / name).write_bytes(data)
    (output / 'manifest.json').write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + '\n')
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--rom', type=Path,
                        default=build_publication.root() / 'out/seg0_c0000000.bin')
    parser.add_argument('--runtime-pool-expected-base', required=True,
                        type=lambda value: int(value, 0))
    parser.add_argument('--dma-bus', required=True, type=lambda value: int(value, 0))
    parser.add_argument('--expected-count', required=True, type=int)
    parser.add_argument('--wait-ms', required=True, type=int)
    parser.add_argument('--extra-source', action='append', default=[], type=Path)
    args = parser.parse_args(argv)
    values = vars(args)
    output = values.pop('output')
    try:
        manifest = write_build(output, extra_sources=values.pop('extra_source'), **values)
    except (OSError, ValueError, RuntimeError) as exc:
        parser.error(str(exc))
    print(json.dumps({
        'output': str(output),
        'schema': manifest['schema'],
        'code_bytes': manifest['runtime_pool']['code_bytes'],
        'deployment_ready': manifest['deployment_ready'],
        'preflight_failclosed': manifest['camera_config']['preflight_failclosed'],
    }, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
