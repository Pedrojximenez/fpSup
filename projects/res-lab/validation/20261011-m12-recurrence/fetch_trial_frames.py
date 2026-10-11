"""Fetch exact known-size first/middle/last DNGs after one completed trial."""
import fcntl
import importlib
import json
import pathlib
import re
import sys

import engine_patch as guard
live = guard.live
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(guard.ROOT/'projects/open-gate/build'))
from fpcam import parse_dng


def main():
    dest = HERE/sys.argv[1]
    trial_name = sys.argv[2] if len(sys.argv) > 2 else 'trial.json'
    assert trial_name in ('trial.json', 'trial-verified-completion.json')
    trial = json.loads((dest/trial_name).read_text())
    assert trial['phase'] == 'captured' and len(trial['new_clips']) == 1
    clip = trial['new_clips'][0]
    date = trial['clips_after'][clip]
    match = re.search(r'file-size=(\d+),',trial['record_log'])
    assert match
    size = int(match[1])
    match = re.search(r'req_cnt=(\d+), fin_cnt=(\d+),',trial['record_log'])
    assert match
    requested, count = int(match[1]), int(match[2])
    assert count <= requested
    assert 0 < size <= 2*1024*1024 and 0 < count <= 3000
    proof = {'clip':clip, 'requested':requested, 'finished':count, 'count':count,
             'bytes':size, 'sampling':'first/middle/finished-count index; not a complete sequence check',
             'transport':'maintained read_bulk with source-address suffix per chunk',
             'frames':[]}
    report = dest/'raw-frames.json'
    assert not report.exists()
    with open('/tmp/fp-af-fusion.lock','r') as lease:
        fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
        guard.standby()
        assert 'slot = sd0' in live.checked_sh('sdcard slot')
        getter = importlib.import_module('getfile')
        # Anonymous 1 MiB replies cannot identify their source range. Keep the
        # maintained allocator/file/free path, but tag every returned RAM chunk.
        getter.read_direct = lambda addr,size: live.putfile.read_bulk(addr,size,'tagged')
        for number in sorted(set((1,(count+1)//2,count))):
            guard.standby()
            local = dest/f'{clip}-{number:06d}.DNG'
            assert not local.exists()
            remote = f'\\CINEMA\\{clip}\\{clip}_{date}_{number:06d}.DNG'
            sys.argv = ['getfile.py',remote,str(local),'--size',str(size)]
            rc = getter.main()
            frame = {'number':number,'path':str(local),'transfer_return_code':rc}
            if not rc:
                assert local.stat().st_size == size
                try:
                    main, ifds = parse_dng(local)
                    row = trial['runtime_before']['rows'][trial['runtime_before']['registry']['row']]
                    frame.update(main_ifd=main,ifds=ifds,
                                 geometry_matches=list(main.get('DefaultCropSize',())) == [row['width'],row['height']],
                                 bit_depth_matches=main.get('BitsPerSample') == 12)
                except Exception as exc:
                    frame['parse_error'] = repr(exc)
            proof['frames'].append(frame)
            report.write_text(json.dumps(proof,indent=2)+'\n')
        print(json.dumps({k:proof[k] for k in ('clip','requested','finished','bytes')},indent=2))
        print(json.dumps([{k:f[k] for k in ('number','transfer_return_code','geometry_matches',
            'bit_depth_matches','parse_error') if k in f} for f in proof['frames']],indent=2))


if __name__ == '__main__':
    main()
