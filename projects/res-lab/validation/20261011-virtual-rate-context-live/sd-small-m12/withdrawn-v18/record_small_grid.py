"""One pinned Lossless grid comparison, with checked standby restoration.

Uses the existing card.c tile_force diagnostic, as tile_sweep.py does. Only
that owned parameter is changed; it is restored after a confirmed idle take.
"""
import fcntl
import json
import subprocess
import sys
import numpy as np
from PIL import Image
import camera as C
sys.path.insert(0, str(C.HERE))
import record_trial
import record_small_lossless as baseline
import lossless_snapshot

assert record_trial.__file__ == str(C.HERE/'record_trial.py')
LABEL = 'tagged-240-small-grid512-v17-quiet'
assert sys.argv[1:] == [LABEL, '23976']
FORCE = (512 << 16) | 368
fields = json.loads((C.HERE/'sd-small-m12/lossless-layout/layout.json').read_text())['fields']
REPORT = C.HERE/'sd-small-m12/grid512-parameter.json'

def main():
    assert not REPORT.exists()
    with open('/tmp/fp-af-fusion.lock','r') as lease:
        fcntl.flock(lease, fcntl.LOCK_EX|fcntl.LOCK_NB)
        assert C.recording() == 0 and C.live.screen() == 'LV_CINE_MEDIUM'
        before = lossless_snapshot.snapshot()
        assert all(before['fields'][k] == 0 for k in ('hold_live','hold.lane','hold_b.lane'))
        state = int(before['state'],16)
        addr = state + fields['tile_force']
        assert C.live.putfile.mem_get(addr,tries=1) == [0]
        shot = C.HERE/'sd-small-m12/before-grid512.png'
        assert not shot.exists()
        subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','avfoundation',
            '-framerate','30','-pixel_format','uyvy422','-i','AVerMedia ExtremeCap UVC:none',
            '-vf','scale=1024:576','-frames:v','1',str(shot)],check=True,timeout=15)
        assert record_trial.overlay(np.asarray(Image.open(shot).convert('RGB')))['standby_visible']
        assert C.recording() == 0
        C.live.putfile.mem_set(addr, FORCE)
        assert C.live.putfile.mem_get(addr,tries=1) == [FORCE]
        proof = {'parameter':hex(addr),'old':0,'forced':FORCE,'grid':[512,368],
                 'standby_proof':str(shot),'before':before,'restored':False}
        REPORT.write_text(json.dumps(proof,indent=2)+'\n')
    def check(runtime, quality):
        result = baseline.check(runtime,quality)
        assert result['lossless']['state'] == before['state']
        assert C.live.putfile.mem_get(addr,tries=1) == [FORCE]
        result['forced_grid'] = [512,368]
        return result
    try:
        sys.argv = [sys.argv[0], LABEL, '23976', '0', 'quiet']
        record_trial.main(runtime_check=check,stop_after=20,frame_count=900)
    finally:
        with open('/tmp/fp-af-fusion.lock','r') as lease:
            fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
            assert C.recording() == 0
            after = lossless_snapshot.snapshot()
            assert after['state'] == before['state']
            assert all(after['fields'][k] == 0 for k in ('hold_live','hold.lane','hold_b.lane'))
            assert C.live.putfile.mem_get(addr,tries=1) == [FORCE]
            proof['after'] = after
            proof['actual_grid'] = [C.live.putfile.mem_get(state+fields[k],tries=1)[0]
                for k in ('hold.job.tile_width','hold.job.tile_height')]
            C.live.putfile.mem_set(addr,0)
            assert C.live.putfile.mem_get(addr,tries=1) == [0]
            proof['restored'] = True
            REPORT.write_text(json.dumps(proof,indent=2)+'\n')
            print(json.dumps({k:proof[k] for k in ('actual_grid','restored')}),flush=True)

if __name__ == '__main__':
    main()
