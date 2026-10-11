"""Task-scoped consumer update using reviewed file tools; no reboot or keys.

Install the reviewed September29 H2 RCD and required v16 consumer. Its existing CFG and the current card's common
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
import subprocess
import numpy as np
from PIL import Image

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(HERE.parent/'20261009-oncamera'))
import live_camera as live
sys.path.insert(0, str(ROOT/'projects/open-gate/build/res-custom'))
import ogc_layout as L
import rcd


def main():
    assert len(sys.argv) == 2
    dest = HERE/sys.argv[1]
    dest.mkdir()
    live.LOG = HERE/'commands.jsonl'
    candidate = ROOT/'projects/res-lab/cards/20261011-virtual-header-inner/plain-h2-recording-v16/fpSup/32RESCUS.BIN'
    prior = ROOT/'projects/res-lab/cards/20261011-virtual-header-inner/debug-sensorlab-profile-v15/fpSup/32RESCUS.BIN'
    new, old = candidate.read_bytes(), prior.read_bytes()
    assert hashlib.sha256(new).hexdigest() == 'a2c6dc20277c4340130191ef0346c14cc48476c87d1673708c1e1e846f504f64'
    assert hashlib.sha256(old).hexdigest() == '51cd29c8f7eea3e6ff78f6398b82d5b0bffa2033f6afc875047c2217606a297f'
    nh, oh = struct.unpack_from('<8I', new), struct.unpack_from('<8I', old)
    assert all(nh[i] == oh[i] for i in (0,1,5,7))
    assert new[32:128] == old[32:128] and len(new) == 185536 and len(old) == 184832
    assert nh[6] == 16 and oh[6] == 15
    proof = {'phase': 'preflight', 'candidate': str(candidate), 'files': {}, 'camera_rebooted': False,
             'reason': 'User authorizes M12 high-rate repair; test the archived H2 p13 profile, sensor240 with native30 carrier'}
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
        assert live.putfile.mem_get(0xc0b9e5d8,4,tries=1)==[0x4000000,0,0x40000,0xc03a55d0]
        shot=dest/'before-write.png'
        subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','avfoundation','-framerate','30','-pixel_format','uyvy422','-i','AVerMedia ExtremeCap UVC:none','-vf','scale=1024:576','-frames:v','1',str(shot)],check=True,timeout=15)
        roi=np.asarray(Image.open(shot).convert('RGB'))[:40,440:650].astype(np.int16)
        assert ((roi[:,:,1]>110)&(roi[:,:,0]<85)&(roi[:,:,2]<85)).sum()>10
        assert ((roi[:,:,0]>110)&(roi[:,:,1]<85)&(roi[:,:,2]<85)).sum()<=10
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
        rcd_directory = live.checked_sh('dir \\fpSup\\RESCUS')
        assert not re.search(r'\sH2S240\.RCD\s*$', rcd_directory, re.I|re.M), 'existing named RCD'
        proof['before_rcd_directory'] = rcd_directory
        datafile = HERE/'h2-success-rcd/H2S240.RCD'
        expected_rcd = datafile.read_bytes()
        assert hashlib.sha256(expected_rcd).hexdigest() == '835d214cf4c0b17d26f075e6ce3f749fe346ac88fb7c9ab4b9fe3642f15cbc99'
        rcd.decode(expected_rcd)
        proof['phase'] = 'backups_verified_before_rcd_write'
        save()
        standby()
        sys.argv = ['putfile.py', str(datafile), '\\fpSup\\RESCUS\\H2S240.RCD']
        assert not importlib.import_module('putfile').main()
        listing_rcd = live.checked_sh('dir \\fpSup\\RESCUS')
        assert length(listing_rcd, 'H2S240.RCD') == len(expected_rcd)
        readback_rcd = fetch('\\fpSup\\RESCUS\\H2S240.RCD', 'installed-H2S240.RCD', len(expected_rcd))
        assert readback_rcd == expected_rcd
        proof['h2_rcd'] = {'bytes':len(readback_rcd), 'sha256':hashlib.sha256(readback_rcd).hexdigest(), 'full_readback':True}
        proof['phase'] = 'rcd_verified_old_running_core_unchanged'
        save()
        prepared = dest/'prepared-32RESCUS.BIN'
        prepared.write_bytes(new[:32]+cfg+new[end:])
        proof['phase'] = 'backups_verified'
        save()
        standby()
        # The maintained writer stages/read-verifies before deleting an old
        # shorter replacement. This candidate is longer; the actual new length and full readback are verified.
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
                     card_updated=True, running_consumer_still_v15=True)
        save()
        print(json.dumps(proof, indent=2), flush=True)


if __name__ == '__main__':
    main()
