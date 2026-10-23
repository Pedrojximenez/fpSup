"""Offline prepared two-mode DNG prefix. No camera or production imports.

One prefix contains an inactive compressed IFD beside the original RAW IFD.
Its TIFF root selects exactly one description. The native generation adapter
is NOT installed by this prototype. Preparation still costs work here; only
the completion phase avoids rebuilding an IFD.
"""
from dataclasses import dataclass
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'projects/lossless-sup/tools'))
from tiff_guard import ClassicTIFF, require, scalar

STRIPS = {273, 278, 279}
LAYOUT = STRIPS | {259, 322, 323, 324, 325}
MAX_TILES = 160


def align(n, step=1024):
    return (n + step - 1) & -step


def entry(tag, kind, count, value):
    return struct.pack('<HHII', tag, kind, count, value)


@dataclass(frozen=True)
class Plan:
    source_bytes: int
    raw_ifd: int
    compressed_ifd: int
    pixels: int
    offsets: int
    counts: int
    tiles: int
    tile_width: int
    tile_height: int
    raw_strip_pointer: int
    schema: tuple
    # The producer must update ALL these inline values for EACH frame.
    # Out-of-line values are shared at their original TIFF-relative offsets.
    mirrors: tuple
    seed: bytes


def make_plan(header, tile_width, tile_height):
    """Prepare fixed layout once per geometry/metadata schema, default RAW."""
    require(0 < len(header) <= 0x20000, 'prefix outside prototype bounds')
    tree = ClassicTIFF(header)
    tags = tree.root['tags']
    require(scalar(tags, 259) == 1 and STRIPS <= tags.keys(), 'not native RAW')
    require(not ({322, 323, 324, 325} & tags.keys()), 'already tiled')
    require(tags[273]['type'] == 4 and tags[273]['count'] == 1,
            'only a scalar LONG strip offset supported')
    require(scalar(tags, 273) == len(header), 'RAW pixels not after prefix')
    width, height = scalar(tags, 256), scalar(tags, 257)
    require(scalar(tags, 278) == height and tags[279]['count'] == 1,
            'only one full-height strip supported')
    require(32 <= tile_width <= 512 and tile_width % 32 == 0 and
            16 <= tile_height <= 512 and tile_height % 16 == 0,
            'grid outside current LOSS engine/TIFF intersection')
    tiles = ((width + tile_width - 1) // tile_width) * ((height + tile_height - 1) // tile_height)
    require(1 <= tiles <= MAX_TILES, 'tile count outside bound')
    for region in tree.protected:
        require(8 <= region['start'] < region['end'] <= len(header),
                'metadata outside retained prefix')
    values = {tag: value['entry'] for tag, value in tags.items() if tag not in STRIPS}
    values[259] = entry(259, 3, 1, 7)
    compressed_ifd = align(len(header), 4)
    ifd_bytes = 2 + 12 * (len(values) + 4) + 4
    offsets = align(compressed_ifd + ifd_bytes, 4)
    counts = offsets + 4 * tiles
    pixels = align(counts + 4 * tiles)
    # For one tile TIFF stores each value inline rather than pointing to arrays.
    values[322] = entry(322, 4, 1, tile_width)
    values[323] = entry(323, 4, 1, tile_height)
    values[324] = entry(324, 4, tiles, pixels if tiles == 1 else offsets)
    values[325] = entry(325, 4, tiles, 0 if tiles == 1 else counts)
    order = sorted(values)
    prefix = bytearray(header) + bytes(pixels - len(header))
    ifd = struct.pack('<H', len(order)) + b''.join(values[t] for t in order) + bytes(4)
    prefix[compressed_ifd:compressed_ifd + len(ifd)] = ifd
    strip_pointer = tags[273]['value_at']
    struct.pack_into('<I', prefix, strip_pointer, pixels)
    if tiles == 1:
        offsets = compressed_ifd + 2 + 12 * order.index(324) + 8
        counts = compressed_ifd + 2 + 12 * order.index(325) + 8
    mirrors = tuple((value['value_at'], compressed_ifd + 2 + 12 * order.index(tag) + 8)
                    for tag, value in tags.items()
                    if tag not in LAYOUT and value['size'] <= 4)
    # Fixed tag/type/count and out-of-line offsets must remain the same.
    schema = tuple((tag, value['type'], value['count'],
                    value['value_at'] if value['size'] > 4 else None)
                   for tag, value in tags.items())
    return Plan(len(header), tree.root_at, compressed_ifd, pixels, offsets, counts,
                tiles, tile_width, tile_height, strip_pointer, schema, mirrors, bytes(prefix))


def prepare_frame(plan, current_header):
    """Model native generation of current metadata into the prepared layout.

    Parsing/copying here is an offline reference, not a proposed hot-path hook.
    An actual adapter must bind the producer's field writes to both IFDs.
    """
    require(len(current_header) == plan.source_bytes, 'prefix shape changed')
    tree = ClassicTIFF(current_header)
    tags = tree.root['tags']
    schema = tuple((tag, value['type'], value['count'],
                    value['value_at'] if value['size'] > 4 else None)
                   for tag, value in tags.items())
    require(tree.root_at == plan.raw_ifd and schema == plan.schema, 'metadata schema changed')
    require(scalar(tags, 259) == 1 and scalar(tags, 273) == plan.source_bytes,
            'producer is not generating the expected RAW layout')
    require(scalar(tags, 256) == scalar(ClassicTIFF(plan.seed).root['tags'], 256) and
            scalar(tags, 257) == scalar(ClassicTIFF(plan.seed).root['tags'], 257),
            'geometry changed: rebuild plan')
    prefix = bytearray(plan.seed)
    prefix[:plan.source_bytes] = current_header
    struct.pack_into('<I', prefix, plan.raw_strip_pointer, plan.pixels)
    for source, dest in plan.mirrors:
        prefix[dest:dest + 4] = current_header[source:source + 4]
    return prefix


def raw_file(plan, prefix, raster):
    require(len(prefix) == plan.pixels and struct.unpack_from('<I', prefix, 4)[0] == plan.raw_ifd,
            'RAW root not selected')
    return bytes(prefix) + raster


def finish_compressed(plan, prefix, payload, tile_sizes, write=None):
    """Fill sizes/positions and publish root LAST; no IFD scan or rebuild."""
    require(len(prefix) == plan.pixels, 'unowned prefix length')
    require(struct.unpack_from('<I', prefix, 4)[0] == plan.raw_ifd, 'not pending RAW')
    require(len(tile_sizes) == plan.tiles and all(isinstance(n, int) and 0 < n < 0x80000000
                                                 for n in tile_sizes), 'invalid tile sizes')
    require(sum(tile_sizes) == len(payload) and len(payload) < 0x80000000 - plan.pixels,
            'tile sizes do not match payload')
    # All possible validation failures occur before changing prefix bytes.
    writes = []
    def put(at, value):
        require(0 <= at <= len(prefix) - 4, 'write outside owned prefix')
        struct.pack_into('<I', prefix, at, value)
        writes.append((at, value))
        if write is not None:
            write(at, value)
    position = plan.pixels
    for n, size in enumerate(tile_sizes):
        put(plan.offsets + 4 * n, position)
        put(plan.counts + 4 * n, size)
        position += size
    put(4, plan.compressed_ifd)
    return bytes(prefix) + payload, writes


def verify_metadata(source_header, output):
    """Independent graph check of both roots and every shared opaque value."""
    source = ClassicTIFF(source_header)
    chosen = ClassicTIFF(output)
    for tag, value in source.root['tags'].items():
        if tag in LAYOUT:
            continue
        other = chosen.root['tags'][tag]
        require((value['type'], value['count'], value['raw']) ==
                (other['type'], other['count'], other['raw']), f'metadata changed: {tag}')
    for region in source.protected:
        if region['label'] == 'IFD0 structure':
            continue
        require(source_header[region['start']:region['end']] == output[region['start']:region['end']],
                f"nested/private metadata changed: {region['label']}")
    return True
