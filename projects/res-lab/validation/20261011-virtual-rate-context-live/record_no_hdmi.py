"""One native-LCD-guarded SD comparison with HDMI physically removed.

Same four consumer-owned rate words as the failed sensor-only experiment.
No producer Apply, buffer change, new camera code, or poll loop during capture.
"""
import fcntl
import json
import re
import struct
import sys
import time
import camera as C
sys.path.insert(0,str(C.HERE))
import native_lcd as LCD
import sensor_only_ram as R
import record_trial as T

DEST=C.HERE/'sensor-only-no-hdmi-quiet20'
PATCH=C.HERE/'sensor-only-no-hdmi-ram'


def main():
    assert sys.argv[1:]==['run']
    DEST.mkdir()
    proof={'phase':'preflight','label':DEST.name,'hdmi_removed_by_user':True,
           'native_LCD_instead_of_HDMI':True,'stop_after_seconds':20,
           'start_sent':False,'stop_sent':False,'spontaneous_stop':False,
           'scope':'Same H2 sensor239.76 / application2997 / processing30.0 / nominal30; mode230; SD; LosslessOFF; native64MiB'}
    save=lambda:(DEST/'trial.json').write_text(json.dumps(proof,indent=2)+'\n')
    save()
    R.prepare(PATCH,lambda:LCD.shot('no-hdmi-before-ram',DEST))
    proof['patch_manifest']=str(PATCH/'patch.json')
    with open('/tmp/fp-af-fusion.lock') as lease:
        fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
        proof['idle_before']=LCD.idle()
        r=C.snapshot();proof['runtime_before']=r;proof['checks_before']=R.check(r,0)
        assert r['screen']=='LV_CINE_MEDIUM' and r['picked_entry']['MODE']>=230
        assert 'slot = sd0' in C.live.checked_sh('sdcard slot')
        proof['audio_getter']=C.live.checked_sh('menu SetAudioRecSupport').strip()
        assert proof['audio_getter']=='1'
        proof['lcd_before']=LCD.shot('no-hdmi-before-record',DEST)
        proof['clips_before']=T.clips()
        clock=T.TrialClock(DEST/'timeline.jsonl',DEST/'no-hdmi.raw',1)
        proof.update(phase='record_start',start_sent=True);save()
        start=time.monotonic();T.pulse(clock,'start')
        time.sleep(max(0,.20-(time.monotonic()-start)))
        current=T.rec(clock,'before_one_processing_rate_read')
        proof['recording_at_one_rate_read']=current
        if current:
            word=C.live.putfile.mem_get(0xC31DF574,tries=1)[0]
            proof['processing_rate_during']={'address':'0xc31df574','word':word,
                                            'fps':struct.unpack('<f',struct.pack('<I',word))[0]}
            assert word==R.ENGINE30
        save()
        time.sleep(max(0,20-(time.monotonic()-start)))
        current=T.rec(clock,'at_target20')
        proof['recording_at_target']=current
        if current:
            assert T.rec(clock,'before_stop')==1
            proof['stop_sent']=True;save();T.pulse(clock,'stop')
        else:
            proof['spontaneous_stop']=True
        for _ in range(10):
            if T.rec(clock,'after_stop')==0:break
            time.sleep(.5)
        else:raise RuntimeError('REC remains positive; no toggle replay')
        proof['native_rec_zero_after']=True;proof['phase']='drain_check';save()
        # Native busy predicates gate all file tools when HDMI is absent.
        # Wait only after REC0; no screenshot or writer operation during drain.
        for attempt in range(6):
            try:
                proof['idle_after']=LCD.idle();break
            except AssertionError as exc:
                proof['idle_pending']=repr(exc);save()
                if attempt==5:raise
                time.sleep(2)
        proof['record_log']=C.live.checked_sh('rec log-out');save()
        req,fin=map(int,re.search(r'req_cnt=(\d+), fin_cnt=(\d+),',proof['record_log']).groups())
        assert req==fin and req>0,(req,fin)
        proof['requested']=req;proof['finished']=fin
        proof['lcd_after']=LCD.shot('no-hdmi-after-record',DEST)
        proof['standby_after']=True
        proof['clips_after']=T.clips()
        proof['new_clips']=sorted(proof['clips_after'].keys()-proof['clips_before'].keys())
        r=C.snapshot();proof['runtime_after']=r;proof['checks_after']=R.check(r,0)
        for key in ('HDR_COPY_HITS','BULK_HITS'):
            assert r['header_copy'][key]==proof['runtime_before']['header_copy'][key]
        assert proof['checks_after']['global_bulk_bytes']==0x4000000
        proof['phase']='captured';save()
        print(json.dumps({k:proof[k] for k in ('phase','recording_at_target','stop_sent','spontaneous_stop','requested','finished','new_clips','record_log')},indent=2),flush=True)


if __name__=='__main__':
    main()
