#!/usr/bin/env python3
"""HOST ONLY: append a new TIFF IFD instead of overwriting original metadata.

This is not the camera's fixed-header writer. It reuses the research JPEG
encoder unchanged but retains every original header byte except TIFF offset
4..8. No existing file is overwritten; first trial is FHD RAW12 only.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import struct
import sys

sys.dont_write_bytecode = True
from tiff_guard import require, validate_fhd, MAX_FILE

HOST_ONLY_APPEND = True
_encoder_dir = None


def configure_encoder(directory):
    global _encoder_dir
    directory = Path(directory).resolve(strict=True)
    for name in ('ljenc.py', 'ljpeg.py', 'ljcost.py', 'tilegeom.py'):
        require((directory / name).is_file(), f'missing existing encoder dependency: {name}')
    _encoder_dir = directory


def load_encoder(name):
    require(_encoder_dir is not None, 'explicit encoder directory required')
    sys.path.insert(0, str(_encoder_dir))
    spec = importlib.util.spec_from_file_location('trial_safe_' + name, _encoder_dir / (name + '.py'))
    require(spec is not None and spec.loader is not None, 'cannot load existing encoder')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build(src, dst, tw=512, th=368, predictor=1, file_align=512):
    require((tw, th, predictor, file_align) == (512, 368, 1, 512),
            'host first trial requires tile512x368/predictor1/align512')
    source, output = Path(src).resolve(strict=True), Path(dst).resolve()
    require(source != output and not output.exists(), 'refusing to overwrite source/existing output')
    require(source.stat().st_size <= MAX_FILE, 'source exceeds FHD trial bounds')
    data = source.read_bytes()
    tree, width, height, old_offset, _, packed_bytes = validate_fhd(data)
    t = tree.root['tags']
    import numpy as np
    encoder = load_encoder('ljenc')
    geometry = load_encoder('tilegeom')
    packed = np.frombuffer(data, np.uint8, count=packed_bytes, offset=old_offset)
    packed = packed.reshape(-1, 3).astype(np.uint16)
    pixels = np.empty(width * height, np.uint16)
    pixels[0::2] = (packed[:, 0] << 4) | (packed[:, 1] >> 4)
    pixels[1::2] = ((packed[:, 1] & 15) << 8) | packed[:, 2]
    padded, tile_count, padded_pixels = geometry.pad_image(pixels.reshape(height, width), tw, th)
    blobs = [encoder.encode_tile(padded[y:y + th, x:x + tw], 12, predictor)
             for y in range(0, padded.shape[0], th) for x in range(0, padded.shape[1], tw)]

    entries = {tag: entry['entry'] for tag, entry in t.items() if tag not in {273, 278, 279}}
    count = len(entries) + 4
    ifd_bytes = 2 + count * 12 + 4
    need = ifd_bytes + 8 * tile_count
    ifd_at = old_offset
    offset_table = ifd_at + ifd_bytes
    count_table = offset_table + 4 * tile_count
    raw_offset = (ifd_at + need + file_align - 1) & -file_align
    header = bytearray(data[:old_offset])
    header.extend(bytes(raw_offset - old_offset))
    offsets, position = [], raw_offset
    for blob in blobs:
        offsets.append(position)
        position += len(blob)

    def tag_entry(tag, kind, n, value):
        return struct.pack('<HHII', tag, kind, n, value)

    entries[259] = tag_entry(259, 3, 1, 7)
    entries[322] = tag_entry(322, 4, 1, tw)
    entries[323] = tag_entry(323, 4, 1, th)
    entries[324] = tag_entry(324, 4, tile_count, offset_table)
    entries[325] = tag_entry(325, 4, tile_count, count_table)
    new_ifd = struct.pack('<H', count) + b''.join(entries[tag] for tag in sorted(entries)) + bytes(4)
    require(len(entries) == count and len(new_ifd) == ifd_bytes, 'new IFD size mismatch')
    header[ifd_at:ifd_at + ifd_bytes] = new_ifd
    struct.pack_into('<' + 'I' * tile_count, header, offset_table, *offsets)
    struct.pack_into('<' + 'I' * tile_count, header, count_table, *map(len, blobs))
    struct.pack_into('<I', header, 4, ifd_at)
    require(header[:4] == data[:4] and header[8:old_offset] == data[8:old_offset],
            'old header changed beyond its root pointer')
    require(all(data[r['start']:r['end']] == header[r['start']:r['end']]
                for r in tree.protected), 'protected metadata modified')
    stored_size = (position + file_align - 1) & -file_align
    with output.open('xb') as stream:
        stream.write(header)
        for blob in blobs:
            stream.write(blob)
        stream.write(bytes(stored_size - position))
    require(source.read_bytes() == data, 'source changed during encoding')
    return {'W': width, 'H': height, 'tiles': tile_count, 'tile': [tw, th],
            'ifd_at': ifd_at, 'need': need, 'insize': len(data), 'outsize': position,
            'stored_size': stored_size, 'predictor': predictor, 'padpx': padded_pixels,
            'input_raw_offset': old_offset, 'output_raw_offset': raw_offset,
            'header_growth': raw_offset - old_offset, 'host_only_append': True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--encoder-dir', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    configure_encoder(args.encoder_dir)
    print(json.dumps(build(args.source, args.output), indent=2))
