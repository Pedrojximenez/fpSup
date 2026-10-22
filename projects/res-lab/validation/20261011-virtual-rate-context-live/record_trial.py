"""One bounded candidate trial, with continuous HDMI and guarded MOV pulses.

Normal UI must select the rate. No live entry overrides, private picker calls,
clip-subdirectory listing or toggle replay. REC=0 and visible STBY are both
required before reading files or starting another trial.
"""
import fcntl
import json
import pathlib
import re
import subprocess
import sys
import time

import numpy as np
import camera as C
from preview_planes import read_planes
sys.path.insert(0,str(C.HERE.parent/'20261011-m12-recurrence'))
from trial_clock import TrialClock

FRAME_BYTES = 1024*576*3
NFRAMES = 300


def overlay(frame):
    rgb = frame[:40,440:650].astype(np.int16)
    red = (rgb[:,:,0]>110)&(rgb[:,:,1]<85)&(rgb[:,:,2]<85)
    green = (rgb[:,:,1]>110)&(rgb[:,:,0]<85)&(rgb[:,:,2]<85)
    return {'rec_pixels':int(red.sum()),'standby_pixels':int(green.sum()),
            'standby_visible':bool(green.sum()>10 and red.sum()<=10)}


def clips():
    out = C.live.checked_sh('dir \\CINEMA')
    return {m[4]:''.join(m.groups()[:3]) for m in
            re.finditer(r'^\s*(\d{4})/(\d{2})/(\d{2}).*\b(A\d{3}_\d{3})\s*$',out,re.M)}


def rec(clock,action='recording_check'):
    out = clock.command(C.live.checked_sh,'status get is_recording',action)
    m = re.fullmatch(r'\s*is_recording -> ([01])\s*',out)
    assert m,out
    return int(m[1])


def pulse(clock,action):
    try:
        clock.command(C.live.checked_sh,'key MOVON',action+'_down')
    finally:
        time.sleep(.12)
        clock.command(C.live.checked_sh,'key MOVOFF',action+'_up')


def main(historical_check=None, runtime_check=None, stop_after=4.0, frame_count=NFRAMES, rate_probe=None):
    label,rank = sys.argv[1],int(sys.argv[2])
    quality = int(sys.argv[3]) if len(sys.argv)>3 else 0
    observe = len(sys.argv)>4 and sys.argv[4]=='observe'
    quiet = len(sys.argv)>4 and sys.argv[4]=='quiet'
    planes = len(sys.argv)>4 and sys.argv[4]=='planes'
    if len(sys.argv)>4:
        assert sys.argv[4] in ('observe', 'quiet', 'planes')
    assert quality in (0,4)
    assert rank in ((2997,) if historical_check else (0,23976,27972))
    dest = C.HERE/label
    dest.mkdir()
    assert not (historical_check and runtime_check)
    assert 0 < stop_after <= 20 and 300 <= frame_count <= 900
    plane_read_after = .25
    numerator = {0:120000,2997:240000,23976:240000,27972:280000}[rank]
    expected_engine = 60.0 if rank==0 else float(np.float32(numerator/1001))
    proof = {'phase':'preflight','label':label,'requested_rank':rank,'requested_quality_enum':quality,'no_camera_poll_during_capture':quiet,
             'bounded_preview_diagnostic':planes,
             'plane_read_requested_after_seconds':plane_read_after if planes else None,
             'one_processing_rate_read_during_capture':bool(rate_probe),
             'stop_after_seconds':stop_after,'start_sent':False,'stop_sent':False,
             'observed_recording':False,'rec_samples':[]}
    def save():
        (dest/'trial.json').write_text(json.dumps(proof,indent=2)+'\n')
    with open('/tmp/fp-af-fusion.lock','r') as lease:
        fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
        r = C.snapshot()
        proof['runtime_before'] = r
        assert r['screen']=='LV_CINE_MEDIUM' and C.recording()==0
        assert re.fullmatch(r'\s*app_current -> 2\s*',C.live.checked_sh('status get app_current'))
        if runtime_check:
            proof['candidate_checks_before'] = runtime_check(r,quality)
        elif historical_check:
            proof['historical_capture_before'] = historical_check(r,quality)
        else:
            assert r['registry']['lock']==0 and r['registry']['provider']==0x42414c52
            assert r['producer']['applied_valid']==1 and r['producer']['applied_geometry']==12
            assert [r['producer'][k] for k in ('out_w','out_h','bin_h','bin_v','crop_w','crop_h','lens_on','output_policy')]==[992,662,1,1,0,0,0,0]
            assert r['consumer']['flag']==1 and r['consumer']['current']==r['registry']['row']+1
            assert r['quality_getter'].strip()==str(quality)
            assert r['fps_state']['VRATE']==rank and r['picked_entry']['VRATE']==rank
            assert r['engine_fps']==expected_engine
            expected_sensor = numerator/1001
            assert abs(r['sensor_timing_fps']-expected_sensor)<.001
        assert r['rate_notification']['RATE_LVOWED']==0
        if observe:
            # Verified fixed native object, no allocation or rotating pointer walk.
            assert C.live.putfile.mem_get(0xc2f1f3d8,tries=1)==[0xc3520cd0]
            assert C.live.putfile.mem_get(0xc3520cd0,tries=1)==[0xc0b99474]
            proof['native_observations']=[]
        proof['file_tool_slot'] = C.live.checked_sh('sdcard slot')
        proof['audio_getter'] = C.live.checked_sh('menu SetAudioRecSupport').strip()
        assert proof['audio_getter'] in ('0', '1')
        proof['clips_before'] = clips()
        save()
        raw = dest/'hdmi.rgb'
        clock = TrialClock(dest/'timeline.jsonl',raw,FRAME_BYTES)
        with (dest/'ffmpeg.log').open('w') as log:
            proc = subprocess.Popen(['ffmpeg','-hide_banner','-loglevel','info',
                '-f','avfoundation','-framerate','30','-pixel_format','uyvy422',
                '-i','AVerMedia ExtremeCap UVC:none','-vf','scale=1024:576',
                '-fps_mode','passthrough','-frames:v',str(frame_count),'-pix_fmt','rgb24',
                '-fs',str((frame_count+1)*FRAME_BYTES),'-f','rawvideo',str(raw)],stdout=subprocess.DEVNULL,stderr=log)
            proof['capture_pid'] = proc.pid
            clock.mark('capture_started',pid=proc.pid)
            try:
                start_capture = time.monotonic()
                while not raw.exists() or raw.stat().st_size<24*FRAME_BYTES:
                    assert proc.poll() is None
                    assert time.monotonic()-start_capture<10
                    time.sleep(.05)
                text = (dest/'ffmpeg.log').read_text()
                assert "from 'AVerMedia ExtremeCap UVC:none'" in text and '1920x1080' in text
                frames = np.memmap(raw,np.uint8,'r',shape=(24,576,1024,3))
                scene = frames[20,45:520,70:954].mean(axis=2)
                proof['scene_before'] = {'p99':float(np.percentile(scene,99)),
                                        'spatial_std':float(scene.std())}
                proof['overlay_before'] = overlay(frames[20])
                del frames
                assert proof['overlay_before']['standby_visible'],'No visible STBY; no key sent'
                assert proof['scene_before']['p99']>=5 and proof['scene_before']['spatial_std']>=3
                assert rec(clock,'before_start')==0
                if planes:
                    proof['planes_before'] = read_planes(C.live.putfile.mem_get,clock,'standby_before')
                    assert rec(clock,'after_planes_before_start')==0
                start = time.monotonic()
                clock.mark('start_requested')
                proof.update(phase='record_start',start_sent=True,
                             capture_frames_before_start=raw.stat().st_size//FRAME_BYTES)
                save()
                pulse(clock,'start')
                if rate_probe:
                    # This task's probe is one fixed native engine word,
                    # independently observed while REC is still positive.
                    time.sleep(max(0,.20-(time.monotonic()-start)))
                    current = rec(clock,'before_one_processing_rate_read')
                    proof['rec_samples'].append([time.monotonic()-start,current])
                    if current:
                        proof['observed_recording'] = True
                        clock.mark('processing_rate_read_begin')
                        proof['processing_rate_during'] = rate_probe()
                        clock.mark('processing_rate_read_end')
                    else:
                        proof['processing_rate_read_skipped_already_stopped'] = True
                    save()
                if planes:
                    # One bounded diagnostic window. No pointer walk, retries,
                    # file tools or repeated polling while capture is active.
                    time.sleep(max(0,plane_read_after-(time.monotonic()-start)))
                    current = rec(clock,'before_plane_diagnostic')
                    proof['rec_samples'].append([time.monotonic()-start,current])
                    if current:
                        proof['observed_recording'] = True
                        proof['planes_during'] = read_planes(C.live.putfile.mem_get,clock,'record_transition')
                        proof['planes_recording_after'] = rec(clock,'after_plane_diagnostic')
                    else:
                        proof['planes_skipped_already_stopped'] = True
                    save()
                if quiet or planes:
                    # No shell, memory reads, or file tools while frames run.
                    # A single fresh getter at target time gates the stop key.
                    time.sleep(max(0,stop_after-(time.monotonic()-start)))
                while time.monotonic()-start<stop_after+2:
                    current = rec(clock)
                    proof['rec_samples'].append([time.monotonic()-start,current])
                    if (quiet or planes) and current==0:
                        proof['rec_zero_at_stop_target']=True
                        proof['spontaneous_stop']=True
                        clock.mark('rec_zero_at_stop_target')
                        break
                    if observe:
                        sample={'elapsed':time.monotonic()-start,'recording_before':current,'words':{}}
                        for name,address,count in (('pool_free',0xc3521dfc,1),('capture_count_limit',0xc352017c,2),('writer_requests',0xc359be68,1),('writer_finished',0xc359bea0,1),('engine',0xc31df574,1)):
                            sample['words'][name]=C.live.putfile.mem_get(address,count,tries=1)
                        sample['elapsed_end']=time.monotonic()-start
                        proof['native_observations'].append(sample)
                    if current:
                        proof['observed_recording'] = True
                    elif proof['observed_recording']:
                        proof['spontaneous_stop'] = True
                        clock.mark('spontaneous_rec_zero')
                        break
                    if current and time.monotonic()-start>=stop_after:
                        if rec(clock,'before_stop'):
                            proof['stop_sent'] = True
                            save()
                            clock.mark('stop_requested')
                            pulse(clock,'stop')
                        else:
                            proof['spontaneous_stop'] = True
                        break
                    time.sleep(.04)
                for _ in range(60):
                    if rec(clock,'after_stop')==0:
                        proof['native_rec_zero_after'] = True
                        break
                    time.sleep(.05)
                else:
                    raise RuntimeError('REC remains positive; no toggle replay')
                save()
                assert proc.wait(timeout=15)==0
                assert raw.stat().st_size==frame_count*FRAME_BYTES
                clock.mark('capture_completed')
                proof['capture_frames'] = frame_count
                frames = np.memmap(raw,np.uint8,'r',shape=(frame_count,576,1024,3))
                proof['overlay_after'] = [overlay(f) for f in frames[-5:]]
                proof['standby_after'] = all(f['standby_visible'] for f in proof['overlay_after'][-3:])
                del frames
            except BaseException as exc:
                proof['error'] = repr(exc)
                raise
            finally:
                if proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=5)
                save()
                clock.mark('capture_cleanup',returncode=proc.poll())
        assert proof['standby_after'],'REC=0 but no HDMI STBY; no file tools or further trial'
        time.sleep(1)
        assert C.recording()==0
        proof['record_log'] = C.live.checked_sh('rec log-out')
        proof['clips_after'] = clips()
        proof['new_clips'] = sorted(proof['clips_after'].keys()-proof['clips_before'].keys())
        proof['runtime_after'] = C.snapshot()
        if runtime_check:
            proof['candidate_checks_after'] = runtime_check(proof['runtime_after'],quality)
        elif historical_check:
            proof['historical_capture_after'] = historical_check(proof['runtime_after'],quality)
        if planes:
            proof['planes_after'] = read_planes(C.live.putfile.mem_get,clock,'standby_after')
        proof['phase'] = 'captured'
        save()
        if (quiet or planes) and not proof['observed_recording']:
            proof['spontaneous_stop']=bool(proof.get('rec_zero_at_stop_target') and not proof['stop_sent'])
            proof['recording_verified_by_nonzero_finished_count']=bool(re.search(r'fin_cnt=[1-9][0-9]*,',proof['record_log']))
            save()
            assert proof['recording_verified_by_nonzero_finished_count']
        else:
            assert proof['observed_recording']
        print(json.dumps({k:proof[k] for k in ('label','new_clips','stop_sent',
            'spontaneous_stop','standby_after','phase','record_log') if k in proof},indent=2),flush=True)


if __name__=='__main__':
    main()
