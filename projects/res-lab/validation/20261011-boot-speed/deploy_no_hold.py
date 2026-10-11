"""Replace only the reviewed v3 loader; preserve its disabled-Sup trailer."""
import fcntl
import hashlib
import importlib
import json
from pathlib import Path
import re
import struct
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(HERE.parent / '20261009-oncamera'))
import live_camera as live

live.LOG = HERE / 'deployment-commands.jsonl'
REMOTE = r'\fpSup\LOADER.BIN'
CARD = ROOT / 'projects/usb-shell-sup/cards/20261011-no-hold-v3'


def fetch(local, size):
    assert not local.exists()
    sys.argv = ['getfile.py', REMOTE, str(local), '--size', str(size)]
    assert importlib.import_module('getfile').main() == 0
    assert local.stat().st_size == size


def main():
    proof = {'phase': 'preflight', 'remote': REMOTE, 'card': str(CARD)}
    evidence = HERE / 'deployment.json'
    assert not evidence.exists()

    def save():
        evidence.write_text(json.dumps(proof, indent=2) + '\n')

    with open('/tmp/fp-af-fusion.lock', 'r') as lease:
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert 'is_recording -> 0' in live.checked_sh('status get is_recording')
        assert 'slot = sd0' in live.checked_sh('sdcard slot')
        def word(address):
            reply = live.checked_sh(f'mem get 0x{address:08X},,4')
            return int(re.search(r'D:0x([0-9A-Fa-f]{8})', reply)[1], 16)

        # The ordinary console keeps an entry of its own. Depth 1 alone does
        # not mean AutoRun is active; identify the interpreter's callback.
        depth = word(0xC2F211DC)
        assert 0 <= depth <= 15
        callbacks = [word(0xC2F20FC0 + 36 * i + 4) for i in range(1, depth + 1)]
        assert 0xC03DA7A8 not in callbacks, 'AutoRun is still active; do not replace its loader'
        assert word(0xC2F211DC) == depth, 'Registration table changed during preflight'
        proof['registration_callbacks'] = [hex(v) for v in callbacks]
        listing = live.checked_sh(r'dir \fpSup')
        size = int(re.search(r'(\d+)\s+LOADER\.BIN\s*$', listing, re.M)[1])
        before = HERE / 'before-deployment-LOADER.BIN'
        fetch(before, size)
        old = before.read_bytes()
        reference = (HERE / 'current-LOADER.BIN').read_bytes()
        old_at = 16 + struct.unpack_from('<I', old, 12)[0]
        assert old[:old_at] == reference[:old_at], 'Unknown loader code'
        trailer = old[old_at:]
        assert len(trailer) == 128
        magic, count = struct.unpack_from('<II', trailer)
        assert magic == 0x53445346 and count <= 30
        ids = [trailer[8 + i * 4:12 + i * 4] for i in range(count)]
        assert len(ids) == len(set(ids))
        new = (CARD / 'fpSup/LOADER.BIN').read_bytes()
        new_at = 16 + struct.unpack_from('<I', new, 12)[0]
        assert len(new) == new_at + 128
        prepared = HERE / 'prepared-LOADER.BIN'
        prepared.write_bytes(new[:new_at] + trailer)
        proof.update(phase='backup_verified', old_bytes=size, new_bytes=prepared.stat().st_size,
                     old_sha256=hashlib.sha256(old).hexdigest(),
                     new_sha256=hashlib.sha256(prepared.read_bytes()).hexdigest(),
                     disabled_ids=[sid.hex() for sid in ids], autorun_changed=False)
        save()

        # Mode 7 does not truncate. Delete this one backed-up non-media file
        # first because removing the sleep made it 16 bytes shorter.
        assert importlib.import_module('putfile').delete_file(REMOTE)
        assert not re.search(r'\sLOADER\.BIN\s*$', live.checked_sh(r'dir \fpSup'), re.M)
        proof['phase'] = 'old_loader_deleted'
        save()
        sys.argv = ['putfile.py', str(prepared), REMOTE]
        assert importlib.import_module('putfile').main() == 0
        proof['phase'] = 'written'
        save()
        listing = live.checked_sh(r'dir \fpSup')
        (HERE / 'directory-after-loader.txt').write_text(listing)
        size = int(re.search(r'(\d+)\s+LOADER\.BIN\s*$', listing, re.M)[1])
        assert size == prepared.stat().st_size
        installed = HERE / 'installed-LOADER.BIN'
        fetch(installed, size)
        assert installed.read_bytes() == prepared.read_bytes()
        proof.update(phase='verified', passed=True)
        save()
        print(json.dumps(proof, indent=2), flush=True)


if __name__ == '__main__':
    main()
