"""Offline tests for the relocatable, non-deployable EP83 camera build."""

import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest import mock

if __package__:
    from . import build_ep83_camera as build
else:
    import build_ep83_camera as build


POOL = 0x44F6FE00
DMA_CPU = POOL + build.RUNTIME_DMA
DMA_BUS = DMA_CPU - 0x40000000


class Ep83CameraBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom = build.build_publication.root() / 'out/seg0_c0000000.bin'
        cls.artifacts, cls.manifest = build.build(
            rom=cls.rom, runtime_pool_expected_base=POOL,
            dma_bus=DMA_BUS, expected_count=7, wait_ms=200,
            extra_sources=(build.CONTROL_SOURCE,))

    def test_single_tu_image_is_bounded_and_non_deployable(self):
        manifest = self.manifest
        code = self.artifacts['ep83-camera.bin']
        self.assertTrue(code)
        self.assertEqual(len(code) & 3, 0)
        self.assertLessEqual(len(code), 0x4000)
        self.assertEqual(manifest['runtime_pool']['code_base_expected'], POOL + 0x50000)
        self.assertEqual(manifest['runtime_pool']['code_limit_expected'], POOL + 0x54000)
        self.assertTrue(manifest['single_translation_unit'])
        self.assertEqual(manifest['external_runtime_symbols'], [])
        self.assertEqual(set(manifest['allocated_sections']) - {'.text', '.ARM.exidx'}, set())
        for name in ('deployment_ready', 'adapter_complete', 'hardware_validated',
                     'autorun_generated', 'card_write_performed',
                     'usb_access_performed', 'single_usb_owner_verified',
                     'usb_client_races_closed', 'dma_mapping_verified',
                     'loader_integration_complete', 'cache_publication_verified',
                     'pool_lease_verified'):
            self.assertIs(manifest[name], False, name)
        self.assertTrue(manifest['cold_boot_required'])
        self.assertTrue(manifest['camera_config']['preflight_failclosed'])
        self.assertTrue(manifest['native_control_candidate_compiled'])
        self.assertFalse(manifest['native_control_installed'])

    def test_config_and_private_templates_match_exact_word_abi(self):
        words = struct.unpack('<64I', self.artifacts['ep83-camera-config.bin'])
        self.assertEqual(words[:15], (
            build.CONFIG_MAGIC, build.CONFIG_SCHEMA, build.CONFIG_BYTES,
            POOL, POOL + 0x50000, POOL + 0x54000,
            POOL + 0x54000, POOL + 0x54080, DMA_CPU,
            DMA_BUS, 0x8080, POOL + 0x64800, POOL + 0x64900,
            7, 200,
        ))
        self.assertEqual(words[15:23], (0,) * 8)
        self.assertEqual(words[23:36], tuple(
            self.manifest['symbols'][name] for name in build.CONFIG_OFFSET_SYMBOLS))
        self.assertEqual(words[36:], (0,) * 28)
        for offset in words[23:36]:
            self.assertGreater(offset, 0)
            self.assertEqual(offset & 3, 0)
            self.assertLess(offset, 0x4000)

        private = struct.unpack('<64I', self.artifacts['ep83-camera-private.bin'])
        self.assertEqual(private[:4], (
            build.PRIVATE_MAGIC, build.PRIVATE_SCHEMA, build.PRIVATE_BYTES, 0))
        self.assertEqual(private[4:], (0,) * 60)
        control = struct.unpack('<64I', self.artifacts['ep83-control-state.bin'])
        self.assertEqual(control[:3], (build.CONTROL_MAGIC, build.CONTROL_SCHEMA, 0))
        self.assertEqual(control[3:], (0,) * 61)
        self.assertEqual(self.manifest['runtime_pool']['control_offset'], 0x64A00)

    def test_required_symbols_and_fixed_binding_mode(self):
        symbols = self.manifest['symbols']
        self.assertTrue(build.REQUIRED_SYMBOLS <= symbols.keys())
        self.assertIn('af_ep83_memory_ok', symbols)
        self.assertIn('af_ep83_control_entry', symbols)
        self.assertNotIn('af_ep83_fixed_wait_ops', symbols)
        self.assertEqual(self.manifest['compiler_defines'], [
            'AF_EP83_ENABLE_FIXED_BINDING',
            'AF_EP83_OMIT_FIXED_OPS_FACTORY',
        ])
        document = json.loads(self.artifacts['ep83-camera-symbols.json'])
        self.assertEqual(document['offsets'], symbols)
        self.assertEqual(document['expected_addresses']['af_ep83_camera_entry'],
                         POOL + 0x50000 + symbols['af_ep83_camera_entry'])

    def test_artifact_hashes_and_source_hashes_are_exact(self):
        for name, identity in self.manifest['artifacts'].items():
            data = self.artifacts[name]
            self.assertEqual(identity['bytes'], len(data))
            self.assertEqual(identity['sha256'], hashlib.sha256(data).hexdigest())
        for path, digest in self.manifest['sources'].items():
            self.assertEqual(hashlib.sha256(Path(path).read_bytes()).hexdigest(), digest)
        self.assertEqual(self.manifest['rom_sha256'], build.ep83_boot_plan.ROM_SHA256)
        self.assertTrue(self.manifest['boot_patch_before_images_verified'])

    def test_invalid_runtime_inputs_fail_closed(self):
        symbols = {name: 4 * (index + 1)
                   for index, name in enumerate(build.CONFIG_OFFSET_SYMBOLS)}
        cases = (
            dict(runtime_pool_expected_base=POOL + 64, dma_bus=DMA_BUS,
                 expected_count=7, wait_ms=200),
            dict(runtime_pool_expected_base=POOL, dma_bus=DMA_BUS + 64,
                 expected_count=7, wait_ms=200),
            dict(runtime_pool_expected_base=POOL, dma_bus=DMA_BUS,
                 expected_count=0, wait_ms=200),
            dict(runtime_pool_expected_base=POOL, dma_bus=DMA_BUS,
                 expected_count=7, wait_ms=2001),
        )
        for values in cases:
            with self.subTest(values=values), self.assertRaises(ValueError):
                build._templates(symbols=symbols, **values)
        bad = dict(symbols)
        bad[build.CONFIG_OFFSET_SYMBOLS[0]] = 0
        with self.assertRaisesRegex(ValueError, 'relocatable offset'):
            build._templates(runtime_pool_expected_base=POOL, dma_bus=DMA_BUS,
                             expected_count=7, wait_ms=200, symbols=bad)

    def test_wrong_rom_and_before_image_stop_before_compilation(self):
        rom = bytearray(self.rom.read_bytes())
        rom[-1] ^= 1
        with tempfile.TemporaryDirectory() as directory:
            wrong = Path(directory) / 'wrong.bin'
            wrong.write_bytes(rom)
            with mock.patch.object(build, '_compile') as compile_core:
                with self.assertRaisesRegex(ValueError, 'unsupported ROM hash'):
                    build.build(rom=wrong, runtime_pool_expected_base=POOL,
                                dma_bus=DMA_BUS, expected_count=7, wait_ms=200)
                compile_core.assert_not_called()

            patch = build.ep83_boot_plan.PATCHES[0]
            rom = bytearray(self.rom.read_bytes())
            struct.pack_into('<I', rom, patch['address'] - build.ep83_boot_plan.ROM_BASE,
                             patch['expected_before'] ^ 1)
            before = Path(directory) / 'before.bin'
            before.write_bytes(rom)
            digest = hashlib.sha256(rom).hexdigest()
            with mock.patch.object(build.ep83_boot_plan, 'ROM_SHA256', digest), \
                    mock.patch.object(build, '_compile') as compile_core:
                with self.assertRaisesRegex(ValueError, 'unexpected before-image'):
                    build.build(rom=before, runtime_pool_expected_base=POOL,
                                dma_bus=DMA_BUS, expected_count=7, wait_ms=200)
                compile_core.assert_not_called()

    def test_optional_extra_source_is_in_same_image(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'native_control_once.c'
            source.write_text(
                '#include <stdint.h>\n'
                'int32_t af_ep83_native_control_marker(uint32_t v) { return (int32_t)(v ^ 7u); }\n')
            artifacts, manifest = build.build(
                rom=self.rom, runtime_pool_expected_base=POOL,
                dma_bus=DMA_BUS, expected_count=1, wait_ms=1,
                extra_sources=(source,))
            self.assertIn('af_ep83_native_control_marker', manifest['symbols'])
            self.assertGreater(len(artifacts['ep83-camera.bin']), 0)
            self.assertIn(str(source.resolve()), manifest['sources'])

    def test_extra_source_cannot_add_data_or_external_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rodata = root / 'bad_rodata.c'
            rodata.write_text(
                '#include <stdint.h>\n'
                'const volatile uint32_t af_bad_words[2] = {1u, 2u};\n'
                'uint32_t af_bad_read(void) { return af_bad_words[0]; }\n')
            with self.assertRaisesRegex(ValueError, 'allocated section'):
                build.build(rom=self.rom, runtime_pool_expected_base=POOL,
                            dma_bus=DMA_BUS, expected_count=1, wait_ms=1,
                            extra_sources=(rodata,))

            external = root / 'bad_external.c'
            external.write_text(
                '#include <stdint.h>\n'
                'extern int32_t af_missing_runtime(void);\n'
                'int32_t af_bad_call(void) { return af_missing_runtime(); }\n')
            with self.assertRaisesRegex(ValueError, 'external runtime symbols'):
                build.build(rom=self.rom, runtime_pool_expected_base=POOL,
                            dma_bus=DMA_BUS, expected_count=1, wait_ms=1,
                            extra_sources=(external,))

    def test_existing_output_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'existing'
            output.mkdir()
            sentinel = output / 'sentinel'
            sentinel.write_bytes(b'keep')
            with mock.patch.object(build, 'build') as build_core:
                with self.assertRaises(FileExistsError):
                    build.write_build(
                        output, rom=self.rom, runtime_pool_expected_base=POOL,
                        dma_bus=DMA_BUS, expected_count=7, wait_ms=200)
                build_core.assert_not_called()
            self.assertEqual(sentinel.read_bytes(), b'keep')


if __name__ == '__main__':
    unittest.main()
