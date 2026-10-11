"""One RAM mode-ID word; native sensor tables unchanged; restore after capture."""
import fcntl
import json
import struct
import subprocess
import sys
import camera as C
sys.path.insert(0,str(C.HERE))
import sensor_only_ram as R
import record_trial
from ogc_layout import ENT

LABEL='native-m12-identity-quiet20'
PATCH=C.HERE/'native-m12-identity-patch.json'


def check(r,quality):
    assert quality==0
    return R.owned(r,True,native_identity=True)


if __name__=='__main__':
    assert sys.argv[1:]==['run'] and not PATCH.exists()
    proof={'phase':'preflight','scope':'one consumer-owned entry mode word; no native table writes'}
    save=lambda:PATCH.write_text(json.dumps(proof,indent=2)+'\n')
    with open('/tmp/fp-af-fusion.lock') as lease:
        fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
        r=C.snapshot();old=R.owned(r,True)
        proof['runtime_before']=r;proof['owned_before']=old;save()
        assert r['screen']=='LV_CINE_MEDIUM'
        native=C.live.putfile.mem_get(0xC0B59A40,8,tries=1)
        assert native[0]==12 and native[1:3]==[R.WANT['w0'],R.WANT['w1']]
        desc=C.live.putfile.mem_get(0xC343B588,tries=1)[0]
        # Native fixed BSS descriptor, as passed by FUN_c0322e88.
        assert desc==0xC2F1E654
        assert C.live.putfile.mem_get(0xC2F1E654,2,tries=1)==[0xC0B59500,70]
        import numpy as np
        from PIL import Image
        shot=C.HERE/'native-m12-identity-preflight.png';assert not shot.exists()
        raw=C.HERE/'native-m12-identity-preflight.rgb';assert not raw.exists()
        subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','avfoundation',
            '-framerate','30','-pixel_format','uyvy422','-i','AVerMedia ExtremeCap UVC:none',
            '-vf','scale=1024:576','-frames:v','24','-pix_fmt','rgb24','-f','rawvideo',str(raw)],
            check=True,timeout=15)
        assert raw.stat().st_size==24*record_trial.FRAME_BYTES
        frames=np.memmap(raw,np.uint8,'r',shape=(24,576,1024,3))
        proof['standby_before']=[record_trial.overlay(f) for f in frames[-3:]]
        Image.fromarray(frames[-1]).save(shot)
        del frames
        save()
        assert all(o['standby_visible'] for o in proof['standby_before'])
        assert C.recording()==0
        address=int(old['entry'],16)+ENT['MODE'];mode=r['picked_entry']['MODE']
        assert 230<=mode<=245 and C.live.putfile.mem_get(address,tries=1)==[mode]
        proof.update(phase='write_requested',address=hex(address),before=mode,after=12);save()
        C.live.putfile.mem_set(address,12)
        assert C.live.putfile.mem_get(address,tries=1)==[12]
        proof['phase']='patched';proof['owned_after']=check(C.snapshot(),0);save()
    sys.argv=[sys.argv[0],LABEL,'2997','0','quiet']
    def rate_probe():
        word=C.live.putfile.mem_get(0xC31DF574,tries=1)[0]
        return {'address':'0xc31df574','word':word,'fps':struct.unpack('<f',struct.pack('<I',word))[0]}
    record_trial.main(historical_check=check,stop_after=20,frame_count=900,rate_probe=rate_probe)
    t=json.loads((C.HERE/LABEL/'trial.json').read_text())
    assert t['phase']=='captured' and t['standby_after'] and t['native_rec_zero_after']
    with open('/tmp/fp-af-fusion.lock') as lease:
        fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
        r=C.snapshot();check(r,0)
        assert C.recording()==0 and C.live.putfile.mem_get(address,tries=1)==[12]
        C.live.putfile.mem_set(address,mode)
        assert C.live.putfile.mem_get(address,tries=1)==[mode]
        proof['phase']='restored';proof['owned_restored']=R.owned(C.snapshot(),True);save()
    print('Native mode ID restored after the bounded trial.',flush=True)
