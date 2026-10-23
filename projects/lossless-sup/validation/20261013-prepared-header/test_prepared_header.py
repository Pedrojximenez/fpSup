"""Offline feasibility: same prepared prefix supports RAW and real JPEG tiles."""
from pathlib import Path
import hashlib
import json
import struct
import tempfile
import unittest

import native_builder_trace as native
import prototype as P
from tiff_guard import ClassicTIFF, scalar, Rejected

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SAMPLES = ROOT / 'projects/lossless-sup/validation/20261012-pipeline-cost/final-normal-60p-frames'


class PreparedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import sys
        sys.path.insert(0, str(ROOT / 'fpSup/lossless/native'))
        from test_trailer import encode_stock, STOCK
        cls.source_path = STOCK
        cls.stock, cls.payload, cls.sizes = encode_stock()
        cls.header = cls.stock[:0x13400]
        cls.plan = P.make_plan(cls.header, 512, 368)

    def prefix(self, header=None):
        return P.prepare_frame(self.plan, self.header if header is None else header)

    def decode_equal(self, source, output):
        import rawpy
        with tempfile.TemporaryDirectory(prefix='fpl-prepared-header-') as tmp:
            path = Path(tmp) / 'candidate.DNG'
            path.write_bytes(output)
            with rawpy.imread(str(source)) as a, rawpy.imread(str(path)) as b:
                self.assertEqual(a.raw_image.shape, b.raw_image.shape)
                self.assertTrue((a.raw_image == b.raw_image).all(), 'raw samples differ')

    def test_same_prefix_is_initially_valid_raw(self):
        output = P.raw_file(self.plan, self.prefix(), self.stock[0x13400:])
        tree = ClassicTIFF(output)
        self.assertEqual(scalar(tree.root['tags'], 259), 1)
        self.assertEqual(scalar(tree.root['tags'], 273), self.plan.pixels)
        self.assertEqual(set(tree.root['tags']), set(ClassicTIFF(self.header).root['tags']))
        self.assertEqual(output[self.plan.pixels:], self.stock[0x13400:])
        self.assertTrue(P.verify_metadata(self.header, output))
        self.decode_equal(self.source_path, output)

    def test_completion_only_updates_two_tables_and_root(self):
        before = bytes(self.prefix())
        prefix = bytearray(before)
        published = []
        def observe(at, value):
            if at != 4:
                self.assertEqual(struct.unpack_from('<I', prefix, 4)[0], self.plan.raw_ifd)
            published.append(at)
        output, writes = P.finish_compressed(self.plan, prefix, self.payload, self.sizes, observe)
        self.assertEqual(len(writes), 2 * len(self.sizes) + 1)
        self.assertEqual(published[-1], 4)
        self.assertEqual(published.count(4), 1)
        self.assertTrue(all(at % 4 == 0 for at in published))
        allowed = {i for at in published for i in range(at, at + 4)}
        self.assertTrue(all(a == b or n in allowed for n, (a, b) in enumerate(zip(before, prefix))))
        self.assertEqual(output[self.plan.pixels:], self.payload)
        tags = ClassicTIFF(output).root['tags']
        self.assertEqual(scalar(tags, 259), 7)
        self.assertEqual(scalar(tags, 322), 512)
        self.assertEqual(scalar(tags, 323), 368)
        self.assertFalse(P.STRIPS & tags.keys())
        self.assertTrue(P.verify_metadata(self.header, output))
        self.decode_equal(self.source_path, output)

    def test_real_camera_payload_is_unchanged_and_decodes_identically(self):
        compressed = (SAMPLES / '000002.DNG').read_bytes()
        tags = ClassicTIFF(compressed).root['tags']
        sizes = struct.unpack('<' + 'I' * tags[325]['count'], tags[325]['raw'])
        offsets = struct.unpack('<' + 'I' * tags[324]['count'], tags[324]['raw'])
        payload = b''.join(compressed[at:at + n] for at, n in zip(offsets, sizes))
        header = bytearray(compressed[:0x13400])
        struct.pack_into('<I', header, 4, 8)
        plan = P.make_plan(header, scalar(tags, 322), scalar(tags, 323))
        output, _ = P.finish_compressed(plan, P.prepare_frame(plan, header), payload, sizes)
        self.assertEqual(output[plan.pixels:], payload)
        self.assertTrue(P.verify_metadata(header, output))
        self.decode_equal(SAMPLES / '000002.DNG', output)
        (HERE / 'real-camera-prepared.DNG').write_bytes(output)
        (HERE / 'prototype-results.json').write_text(json.dumps(dict(
            source=str(SAMPLES / '000002.DNG'), source_sha256=hashlib.sha256(compressed).hexdigest(),
            prototype_sha256=hashlib.sha256(output).hexdigest(),
            raw_ifd=plan.raw_ifd, compressed_ifd=plan.compressed_ifd,
            header_bytes=plan.pixels, original_header_bytes=plan.source_bytes,
            header_growth=plan.pixels-plan.source_bytes, tiles=plan.tiles,
            completion_logical_word_writes=2*plan.tiles+1,
            all_metadata_preserved=True, payload_identical=True, decoded_samples_identical=True,
            camera_ready=False, installed_hook=False,
            scope='host feasibility only; no native allocation, scheduling or CPU benchmark'), indent=2)+'\n')

    def test_inline_and_nested_current_frame_metadata_are_not_frozen(self):
        current = bytearray(self.header)
        original = ClassicTIFF(current)
        white = original.root['tags'][50717]
        self.assertLessEqual(white['size'], 4)
        struct.pack_into('<I', current, white['value_at'], 4094)
        exif = next(node for node in original.nodes if '/Exif' in node['path'])
        exposure = exif['tags'][33434]
        struct.pack_into('<II', current, exposure['value_at'], 7, 1000)
        output, _ = P.finish_compressed(self.plan, self.prefix(current), self.payload, self.sizes)
        chosen = ClassicTIFF(output)
        self.assertEqual(scalar(chosen.root['tags'], 50717), 4094)
        self.assertEqual(next(n for n in chosen.nodes if '/Exif' in n['path'])['tags'][33434]['raw'],
                         struct.pack('<II', 7, 1000))
        self.assertTrue(P.verify_metadata(current, output))

    def test_malformed_completion_has_zero_writes_and_keeps_raw(self):
        for payload, sizes in ((self.payload, self.sizes[:-1]), (self.payload, [0]*len(self.sizes)),
                               (self.payload[:-1], self.sizes), (b'', [])):
            with self.subTest(sizes=sizes[:2]):
                prefix, events = self.prefix(), []
                before = bytes(prefix)
                with self.assertRaises(Rejected):
                    P.finish_compressed(self.plan, prefix, payload, sizes, lambda a,v: events.append(a))
                self.assertEqual(bytes(prefix), before)
                self.assertEqual(events, [])
                self.assertEqual(struct.unpack_from('<I', prefix, 4)[0], 8)

    def test_geometry_and_schema_changes_require_new_plan(self):
        for tag, atdelta, value in ((256, 8, 1920), (50717, 4, 2)):
            header = bytearray(self.header)
            t = ClassicTIFF(header).root['tags'][tag]
            # Inline source entry starts eight bytes before its value.
            struct.pack_into('<I', header, t['value_at'] - 8 + atdelta, value)
            with self.subTest(tag=tag), self.assertRaises(Rejected):
                self.prefix(header)

    def test_unknown_inline_metadata_is_mirrored_too(self):
        # Keep the record shape but replace Orientation with an unused sorted
        # tag 275. This demonstrates that metadata mapping is not a whitelist.
        header = bytearray(self.header)
        original = ClassicTIFF(header).root['tags'][274]
        struct.pack_into('<H', header, original['value_at'] - 8, 275)
        plan = P.make_plan(header, 512, 368)
        current = bytearray(header)
        struct.pack_into('<H', current, original['value_at'], 13)
        output, _ = P.finish_compressed(plan, P.prepare_frame(plan, current), self.payload, self.sizes)
        self.assertEqual(scalar(ClassicTIFF(output).root['tags'], 275), 13)
        self.assertTrue(P.verify_metadata(current, output))

    def test_single_tile_uses_inline_values(self):
        header = bytearray(self.header)
        tags = ClassicTIFF(header).root['tags']
        for tag, value in ((256, 32), (257, 16), (278, 16), (279, 768)):
            struct.pack_into('<I', header, tags[tag]['value_at'], value)
        plan = P.make_plan(header, 32, 16)
        output, _ = P.finish_compressed(plan, P.prepare_frame(plan, header), b'\x01'*16, [16])
        tags = ClassicTIFF(output).root['tags']
        self.assertEqual(scalar(tags, 324), plan.pixels)
        self.assertEqual(scalar(tags, 325), 16)

    def test_maximum_160_tile_plan_and_bounds(self):
        plan = P.make_plan(self.header, 128, 112)
        self.assertEqual(plan.tiles, 160)
        self.assertEqual(plan.pixels-plan.source_bytes, 2048)
        output, writes = P.finish_compressed(plan, P.prepare_frame(plan, self.header),
                                             bytes(640), [4]*160)
        self.assertEqual(len(writes), 321)
        self.assertTrue(all(a%4 == 0 and a+4 <= plan.pixels for a,v in writes))
        tags = ClassicTIFF(output).root['tags']
        offsets = struct.unpack('<160I', tags[324]['raw'])
        self.assertEqual(offsets, tuple(plan.pixels+4*i for i in range(160)))
        self.assertTrue(P.verify_metadata(self.header, output))
        with self.assertRaises(Rejected):
            P.make_plan(self.header, 32, 16)

    def broken_module(self, name, old, new):
        import importlib.util
        import sys
        source = (HERE / 'prototype.py').read_text()
        self.assertEqual(source.count(old), 1)
        # Compile an isolated source variant; never edit the shared file.
        from types import ModuleType
        module = ModuleType(name)
        module.__file__ = str(HERE / 'prototype.py')
        sys.modules[name] = module
        self.addCleanup(sys.modules.pop, name, None)
        exec(compile(source.replace(old, new), module.__file__, 'exec'), module.__dict__)
        return module

    def test_mutation_publishing_root_early_is_detected(self):
        bad = self.broken_module('early_root_mutation',
            '    position = plan.pixels\n',
            '    put(4, plan.compressed_ifd)\n    position = plan.pixels\n')
        prefix = self.prefix()
        def observe(at, value):
            if at != 4:
                self.assertEqual(struct.unpack_from('<I', prefix, 4)[0], self.plan.raw_ifd)
        with self.assertRaises(AssertionError):
            bad.finish_compressed(self.plan, prefix, self.payload, self.sizes, observe)

    def test_mutation_freezing_inline_metadata_is_detected(self):
        bad = self.broken_module('frozen_metadata_mutation',
            '    for source, dest in plan.mirrors:\n', '    for source, dest in ():\n')
        current = bytearray(self.header)
        tag = ClassicTIFF(current).root['tags'][50717]
        struct.pack_into('<I', current, tag['value_at'], 4094)
        output, _ = P.finish_compressed(self.plan, bad.prepare_frame(self.plan, current),
                                       self.payload, self.sizes)
        with self.assertRaisesRegex(Rejected, 'metadata changed: 50717'):
            P.verify_metadata(current, output)


class NativeTests(unittest.TestCase):
    def test_actual_rom_raw_branch_and_registers(self):
        self.assertTrue(native.verify(native.trace(False)))

    def test_actual_rom_tile_branch_and_registers(self):
        self.assertTrue(native.verify(native.trace(True)))


if __name__ == '__main__':
    unittest.main()
