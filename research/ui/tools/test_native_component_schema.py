#!/usr/bin/env python3
"""Offline schema checks; all native execution uses synthetic RAM only."""
import argparse
from collections import Counter
import json
from pathlib import Path
import struct
import sys
import unittest

import native_component_schema as schema


class Schemas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.capture = schema.Capture(IMAGE)
        cls.report = cls.capture.scan()
        cls.components = cls.report['components']

    def test_all_eighteen_components(self):
        self.assertEqual(set(self.components), schema.KINDS)
        self.assertEqual(self.report['missing'], [])
        self.assertEqual(self.report['failures'], [])

    def test_provenance_is_not_all_native_execution(self):
        counts = Counter(c['provenance']['method'] for c in self.components.values())
        self.assertEqual(counts, {'native_constructor_prefix_capture': 14,
                                  'verified_static_argument_window': 4})

    def test_drawable_common_tail(self):
        for name, declared in (('drawImage', 7), ('drawRect', 9), ('drawText', 30)):
            comp = self.components[name]
            self.assertEqual((comp['declared_count'], comp['count']), (declared, declared + 2))
            self.assertEqual([(p['name'], p['type']) for p in comp['properties'][-2:]],
                             [('rect', 5), ('layout', 10)])

    def test_descriptors_are_contiguous_and_typed(self):
        for comp in self.components.values():
            self.assertEqual([p['index'] for p in comp['properties']], list(range(comp['count'])))
            self.assertTrue(all(0 <= p['type'] <= 14 for p in comp['properties']))
            table = int(comp['property_table'], 16)
            for prop in comp['properties'][:comp['declared_count']]:
                self.assertEqual(int(prop['descriptor_address'], 16), table + 12 * prop['index'])

    def test_reference_types(self):
        def types(name):
            return {p['name']: p['type'] for p in self.components[name]['properties']}
        self.assertEqual(types('controlFocus')['object-id'], 14)
        self.assertEqual(types('controlAppVariable')['object-id'], 14)
        self.assertEqual(types('controlAppVariable')['destination-variable'], 11)
        self.assertEqual(types('drawText')['text'], 11)

    def test_custom_clip_is_not_normal_properties(self):
        self.assertNotIn('animationClip', self.components)
        self.assertEqual(len(self.report['custom_record_decoders']), 1)

    def test_exact_pin(self):
        with self.assertRaisesRegex(ValueError, 'pinned'):
            schema.Capture(IMAGE[:-1])
        broken = bytearray(IMAGE)
        broken[0] ^= 1
        with self.assertRaisesRegex(ValueError, 'pinned'):
            schema.Capture(broken)

    def test_string_bounds(self):
        for address in (schema.BASE - 1, schema.BASE + len(IMAGE)):
            with self.assertRaisesRegex(ValueError, 'outside'):
                self.capture.string(address)

    def test_property_bounds(self):
        with self.assertRaisesRegex(ValueError, 'outside'):
            self.capture.property(schema.BASE + len(IMAGE) - 11, 0)

    def test_static_constructor_identity(self):
        with self.assertRaisesRegex(ValueError, 'constructor mismatch'):
            schema.static_capture(IMAGE, 'drawText', 0xC05FE1AB)

    def test_static_count_tamper(self):
        broken = bytearray(IMAGE)
        # movs r1,#30 becomes #29; helper must not trust configured expectations.
        broken[0xC05FE1FC - schema.BASE] = 29
        with self.assertRaisesRegex(ValueError, 'arguments differ'):
            schema.static_capture(broken, 'drawText', 0xC05FE1A9)

    def test_static_call_tamper(self):
        broken = bytearray(IMAGE)
        struct.pack_into('<I', broken, 0xC05FE1FE - schema.BASE, 0xBF00BF00)
        with self.assertRaisesRegex(ValueError, 'incomplete argument window'):
            schema.static_capture(broken, 'drawText', 0xC05FE1A9)

    def test_scope_does_not_claim_renderer(self):
        for name in ('renderer', 'UI events', 'camera', 'property registration'):
            self.assertIn(name, self.report['not_executed'])


def main():
    global IMAGE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seg0', type=Path, required=True)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    IMAGE = args.seg0.read_bytes()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Schemas)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {'input_sha256': schema.PIN, 'tests_run': result.testsRun,
              'failures': len(result.failures), 'errors': len(result.errors),
              'skipped': len(result.skipped), 'passed': result.wasSuccessful(),
              'native_constructor_prefixes': 14, 'static_argument_windows': 4,
              'camera_used': False, 'runtime_ready': False}
    if args.report:
        with args.report.open('x') as out:
            json.dump(report, out, indent=2)
            out.write('\n')
    print(json.dumps(report, indent=2))
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(main())
