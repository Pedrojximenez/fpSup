"""Verified SUP update; exact old files, preserved settings and shared chain."""
import fcntl
import hashlib
import importlib
import json
import pathlib
import re
import struct
import sys
import on_camera as cam

live = cam.live
HERE, ROOT = cam.HERE, cam.ROOT
sys.path.insert(0, str(ROOT/'projects/open-gate/build/res-custom'))
import ogc_layout as L
import rcd


def main():
    old, card = map(pathlib.Path, sys.argv[1:3])
    dest = HERE / sys.argv[3]
    consumer = '--consumer' in sys.argv[4:]
    dest.mkdir()  # Preserve earlier deployment evidence.
    proof = {'old_card': str(old), 'new_card': str(card), 'phase': 'preflight'}
    def save():
        (dest/'deployment.json').write_text(json.dumps(proof, indent=2)+'\n')
    def fetch(remote, local, size):
        sys.argv = ['getfile.py', remote, str(local), '--size', str(size)]
        assert not importlib.import_module('getfile').main()
        assert local.stat().st_size == size
    with open('/tmp/fp-af-fusion.lock', 'r') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert 'is_recording -> 0' in live.checked_sh('status get is_recording')
        assert 'slot = sd0' in live.checked_sh('sdcard slot')
        for relative in ('AutoRun.txt', 'fpSup/32RESCUS.BIN', 'fpSup/LOADER.BIN', 'fpSup/50RESLAB.BIN'):
            expected = (old/relative).read_bytes()
            target = '\\' + relative.replace('/', '\\')
            backup = dest/('before-'+pathlib.Path(relative).name)
            fetch(target, backup, len(expected))
            actual = backup.read_bytes()
            if relative == 'fpSup/32RESCUS.BIN' and actual != expected:
                # The consumer owns a persistent settings record at file+32.
                # Preserve it; compare all code bytes and check the record CRC.
                end = 32+L.CFG['BYTES']; cfg = actual[32:end]
                assert actual[:32] == expected[:32] and actual[end:] == expected[end:]
                word = lambda key: struct.unpack_from('<I', cfg, L.CFG[key])[0]
                assert word('MAGIC') == L.CFG_MAGIC and word('VERSION') == L.CFG_VERSION
                assert word('SUM') == rcd.fnv(cfg[:L.CFG['SUM']])
                proof['consumer_settings_preserved'] = {'sha256': hashlib.sha256(actual).hexdigest(),
                    'label': cfg[L.CFG['SEL']:L.CFG['SEL']+8].split(b'\0')[0].decode(),
                    'stock': word('SEL_STOCK'), 'flags': word('FLAGS'), 'checksum_valid': True}
            elif relative == 'fpSup/LOADER.BIN' and actual != expected:
                # SupManager's existing FSDS trailer stores disabled SUP ids.
                start = len(expected)-128
                assert expected[start:start+4] == b'FSDS'
                assert actual[:start+4] == expected[:start+4]
                count = struct.unpack_from('<I', actual, start+4)[0]
                assert count <= 30
                ids = [actual[start+8+i*4:start+12+i*4].decode('ascii') for i in range(count)]
                assert len(ids) == len(set(ids))
                proof['disabled_sups_preserved'] = ids
            else:
                assert actual == expected, f'Unknown existing {relative}'
            if relative != 'fpSup/50RESLAB.BIN' and not (consumer and relative == 'fpSup/32RESCUS.BIN'):
                assert expected == (card/relative).read_bytes(), f'Incompatible common chain: {relative}'
        sources = [('50RESLAB.BIN', card/'fpSup/50RESLAB.BIN')]
        if consumer:
            code = (card/'fpSup/32RESCUS.BIN').read_bytes()
            prior = (dest/'before-32RESCUS.BIN').read_bytes()
            prepared = dest/'prepared-32RESCUS.BIN'
            prepared.write_bytes(code[:32]+prior[32:32+L.CFG['BYTES']]+code[32+L.CFG['BYTES']:])
            sources.append(('32RESCUS.BIN', prepared))
        proof['phase'] = 'backup_verified'; save()
        proof['files'] = []
        for name, source in sources:
            target = '\\fpSup\\'+name
            if source.stat().st_size < (dest/('before-'+name)).stat().st_size:
                live.checked_sh('fl del '+target)
                assert not re.search(r'\s'+re.escape(name)+r'\s*$', live.checked_sh('dir \\fpSup'), re.M)
                proof['phase'] = name+' old_deleted'; save()
            sys.argv = ['putfile.py', str(source), target]
            assert not importlib.import_module('putfile').main()
            proof['phase'] = name+' written'; save()
            listing = live.checked_sh('dir \\fpSup')
            (dest/('directory-after-'+name+'.txt')).write_text(listing)
            size = int(re.search(r'(\d+)\s+'+re.escape(name)+r'\s*$', listing, re.M).group(1))
            assert size == source.stat().st_size
            installed = dest/('installed-'+name)
            fetch(target, installed, size)
            assert installed.read_bytes() == source.read_bytes()
            proof['files'].append({'name':name,'bytes':size,'sha256':hashlib.sha256(installed.read_bytes()).hexdigest(),
                'candidate_sha256':hashlib.sha256((card/'fpSup'/name).read_bytes()).hexdigest(),
                'backup_sha256':hashlib.sha256((dest/('before-'+name)).read_bytes()).hexdigest()})
            save()
        proof.update(phase='verified', passed=True)
        save(); print(json.dumps(proof, indent=2), flush=True)


if __name__ == '__main__':
    main()
