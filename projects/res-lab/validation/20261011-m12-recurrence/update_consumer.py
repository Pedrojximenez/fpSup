"""Task-scoped consumer update using reviewed file tools; no reboot or keys.

Only 32RESCUS.BIN is written. Its existing CFG and the current card's common
loader/AutoRun are preserved. All reads/writes run under the AF lease in standby.
"""
import fcntl
import hashlib
import importlib
import json
import pathlib
import re
import struct
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(HERE.parent/'20261009-oncamera'))
import live_camera as live
sys.path.insert(0, str(ROOT/'projects/open-gate/build/res-custom'))
import ogc_layout as L
import rcd


def main():
    dest = HERE/sys.argv[1]
    dest.mkdir()
    live.LOG = HERE/'commands.jsonl'
    candidate = ROOT/'projects/res-lab/cards/20261011-m12-engine60-v39/debug/fpSup/32RESCUS.BIN'
    prior = ROOT/'projects/res-lab/cards/20261011-count-v38/debug/fpSup/32RESCUS.BIN'
    new, old = candidate.read_bytes(), prior.read_bytes()
    assert hashlib.sha256(new).hexdigest() == '650c6fa0f27d216adba551cbec777741d42b39f4374e8b76db0f71dfbfe1cb85'
    assert new[:32] == old[:32] and len(new) == len(old) == 182720
    proof = {'phase': 'preflight', 'candidate': str(candidate), 'files': {}, 'camera_rebooted': False}
    def save():
        (dest/'deployment.json').write_text(json.dumps(proof, indent=2)+'\n')
    def standby():
        assert 'is_recording -> 0' in live.checked_sh('status get is_recording')
    def length(listing, name):
        m = re.search(r'(\d+)\s+'+re.escape(name)+r'\s*$', listing, re.M)
        assert m, name
        return int(m[1])
    def fetch(remote, name, size):
        standby()
        path = dest/name
        assert not path.exists() and 0 < size < 2000000
        sys.argv = ['getfile.py', remote, str(path), '--size', str(size)]
        assert not importlib.import_module('getfile').main()
        assert path.stat().st_size == size
        return path.read_bytes()
    with open('/tmp/fp-af-fusion.lock', 'r') as lease:
        fcntl.flock(lease, fcntl.LOCK_EX|fcntl.LOCK_NB)
        standby()
        assert 'slot = sd0' in live.checked_sh('sdcard slot')
        files = live.checked_sh('dir \\fpSup')
        root = live.checked_sh('dir')
        screenshot = live.checked_sh('dir \\DCIM\\100SIGMA')
        for name, listing in (('AutoRun.txt', root), ('LOADER.BIN', files),
                              ('32RESCUS.BIN', files), ('50RESLAB.BIN', files)):
            size = length(listing, name)
            remote = '\\'+name if name == 'AutoRun.txt' else '\\fpSup\\'+name
            data = fetch(remote, 'before-'+name, size)
            proof['files'][name] = {'bytes': size, 'before_sha256': hashlib.sha256(data).hexdigest()}
            save()
        data = fetch('\\DCIM\\100SIGMA\\SS__1670.JPG', 'SS__1670.JPG', length(screenshot, 'SS__1670.JPG'))
        proof['screenshot_sha256'] = hashlib.sha256(data).hexdigest()
        actual = (dest/'before-32RESCUS.BIN').read_bytes()
        end = 32+L.CFG['BYTES']
        assert actual[:32] == old[:32] and actual[end:] == old[end:], 'unknown consumer code'
        cfg = actual[32:end]
        word = lambda name: struct.unpack_from('<I', cfg, L.CFG[name])[0]
        # A pristine build has the exact frozen default (all-zero) CFG. The
        # runtime deliberately treats this as no saved enable record. Accept
        # that known image, or a structurally valid saved record; nothing else.
        if cfg == old[32:end]:
            assert not any(cfg), 'unexpected frozen default'
            proof['cfg_kind'] = 'exact_frozen_default'
        else:
            assert word('MAGIC') == L.CFG_MAGIC and word('VERSION') == L.CFG_VERSION
            assert word('NEN') <= L.MAX_ROWS and word('SUM') == rcd.fnv(cfg[:L.CFG['SUM']])
            proof['cfg_kind'] = 'validated_saved_record'
        proof['preserved_cfg_sha256'] = hashlib.sha256(cfg).hexdigest()
        producer = (dest/'before-50RESLAB.BIN').read_bytes()
        assert hashlib.sha256(producer).hexdigest() == 'dad8226db751fe10c2cac1f2f21269cc746957c7aacc5b19bec83dd027da155f'
        prepared = dest/'prepared-32RESCUS.BIN'
        prepared.write_bytes(new[:32]+cfg+new[end:])
        proof['phase'] = 'backups_verified'
        save()
        standby()
        # The maintained writer stages/read-verifies before deleting an old
        # shorter replacement. This candidate has the same exact length.
        sys.argv = ['putfile.py', str(prepared), '\\fpSup\\32RESCUS.BIN']
        assert not importlib.import_module('putfile').main()
        proof['phase'] = 'written'
        save()
        listing = live.checked_sh('dir \\fpSup')
        assert length(listing, '32RESCUS.BIN') == len(new)
        installed = fetch('\\fpSup\\32RESCUS.BIN', 'installed-32RESCUS.BIN', len(new))
        assert installed == prepared.read_bytes()
        # Read all preserved files, rather than claiming that a successful
        # consumer transfer also proves the shared chain stayed unchanged.
        for name in ('AutoRun.txt', 'LOADER.BIN', '50RESLAB.BIN'):
            remote = '\\'+name if name == 'AutoRun.txt' else '\\fpSup\\'+name
            after = fetch(remote, 'after-'+name, proof['files'][name]['bytes'])
            assert after == (dest/('before-'+name)).read_bytes()
            proof['files'][name]['unchanged'] = True
        proof.update(phase='verified', installed_sha256=hashlib.sha256(installed).hexdigest(),
                     card_updated=True, running_consumer_still_v38=True)
        save()
        print(json.dumps(proof, indent=2), flush=True)


if __name__ == '__main__':
    main()
