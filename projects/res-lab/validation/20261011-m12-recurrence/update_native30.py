"""Task-scoped consumer update using reviewed file tools; no reboot or keys.

Diagnostic native-30 carrier only. Only 32RESCUS.BIN is written. Its existing CFG and the current card's common
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
    rollback = len(sys.argv) == 3 and sys.argv[2] == '--rollback-v39'
    assert len(sys.argv) == 2 or rollback
    dest = HERE/sys.argv[1]
    dest.mkdir()
    live.LOG = HERE/'commands.jsonl'
    candidate = ROOT/'projects/res-lab/cards/20261011-m12-native30-v40/debug/fpSup/32RESCUS.BIN'
    prior = ROOT/'projects/res-lab/cards/20261011-m12-engine60-v39/debug/fpSup/32RESCUS.BIN'
    if rollback:
        candidate, prior = prior, candidate
    new, old = candidate.read_bytes(), prior.read_bytes()
    hashes = ('650c6fa0f27d216adba551cbec777741d42b39f4374e8b76db0f71dfbfe1cb85',
              '4358fce4127aedebbff0b93ea9db91f0a2805ae4cc013552dabc2f43e31c99dc') if rollback else (
              '4358fce4127aedebbff0b93ea9db91f0a2805ae4cc013552dabc2f43e31c99dc',
              '650c6fa0f27d216adba551cbec777741d42b39f4374e8b76db0f71dfbfe1cb85')
    assert tuple(hashlib.sha256(b).hexdigest() for b in (new,old)) == hashes
    if rollback:
        # Restore the exact previously verified bytes, rather than building a
        # new candidate. Its recorded 120p hardware trial finished 582/582.
        trial = json.loads((HERE/'v39-120-visible/trial-verified-completion.json').read_text())
        stop = json.loads((HERE/'v39-120-visible/stop-verification.json').read_text())
        # Preserve the original five-frame result. The separately verified
        # last three frames and fresh standby getter establish completion.
        assert trial['phase'] == 'captured' and trial['native_rec_zero_after']
        assert len(trial['overlay_after']) >= 3
        assert all(frame['standby_visible'] and not frame['rec_pixels']
                   for frame in trial['overlay_after'][-3:])
        assert stop['last_three_positive_STBY'] and stop['fresh_native_standby']
        assert stop['fresh_screen'] == 'LV_CINE_MEDIUM'
        assert stop['req_cnt'] == stop['fin_cnt'] == 582
        assert stop['ui_factor'] == 'Button' and stop['record_factor'] == 'Nothing'
        assert (HERE/'v39-120-visible'/stop['fresh_HDMI']).is_file()
        assert 'req_cnt=582, fin_cnt=582' in trial['record_log']
        original = (HERE/'deployment-v40-native30/before-32RESCUS.BIN').read_bytes()
        assert original[:32] == new[:32] and original[128:] == new[128:]
    else:
        offline = json.loads((HERE/'v40-offline-proof.json').read_text())
        assert offline['phase'] == 'offline_verified' and len(offline['passed_cases']) == 4
        assert offline['candidate_sha256'] == hashlib.sha256(new).hexdigest()
    nh, oh = struct.unpack_from('<8I', new), struct.unpack_from('<8I', old)
    assert all(nh[i] == oh[i] for i in (0,1,2,3,5,6,7))
    assert new[32:128] == old[32:128] and len(new) == len(old) == 182720
    proof = {'phase': 'preflight', 'candidate': str(candidate), 'files': {}, 'camera_rebooted': False,
             'rollback_to_v39': rollback}
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
        getter = importlib.import_module('getfile')
        getter.read_direct = lambda addr,n: live.putfile.read_bulk(addr,n,'tagged')
        assert not getter.main()
        assert path.stat().st_size == size
        return path.read_bytes()
    with open('/tmp/fp-af-fusion.lock', 'r') as lease:
        fcntl.flock(lease, fcntl.LOCK_EX|fcntl.LOCK_NB)
        standby()
        assert 'slot = sd0' in live.checked_sh('sdcard slot')
        files = live.checked_sh('dir \\fpSup')
        root = live.checked_sh('dir')
        for name, listing in (('AutoRun.txt', root), ('LOADER.BIN', files),
                              ('32RESCUS.BIN', files), ('50RESLAB.BIN', files)):
            size = length(listing, name)
            remote = '\\'+name if name == 'AutoRun.txt' else '\\fpSup\\'+name
            data = fetch(remote, 'before-'+name, size)
            proof['files'][name] = {'bytes': size, 'before_sha256': hashlib.sha256(data).hexdigest()}
            save()
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
                     card_updated=True, running_consumer_still_v39=not rollback,
                     running_consumer_still_v40=rollback, diagnostic_only=not rollback)
        save()
        print(json.dumps(proof, indent=2), flush=True)


if __name__ == '__main__':
    main()
