#!/usr/bin/env python3
"""Back up only a selected test card's AutoRun.txt and VSHL.BIN. Never writes the card."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import stat
import subprocess

TARGETS = {'AutoRun.txt': 1024 * 1024, 'VSHL.BIN': 16 * 1024 * 1024}


def _hash(data):
    return hashlib.sha256(data).hexdigest()


def mounted_card_identity(volume):
    """Resolve an explicitly named external physical volume without changing it."""
    volume = Path(volume)
    if not volume.is_absolute() or volume.parent != Path('/Volumes') or volume.is_symlink():
        raise ValueError('select one explicit /Volumes/<test-card> directory, not a symlink')
    if not volume.is_dir() or volume.resolve() != volume:
        raise ValueError('test card is not mounted at the exact selected path')
    raw = subprocess.run(['diskutil', 'info', '-plist', str(volume)], check=True,
                         capture_output=True).stdout
    info = plistlib.loads(raw)
    if (info.get('MountPoint') != str(volume) or info.get('Internal') is not False or
            info.get('VirtualOrPhysical') != 'Physical' or
            not isinstance(info.get('DeviceIdentifier'), str)):
        raise ValueError('selected path is not a verified external physical volume')
    return {name: info.get(name) for name in (
        'MountPoint', 'DeviceIdentifier', 'VolumeUUID', 'DiskUUID', 'VolumeName',
        'Internal', 'VirtualOrPhysical', 'RemovableMedia', 'VolumeSize', 'FilesystemType')}


def _read_regular(path, maximum):
    """One bounded stable read, refusing symlinks/devices/FIFOs."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        if os.path.lexists(path):
            raise ValueError(f'broken symlink is not an absent file: {path.name}')
        return None
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or not 0 <= before.st_size <= maximum:
            raise ValueError(f'unsupported file type or size: {path.name}')
        chunks, remaining = [], before.st_size
        while remaining:
            chunk = os.read(fd, min(remaining, 1024 * 1024))
            if not chunk:
                raise ValueError(f'file truncated during backup: {path.name}')
            chunks.append(chunk)
            remaining -= len(chunk)
        extra = os.read(fd, 1)
        after = os.fstat(fd)
        current = os.stat(path, follow_symlinks=False)
        fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
        if extra or any(getattr(before, k) != getattr(after, k) or
                        getattr(before, k) != getattr(current, k) for k in fields):
            raise ValueError(f'file changed during backup: {path.name}')
        return b''.join(chunks)
    finally:
        os.close(fd)


def backup(volume, output, *, identity_reader=mounted_card_identity):
    volume, output = Path(volume), Path(output)
    identity = identity_reader(volume)  # all real CLI targets resolved here
    if output.exists() or output.is_symlink():
        raise ValueError('backup output must not already exist')
    if volume.resolve() == output.resolve() or volume.resolve() in output.resolve().parents:
        raise ValueError('backup must be stored off the test card')
    images = {name: _read_regular(volume / name, maximum) for name, maximum in TARGETS.items()}
    # Detect card swap/remount before committing a local backup manifest.
    if identity_reader(volume) != identity:
        raise ValueError('test card identity changed during backup')
    output.mkdir(parents=False, exist_ok=False)
    files = {}
    for name, data in images.items():
        if data is None:
            files[name] = {'present': False}
            continue
        with (output / name).open('xb') as destination:
            destination.write(data)
            destination.flush()
            os.fsync(destination.fileno())
        saved = (output / name).read_bytes()
        if saved != data:
            raise OSError(f'local backup readback failed: {name}')
        files[name] = {'present': True, 'bytes': len(data), 'sha256': _hash(data)}
    manifest = {'schema': 'fp-af-test-card-backup-v1', 'source_volume': str(volume),
                'volume_identity': identity, 'files': files,
                'card_modified': False, 'backup_readback_verified': True,
                'firmware_flashing_performed': False}
    with (output / 'backup.json').open('x', encoding='utf-8') as destination:
        destination.write(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
        destination.flush()
        os.fsync(destination.fileno())
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--volume', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = backup(args.volume, args.output)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
