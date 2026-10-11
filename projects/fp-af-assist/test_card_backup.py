"""Offline filesystem fixtures; no diskutil, card, USB or camera access."""
import hashlib
from pathlib import Path
import tempfile
import unittest

from highrate.card_backup import backup, mounted_card_identity


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='fp-card-backup-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.card = self.root / 'card'
        self.card.mkdir()
        self.output = self.root / 'backup'
        self.identity = lambda _: {'DeviceIdentifier': 'fixture', 'VolumeUUID': 'fixture-only'}

    def run_backup(self):
        return backup(self.card, self.output, identity_reader=self.identity)

    def test_exact_two_file_copy_sha_readback_no_other_card_changes(self):
        files = {'AutoRun.txt': b'old autorun\r\n', 'VSHL.BIN': b'VBIN\0old payload'}
        for name, data in files.items():
            (self.card / name).write_bytes(data)
        (self.card / 'DCIM').mkdir()
        report = self.run_backup()
        for name, data in files.items():
            self.assertEqual((self.output / name).read_bytes(), data)
            self.assertEqual((self.card / name).read_bytes(), data)
            self.assertEqual(report['files'][name]['sha256'], hashlib.sha256(data).hexdigest())
        self.assertFalse((self.output / 'DCIM').exists())
        self.assertTrue(report['backup_readback_verified'])
        self.assertFalse(report['card_modified'])

    def test_absent_files_recorded_and_empty_file_preserved(self):
        (self.card / 'AutoRun.txt').touch()
        report = self.run_backup()
        self.assertEqual(report['files']['VSHL.BIN'], {'present': False})
        self.assertTrue(report['files']['AutoRun.txt']['present'])
        self.assertEqual(report['files']['AutoRun.txt']['bytes'], 0)

    def test_symlink_or_device_refused_before_output(self):
        (self.card / 'AutoRun.txt').symlink_to(self.root / 'missing')
        with self.assertRaises((OSError, ValueError)):
            self.run_backup()
        self.assertFalse(self.output.exists())

    def test_no_backup_overwrite_or_backup_on_card(self):
        self.output.mkdir()
        with self.assertRaises(ValueError):
            self.run_backup()
        with self.assertRaises(ValueError):
            backup(self.card, self.card / 'backup', identity_reader=self.identity)

    def test_card_swap_refused_before_output(self):
        calls = []
        def unstable(_):
            calls.append(1)
            return {'id': len(calls)}
        with self.assertRaises(ValueError):
            backup(self.card, self.output, identity_reader=unstable)
        self.assertFalse(self.output.exists())

    def test_real_target_validator_rejects_broad_or_unmounted_paths(self):
        for path in ('/', '/Users/dido', '/Volumes', '.', '/Volumes/not-a-mounted-card-ep83'):
            with self.assertRaises(ValueError):
                mounted_card_identity(Path(path))


if __name__ == '__main__':
    unittest.main()
