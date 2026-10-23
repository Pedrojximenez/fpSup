"""Add the reviewed five RCDs and enable RCUS in the existing FSDS settings.

Uses the exact current-card loader program/envelope and changes only its
documented disabled-list trailer. Payload, AutoRun and other Sups are preserved.
"""
import fcntl
import hashlib
import json
import struct
import sys
import re
import experiment as E

p = E.HERE / 'run3'
report = p / 'enable-deployment.json'
assert not report.exists()
manifest = json.loads((p / 'backup/manifest.json').read_text())
assert manifest['phase'] == 'complete'
assert not re.search(r'<DIR>\s+RESCUS\s*$', manifest['fpSup_listing'], re.M)
proof = json.loads((p / 'enable-preparation.json').read_text())
verification = json.loads((p / 'combined-fix1-verification.json').read_text())
old = (p / 'backup/fpSup__LOADER.BIN').read_bytes()
new = (p / 'enabled-LOADER.BIN').read_bytes()
assert hashlib.sha256(new).hexdigest() == verification['actual_card_loader'] == proof['new_sha256']
assert new[:-128] == old[:-128] and len(new) == len(old)
assert old[-128:-124] == new[-128:-124] == b'FSDS'
assert struct.unpack_from('<I', old, len(old)-124)[0] == 1
assert old[-120:-116] == b'RCUS' and new[-124:] == bytes(124)
folder = E.HERE / 'combined-fix1'
files = json.loads((folder / 'build.json').read_text())['files']
proof.update(phase='preflight', written={})
save = lambda: report.write_text(json.dumps(proof, indent=2) + '\n')
with open('/tmp/fp-af-fusion.lock') as lease:
    fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
    E.live.LOG = p / 'commands.jsonl'
    E.daemon(); E.B.idle()
    assert E.B.fetch('\\fpSup\\LOADER.BIN', p / 'before-enable-LOADER.BIN', len(old)) == old
    expected = (E.HERE / 'prepared-combined-fix1-32RESCUS.BIN').read_bytes()
    assert E.B.fetch('\\fpSup\\32RESCUS.BIN', p / 'before-enable-32RESCUS.BIN', len(expected)) == expected
    assert not re.search(r'<DIR>\s+RESCUS\s*$', E.live.checked_sh('dir \\fpSup'), re.M)
    save()
    E.live.checked_sh('mkdir \\fpSup\\RESCUS')
    assert re.search(r'<DIR>\s+RESCUS\s*$', E.live.checked_sh('dir \\fpSup'), re.M)
    for name, meta in files.items():
        if not name.startswith('RESCUS/'):
            continue
        local = folder / name
        data = local.read_bytes()
        assert hashlib.sha256(data).hexdigest() == meta['sha256']
        remote = '\\fpSup\\' + name.replace('/', '\\')
        assert E.pf.remote_file_size(remote) is None
        E.B.idle(); sys.argv = ['putfile.py', str(local), remote]
        assert E.pf.main() == 0
        assert E.pf.remote_file_size(remote) == len(data)
        assert E.B.fetch(remote, p / ('installed-' + local.name), len(data)) == data
        proof['written'][remote] = meta['sha256']; save()
    # The loader's executable bytes remain exact. Only remove RCUS from its
    # existing settings trailer, just as SupManager's explicit Enable does.
    E.B.idle(); sys.argv = ['putfile.py', str(p / 'enabled-LOADER.BIN'), '\\fpSup\\LOADER.BIN']
    assert E.pf.main() == 0
    assert E.pf.remote_file_size('\\fpSup\\LOADER.BIN') == len(new)
    assert E.B.fetch('\\fpSup\\LOADER.BIN', p / 'installed-enabled-LOADER.BIN', len(new)) == new
    proof['phase'] = 'verified'; save(); E.B.idle()
    print(json.dumps(proof, indent=2), flush=True)
