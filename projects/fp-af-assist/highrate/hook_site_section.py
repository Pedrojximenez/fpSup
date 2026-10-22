#!/usr/bin/env python3
"""Emit the four-byte card section that puts the AF hook site into the journal.

A sup that arms a hook at run time declares the site as a four-byte section
holding the firmware's own word, so stage2 journals it before the entry runs and
the loader's power-off callback writes it back
(fpSup/HOOKS_AT_POWER_OFF.md; gyro's `hook_sites()` in gyro/build_base_card.py).
Writing a site's own word back is a no-op on a stock image and a repair on one a
missed power-off left patched.

The word is READ FROM THE ROM, never typed here, and the ROM's hash is checked
first. This tool writes a file and prints the argument to add to the card build;
it does not build, write or install a card.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

if __package__:
    from . import af_batch as fmt, build_publication as build, shutdown_restore as restore
else:
    import af_batch as fmt
    import build_publication as build
    import shutdown_restore as restore

# The words this project borrows at run time. The echo is deliberately NOT here:
# on an ordinary cold start it may still be lent to `lboot` when stage2 runs, so
# journalling it would record the borrowed value and "restore" the wrong word.
SITES = {fmt.CALLSITE: 'AF publication hook site'}


def stock_word(address, rom=None):
    """The firmware's own word at `address`, from the checked ROM image."""
    if rom is None:
        rom = (build.root() / 'out/seg0_c0000000.bin').read_bytes()
    if hashlib.sha256(rom).hexdigest() != build.ROM_SHA256:
        raise ValueError('unsupported firmware image')
    if address & 3 or not 0xC0000000 <= address < 0xC0000000 + len(rom) - 4:
        raise ValueError('address outside the checked image')
    return struct.unpack_from('<I', rom, address - 0xC0000000)[0]


def section(address, rom=None):
    word = stock_word(address, rom)
    if address in SITES and address == fmt.CALLSITE and word != fmt.ORIGINAL_WORD:
        raise ValueError('ROM word at the AF callsite is not the expected one')
    return struct.pack('<I', word)


def emit(output, *, addresses=tuple(SITES), rom=None):
    """Write one file per site and return the build arguments to add."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    manifest = dict(schema='fp.af-hook-site-section/v1', offline_only=True,
                    card_built=False, installed=False, sites=[])
    for address in addresses:
        data = section(address, rom)
        name = f'hook-site-{address:08X}.bin'
        (output / name).write_bytes(data)
        manifest['sites'].append(dict(
            address=address, word=struct.unpack('<I', data)[0], bytes=len(data),
            note=SITES.get(address, 'run-time hook site'), file=name,
            # --also assembles a source file; --also-bin takes raw bytes.
            build_argument=f'--also-bin 0x{address:08X}:{name}'))
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


def check_card(vbin, *, addresses=tuple(SITES), rom=None):
    """Does this built card declare each site with the stock word?"""
    out = []
    for address in addresses:
        word = struct.unpack('<I', section(address, rom))[0]
        result = restore.declares_hook_site(vbin, address, word)
        out.append(dict(address=address, expected_word=word, **result))
    return dict(all_declared=all(row['matches'] for row in out), sites=out)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--check-card', type=Path,
                        help='a built fpSup.BIN to verify instead of emitting')
    args = parser.parse_args(argv)
    if args.check_card:
        result = check_card(args.check_card.read_bytes())
        args.output.mkdir(parents=True, exist_ok=False)
        (args.output / 'card-check.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result, indent=2))
        return 0 if result['all_declared'] else 1
    print(json.dumps(emit(args.output), indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
