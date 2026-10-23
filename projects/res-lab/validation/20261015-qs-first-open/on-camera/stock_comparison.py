"""Temporarily remove only the backed-up RES-Custom BIN; restore exact bytes.

Both actions require the verified daemon and guarded idle camera. Other card
files, loader, settings and media remain in place. Reboot is a separate step.
"""
import argparse
import fcntl
import hashlib
import json
import sys
import experiment as E

parser = argparse.ArgumentParser()
parser.add_argument('action', choices=('disable', 'restore'))
parser.add_argument('--variant', choices=('combined', 'combined-fix9'), default='combined')
parser.add_argument('--folder', type=E.Path, default=E.HERE / 'run2/stock-comparison')
args = parser.parse_args()
folder = args.folder.resolve()
assert folder.is_relative_to(E.HERE.resolve())
remote = '\\fpSup\\32RESCUS.BIN'
backup = folder / '32RESCUS.BIN'
report = folder / 'card-state.json'
with open('/tmp/fp-af-fusion.lock') as lease:
    fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
    E.live.LOG = folder.parent / (folder.name + '-commands.jsonl')
    E.daemon(); E.B.idle()
    if args.action == 'disable':
        assert not folder.exists(), 'never overwrite comparison evidence'
        folder.mkdir()
        size = E.pf.remote_file_size(remote)
        expected = (E.HERE / ('prepared-' + args.variant + '-32RESCUS.BIN')).read_bytes()
        assert size == len(expected)
        data = E.B.fetch(remote, backup, size)
        assert data[:32] == expected[:32] and data[128:] == expected[128:]
        proof = {'phase': 'backed_up', 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
        report.write_text(json.dumps(proof, indent=2) + '\n')
        E.B.idle()
        assert E.pf.delete_file(remote)
        assert E.pf.remote_file_size(remote) is None
        proof['phase'] = 'disabled'
    else:
        proof = json.loads(report.read_text())
        assert proof['phase'] == 'disabled'
        data = backup.read_bytes()
        assert hashlib.sha256(data).hexdigest() == proof['sha256']
        assert E.pf.remote_file_size(remote) is None
        sys.argv = ['putfile.py', str(backup), remote]
        assert E.pf.main() == 0
        assert E.pf.remote_file_size(remote) == len(data)
        assert E.B.fetch(remote, folder / 'restored.BIN', len(data)) == data
        proof['phase'] = 'restored_exact'
    report.write_text(json.dumps(proof, indent=2) + '\n')
    E.B.idle()
    print(json.dumps(proof, indent=2), flush=True)
