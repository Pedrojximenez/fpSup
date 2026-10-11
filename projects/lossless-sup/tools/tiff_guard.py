"""Bounded TIFF metadata graph and first-trial FHD source validation; no I/O."""
import hashlib
import struct

TYPE_BYTES = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4, 10: 8, 11: 4, 12: 8}
POINTERS = {330: "SubIFD", 34665: "Exif", 34853: "GPS", 40965: "Interop"}
MAX_FILE = 32 * 1024 * 1024


class Rejected(ValueError):
    """Unsupported source shape or an unproven metadata write."""


def require(condition, message):
    if not condition:
        raise Rejected(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def overlap(a, b):
    return a[0] < b[1] and b[0] < a[1]


class ClassicTIFF:
    """Read classic little-endian TIFF without following unbounded offsets.

    All out-of-line values are protected, including opaque MakerNote/private
    blobs. Exif/GPS/Interop/SubIFD links and nested next-IFD chains are walked.
    Nested image storage is rejected rather than assuming its bytes survive.
    """
    def __init__(self, data):
        self.data = data
        require(8 <= len(data) <= MAX_FILE, 'file size outside host-trial bounds')
        require(data[:4] == b'II*\0', 'only classic little-endian TIFF 42 supported')
        self.root_at = struct.unpack_from('<I', data, 4)[0]
        self.nodes = []
        self.protected = []
        self.visited = set()
        self.root = self.walk(self.root_at, 'IFD0', 0)
        require(self.root['next'] == 0, 'multiple top-level image IFDs unsupported')

    def bounded(self, start, size, label):
        require(start >= 0 and size >= 0 and start + size <= len(self.data),
                f'{label}: range outside file')
        return self.data[start:start + size]

    def walk(self, offset, path, depth):
        require(8 <= offset < len(self.data), f'{path}: invalid IFD offset')
        require(depth <= 16 and len(self.nodes) < 32, 'IFD graph exceeds bounds')
        require(offset not in self.visited, f'{path}: cyclic/shared IFD unsupported')
        self.visited.add(offset)
        count = struct.unpack('<H', self.bounded(offset, 2, path))[0]
        require(0 < count <= 4096, f'{path}: empty/oversized IFD unsupported')
        length = 2 + count * 12 + 4
        self.bounded(offset, length, path)
        self.protected.append({'start': offset, 'end': offset + length,
                               'label': path + ' structure', 'nested': depth > 0})
        tags = {}
        for index in range(count):
            at = offset + 2 + index * 12
            tag, kind, n, value = struct.unpack_from('<HHII', self.data, at)
            require(tag not in tags, f'{path}: duplicate TIFF tag {tag}')
            require(kind in TYPE_BYTES and n > 0,
                    f'{path}/{tag}: unsupported type/count {kind}/{n}')
            size = TYPE_BYTES[kind] * n
            value_at = value if size > 4 else at + 8
            raw = self.bounded(value_at, size, f'{path}/{tag}')
            tags[tag] = {'type': kind, 'count': n, 'value_at': value_at,
                         'size': size, 'raw': raw,
                         'entry': self.data[at:at + 12]}
            if size > 4:
                self.protected.append({'start': value_at, 'end': value_at + size,
                                       'label': f'{path} tag {tag} value',
                                       'nested': depth > 0})
        nxt = struct.unpack_from('<I', self.data, offset + length - 4)[0]
        node = {'path': path, 'offset': offset, 'length': length,
                'next': nxt, 'tags': tags}
        self.nodes.append(node)
        if depth > 0:
            require(not ({273, 279, 324, 325, 513, 514} & tags.keys()),
                    f'{path}: nested image storage unsupported')
        for tag, name in POINTERS.items():
            if tag not in tags:
                continue
            entry = tags[tag]
            require(entry['type'] == 4 and entry['count'] <= 64,
                    f'{path}/{name}: only bounded LONG IFD pointers supported')
            require(tag == 330 or entry['count'] == 1,
                    f'{path}/{name}: multiple pointers unsupported')
            children = struct.unpack('<' + 'I' * entry['count'], entry['raw'])
            for index, child in enumerate(children):
                self.walk(child, f'{path}/{name}[{index}]', depth + 1)
        if nxt:
            require(depth > 0, 'multiple top-level image IFDs unsupported')
            self.walk(nxt, path + '/next', depth + 1)
        return node


def integers(tags, tag):
    require(tag in tags, f'missing required tag {tag}')
    entry = tags[tag]
    require(entry['type'] in (1, 3, 4), f'tag {tag}: integer type required')
    fmt = {1: 'B', 3: 'H', 4: 'I'}[entry['type']]
    return struct.unpack('<' + fmt * entry['count'], entry['raw'])


def scalar(tags, tag, default=None):
    if tag not in tags and default is not None:
        return default
    values = integers(tags, tag)
    require(len(values) == 1, f'tag {tag}: scalar required')
    return values[0]


def validate_fhd(data):
    tree = ClassicTIFF(data)
    t = tree.root['tags']
    require(not ({322, 323, 324, 325} & t.keys()), 'source already has tile tags')
    width, height = scalar(t, 256), scalar(t, 257)
    require((width, height) == (1936, 1090), 'first trial supports FHD raster only')
    require(scalar(t, 258) == 12 and scalar(t, 259) == 1,
            'source must be uncompressed RAW12')
    require(t[259]['type'] == 3 and t[259]['count'] == 1,
            'builder requires SHORT scalar Compression tag')
    require(scalar(t, 262) == 32803 and scalar(t, 277) == 1 and
            scalar(t, 284, 1) == 1 and scalar(t, 266, 1) == 1,
            'only single-sample chunky CFA, normal fill order supported')
    start, bytecount = scalar(t, 273), scalar(t, 279)
    require(scalar(t, 278) == height, 'single full-height strip required')
    packed_bytes = width * height * 3 // 2
    # Verified stock size rule (projects/open-gate/build/og4k_offline/
    # og4k_sizes.py:raw12_bytes): final width rounds to 12 pixels, then four
    # bytes. FHD has 12 non-image bytes after its last raster row. The original
    # builder encodes raster samples only; report this declared strip padding.
    row_bytes = (width * 3 // 2 + 3) & ~3
    final_row = (((width + 11) // 12 * 12 * 3 // 2) + 3) & ~3
    stock_bytes = (height - 1) * row_bytes + final_row
    require(row_bytes == width * 3 // 2 and bytecount in (packed_bytes, stock_bytes),
            'StripByteCounts/row stride does not match known RAW12 layout')
    require(8 <= start <= 1024 * 1024, 'header outside trial bounds')
    tree.bounded(start, bytecount, 'RAW strip')
    tail = data[start + bytecount:]
    require(len(tail) < 512 and not any(tail), 'unexpected non-padding trailing data')
    for region in tree.protected:
        require(8 <= region['start'] < region['end'] <= start,
                region['label'] + ': metadata outside retained header')

    return tree, width, height, start, bytecount, packed_bytes
