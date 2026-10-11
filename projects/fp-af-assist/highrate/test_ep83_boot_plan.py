"""Offline-only checks for the non-deployable EP83 cold-boot plan."""

import hashlib
import contextlib
import io
from pathlib import Path
import struct
import tempfile
import unittest
from unittest import mock

if __package__:
    from . import ep83_boot_plan as plan
else:
    import ep83_boot_plan as plan


class Ep83BootPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom = (plan.project_root() / 'out/seg0_c0000000.bin').read_bytes()

    def test_verified_manifest_is_ordered_and_non_deployable(self):
        result = plan.build_plan(self.rom)
        self.assertEqual(result['rom_sha256'], plan.ROM_SHA256)
        self.assertEqual([(p['sequence'], p['address'], p['expected_before'],
                           p['candidate_after']) for p in result['patch_order']], [
            (1, 0xC01E5880, 0x4DF0E92D, 0x47702000),
            (2, 0xC07E2800, 0x00000002, 0x00000001),
        ])
        for key in ('deployment_ready', 'adapter_complete',
                    'firmware_adapter_complete', 'ownership_verified',
                    'lifecycle_verified', 'preflight_may_succeed',
                    'autorun_generated', 'card_write_performed',
                    'usb_access_performed'):
            self.assertIs(result[key], False, key)
        self.assertTrue(result['offline_only'])
        self.assertTrue(result['plan_only'])
        self.assertTrue(result['requires']['cold_boot'])
        self.assertTrue(result['requires'][
            'usb_cable_unplugged_until_boot_patches_and_worker_are_ready'])
        self.assertTrue(result['requires']['existing_ep83_descriptor_bulk_patches'])
        self.assertTrue(result['requires'][
            'one_serial_worker_task_owns_all_ep83_start_wait_trb_access'])
        self.assertTrue(result['requires']['explicit_dma_buffer_lease'])
        self.assertTrue(result['requires']['rollback_requires_reboot_without_candidate_patches'])
        self.assertEqual(result['requires']['dma_alignment_bytes'], 64)
        self.assertIn('mode1_wait_completion_rearms_bulk_out',
                      {item['id'] for item in result['unresolved_blockers']})

    def test_wrong_rom_hash_is_rejected_before_planning(self):
        damaged = bytearray(self.rom)
        damaged[-1] ^= 1
        with self.assertRaisesRegex(ValueError, 'unsupported ROM hash'):
            plan.build_plan(damaged)

    def test_each_wrong_before_image_is_rejected(self):
        for patch in plan.PATCHES:
            with self.subTest(address=hex(patch['address'])):
                damaged = bytearray(self.rom)
                offset = patch['address'] - plan.ROM_BASE
                struct.pack_into('<I', damaged, offset, patch['expected_before'] ^ 1)
                digest = hashlib.sha256(damaged).hexdigest()
                with mock.patch.object(plan, 'ROM_SHA256', digest):
                    with self.assertRaisesRegex(ValueError, 'unexpected before-image'):
                        plan.build_plan(damaged)

    def test_existing_or_dangling_output_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'plan.json'
            output.write_text('preserve')
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                plan.main(['--output', str(output)])
            self.assertEqual(output.read_text(), 'preserve')
            missing = Path(directory) / 'missing.json'
            link = Path(directory) / 'dangling.json'
            link.symlink_to(missing)
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                plan.main(['--output', str(link)])
            self.assertTrue(link.is_symlink())
            self.assertFalse(missing.exists())


if __name__ == '__main__':
    unittest.main()
