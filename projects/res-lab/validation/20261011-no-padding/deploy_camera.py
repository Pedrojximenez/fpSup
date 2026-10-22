"""Install the unpadded AutoRun only, through the maintained short-file path."""
import fcntl
import hashlib
import importlib
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(HERE.parent / '20261009-oncamera'))
import live_camera as live
live.LOG = HERE / 'deployment-commands.jsonl'
CARD = ROOT / 'projects/usb-shell-sup/cards/20261011-no-pad-v3'


def fetch(remote, local, size):
    assert not local.exists()
    sys.argv = ['getfile.py', remote, str(local), '--size', str(size)]
    assert importlib.import_module('getfile').main() == 0
    assert local.stat().st_size == size


def word(address):
    reply = live.checked_sh(f'mem get 0x{address:08X},,4')
    return int(re.search(r'D:0x([0-9A-Fa-f]{8})', reply)[1], 16)


def main():
    evidence = HERE / 'deployment.json'
    assert not evidence.exists()
    proof = {'phase': 'preflight', 'remote': r'\AutoRun.txt'}
    def save():
        evidence.write_text(json.dumps(proof, indent=2) + '\n')
    with open('/tmp/fp-af-fusion.lock', 'r') as lease:
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert 'is_recording -> 0' in live.checked_sh('status get is_recording')
        assert 'slot = sd0' in live.checked_sh('sdcard slot')
        depth = word(0xC2F211DC)
        assert 0 <= depth <= 15
        callbacks = [word(0xC2F20FC0 + 36*i + 4) for i in range(1, depth + 1)]
        assert 0xC03DA7A8 not in callbacks, 'AutoRun is still active'
        assert word(0xC2F211DC) == depth
        p = importlib.import_module('putfile')
        old_size = p.remote_file_size(r'\AutoRun.txt')
        before = HERE / 'before-AutoRun.txt'
        fetch(r'\AutoRun.txt', before, old_size)
        old = before.read_bytes()
        expected = (ROOT / 'projects/usb-shell-sup/cards/20261011-no-hold-v3/AutoRun.txt').read_bytes()
        assert old == expected, 'Unknown existing AutoRun'
        new = (CARD / 'AutoRun.txt').read_bytes()
        from autorun_text import without_legacy_padding
        assert new == without_legacy_padding(old)
        loader_size = p.remote_file_size(r'\fpSup\LOADER.BIN')
        loader = HERE / 'before-LOADER.BIN'
        fetch(r'\fpSup\LOADER.BIN', loader, loader_size)
        proof.update(phase='backup_verified', old_bytes=old_size, new_bytes=len(new),
                     old_sha256=hashlib.sha256(old).hexdigest(),
                     new_sha256=hashlib.sha256(new).hexdigest(),
                     loader_sha256=hashlib.sha256(loader.read_bytes()).hexdigest(),
                     registration_callbacks=[hex(v) for v in callbacks])
        save()
        # putfile stages/verifies first, deletes a shorter target, confirms
        # absence, then writes the exact new bytes with no command replay.
        sys.argv = ['putfile.py', str(CARD / 'AutoRun.txt'), r'\AutoRun.txt']
        assert p.main() == 0
        proof['phase'] = 'written'
        save()
        size = p.remote_file_size(r'\AutoRun.txt')
        assert size == len(new)
        installed = HERE / 'installed-AutoRun.txt'
        fetch(r'\AutoRun.txt', installed, size)
        assert installed.read_bytes() == new
        same_loader = HERE / 'installed-LOADER.BIN'
        fetch(r'\fpSup\LOADER.BIN', same_loader, loader_size)
        assert same_loader.read_bytes() == loader.read_bytes()
        proof.update(phase='verified', passed=True, loader_unchanged=True)
        save()
        print(json.dumps(proof, indent=2), flush=True)


if __name__ == '__main__':
    main()
