"""One bounded M12 recording with continuous, named HDMI capture.

Normal UI must select the requested rate first. Paired MOV keys are never
replayed; a stop toggle is sent only after a fresh REC=1 check. A spontaneous
stop is retained as evidence, not mistaken for permission to start again.
No clip subdirectory listing, file deletion, allocator experiment or private
firmware picker calls. Use an unused label to retain all evidence.
"""
import fcntl
import hashlib
import json
import os
import pathlib
import re
import subprocess
import struct
import sys
import time

import numpy as np

import engine_patch as guard
from trial_clock import TrialClock
live = guard.live
HERE = pathlib.Path(__file__).resolve().parent
FRAME_BYTES = 1024*576*3


def overlay_state(frame):
    """Observe the known HDMI REC/STBY plate; native REC=0 can precede drain."""
    rgb = frame[:40,440:650].astype(np.int16)
    red = (rgb[:,:,0] > 110) & (rgb[:,:,1] < 85) & (rgb[:,:,2] < 85)
    green = (rgb[:,:,1] > 110) & (rgb[:,:,0] < 85) & (rgb[:,:,2] < 85)
    counts = {'rec_pixels':int(red.sum()), 'standby_pixels':int(green.sum())}
    counts['standby_visible'] = counts['standby_pixels'] > 10 and counts['rec_pixels'] <= 10
    return counts


def recording(clock=None, action='recording_check'):
    out = (clock.command(live.checked_sh, 'status get is_recording', action)
           if clock else live.checked_sh('status get is_recording'))
    match = re.fullmatch(r'\s*is_recording -> ([01])\s*', out)
    assert match, out
    return int(match[1])


def clips():
    out = live.checked_sh('dir \\CINEMA')
    return {m[4]: ''.join(m.groups()[:3]) for m in
            re.finditer(r'^\s*(\d{4})/(\d{2})/(\d{2}).*\b(A\d{3}_\d{3})\s*$', out, re.M)}


def pulse(clock, action):
    try:
        clock.command(live.checked_sh, 'key MOVON', action+'_down')
    finally:
        time.sleep(.12)
        clock.command(live.checked_sh, 'key MOVOFF', action+'_up')


def main():
    label, rank = sys.argv[1], int(sys.argv[2])
    rollback_v38 = os.environ.get('RESLAB_VERIFY_V38') == '1'
    if rollback_v38:
        assert rank == 0, 'This runner verifies only restored 120p'
        assert hashlib.sha256((guard.CARD/'fpSup/32RESCUS.BIN').read_bytes()).hexdigest() == '0751f2e6b6d30f84d38e6b0b7447bd7cfe3f766bb9fd8e97048017ca586031f3'
    assert rank in (0,23976,27972)
    expected_engine = float(os.environ.get('RESLAB_DIAGNOSTIC_ENGINE', '60'))
    assert expected_engine in (30.0, 60.0)
    assert expected_engine == 60.0 or rank != 0
    expected_word = struct.unpack('<I', struct.pack('<f', expected_engine))[0]
    preview_half = os.environ.get('RESLAB_PREVIEW_DIAGNOSTIC', '') == 'half'
    assert not preview_half or (rank and expected_engine == 60.0)
    stop_after = float(sys.argv[3]) if len(sys.argv) > 3 else 2.0
    assert 0 <= stop_after <= 2
    if rank:
        # The REC flag precedes actual RAW writes. A first-REC stop can produce
        # only one DNG, so permit a bounded startup window; no sustained SD run.
        assert stop_after in (0, .85, 1.05, 1.2), 'High-rate SD preview requires bounded startup stop'
        if stop_after == 1.2:
            # One diagnostic window crossing the first RAW write, on the exact
            # restored v39 code with the offline-validated entry-only override.
            # Never interpret this as sustained high-rate SD validation.
            assert expected_engine == 30.0 or preview_half
            assert hashlib.sha256((guard.CARD/'fpSup/32RESCUS.BIN').read_bytes()).hexdigest() == '650c6fa0f27d216adba551cbec777741d42b39f4374e8b76db0f71dfbfe1cb85'
    trace_engine = os.environ.get('RESLAB_TRACE_ENGINE', '0') == '1'
    assert not trace_engine or (rank and stop_after == 1.05)
    trace_geometry = os.environ.get('RESLAB_TRACE_GEOMETRY', '0') == '1'
    assert not trace_geometry or stop_after in (.85, 1.2)
    dest = HERE/label
    dest.mkdir()
    proof = {'label':label, 'requested_rank':rank, 'stop_after_seconds':stop_after, 'phase':'preflight',
             'start_sent':False, 'stop_sent':False, 'observed_recording':False}
    proof['diagnostic_engine_fps'] = expected_engine
    def save():
        (dest/'trial.json').write_text(json.dumps(proof,indent=2)+'\n')
    with open('/tmp/fp-af-fusion.lock','r') as lease:
        fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
        checked = guard.collect(extra_engine=expected_word if expected_engine == 30.0 else None)
        if preview_half:
            from preview_half_patch import collect as collect_preview
            from preview_half_spec import CHANGES
            preview = collect_preview()
            assert all(t['value'] == CHANGES[t['key']][1] for t in preview['targets'])
            proof['diagnostic_preview_pairs'] = preview['pairs']
        r = checked['runtime']
        proof['runtime_before'] = r
        assert all(t['words'][guard.ENT['ENGFPS']//4] == (guard.OLD[t['rank']] if rollback_v38 else expected_word) for t in checked['targets'])
        assert r['screen'] == 'LV_CINE_MEDIUM' and recording() == 0
        assert re.fullmatch(r'\s*app_current -> 2\s*',live.checked_sh('status get app_current'))
        assert r['fps_state']['VRATE'] == rank and r['engine_fps'] == expected_engine
        assert r['picked_entry']['VRATE'] == rank and r['picked_entry']['ENGFPS'] == expected_word
        proof['file_tool_slot'] = live.checked_sh('sdcard slot')
        proof['clips_before'] = clips()
        save()
        raw = dest/'hdmi.rgb'
        clock = TrialClock(dest/'timeline.jsonl', raw, FRAME_BYTES)
        proof['timeline_file'] = 'timeline.jsonl'
        proof['timeline_limitation'] = 'host frame delivery and command intervals; unmeasured HDMI latency'
        if trace_geometry:
            from native_geometry import read_geometry
            proof['native_geometry'] = [read_geometry(live.putfile.mem_get, clock, 'standby_before')]
        with (dest/'ffmpeg.log').open('w') as log:
            proc = subprocess.Popen(['ffmpeg','-hide_banner','-loglevel','info',
                '-f','avfoundation','-framerate','30','-pixel_format','uyvy422',
                '-i','AVerMedia ExtremeCap UVC:none','-vf','scale=1024:576',
                '-fps_mode','passthrough','-frames:v','240','-pix_fmt','rgb24',
                '-fs','500M','-f','rawvideo',str(raw)],stdout=subprocess.DEVNULL,stderr=log)
            proof['capture_pid'] = proc.pid
            clock.mark('capture_started', pid=proc.pid)
            capture_start = time.monotonic()
            try:
                while not raw.exists() or raw.stat().st_size < 24*FRAME_BYTES:
                    assert proc.poll() is None, 'HDMI capture exited before recording'
                    assert time.monotonic()-capture_start < 10, 'No live HDMI frames'
                    time.sleep(.05)
                text = (dest/'ffmpeg.log').read_text()
                clock.mark('preflight_frames_ready')
                assert "from 'AVerMedia ExtremeCap UVC:none'" in text and '1920x1080' in text
                # UI overlays alone can change over a completely black image.
                # Require visible detail in the scene, excluding the overlays,
                # before creating a clip for the split-screen comparison.
                frames = np.memmap(raw, np.uint8, 'r', shape=(24,576,1024,3))
                scene = frames[20,45:520,70:954].mean(axis=2)
                proof['scene_before_start'] = {'p99':float(np.percentile(scene,99)),
                                               'spatial_std':float(scene.std())}
                proof['overlay_before_start'] = overlay_state(frames[20])
                del frames
                if not proof['overlay_before_start']['standby_visible']:
                    proof['phase'] = 'blocked_by_unconfirmed_standby'
                    save()
                    raise RuntimeError('HDMI has not returned to STBY; no recording key sent')
                if proof['scene_before_start']['p99'] < 5 or proof['scene_before_start']['spatial_std'] < 3:
                    proof['phase'] = 'blocked_by_dark_scene'
                    save()
                    raise RuntimeError('No visible scene detail; no recording key sent')
                assert recording(clock, 'before_start_check') == 0
                start = time.monotonic()
                clock.mark('start_requested')
                proof.update(phase='record_start', start_sent=True,
                             capture_frames_before_start=raw.stat().st_size//FRAME_BYTES)
                save()
                pulse(clock, 'start')
                proof['rec_samples'] = []
                while time.monotonic()-start < 4:
                    rec = recording(clock)
                    proof['rec_samples'].append([round(time.monotonic()-start,4),rec])
                    if rec:
                        if trace_geometry and not proof['observed_recording']:
                            proof['native_geometry'].append(read_geometry(live.putfile.mem_get, clock, 'first_rec_check'))
                            save()
                        proof['observed_recording'] = True
                    elif proof['observed_recording']:
                        proof['spontaneous_stop'] = True
                        clock.mark('spontaneous_rec_zero')
                        break
                    if (rank or rollback_v38) and rec and time.monotonic()-start < stop_after:
                        # Leave the recording worker undisturbed during this
                        # short interval, then freshly verify REC before stop.
                        time.sleep(max(0, stop_after-(time.monotonic()-start)))
                        continue
                    if proof['observed_recording'] and time.monotonic()-start >= stop_after:
                        if trace_engine and rec:
                            # Two source-traced scalar reads, once only. No
                            # allocator, code, DMA descriptor or MMIO access.
                            # They are independent reads, not an atomic snapshot.
                            stamp = time.monotonic()-start
                            words = {hex(a):live.putfile.mem_get(a,tries=1)[0]
                                     for a in (0xc31df574, 0xc31df724)}
                            proof['native_engine_reads'] = {
                                'start_elapsed':stamp, 'end_elapsed':time.monotonic()-start,
                                'words':words, 'limitation':'independent reads between fresh REC checks'}
                            save()
                        # The observation above is followed by a second fresh
                        # check, avoiding the old runner's unconditional toggle.
                        if recording(clock, 'before_stop_check'):
                            if trace_geometry:
                                proof['native_geometry'].append(read_geometry(live.putfile.mem_get, clock, 'before_stop'))
                                save()
                                # Reads can straddle a spontaneous stop; only
                                # a new positive check permits the toggle.
                                if not recording(clock, 'after_geometry_before_stop_check'):
                                    proof['spontaneous_stop'] = True
                                    clock.mark('spontaneous_rec_zero')
                                    break
                            proof['stop_sent'] = True
                            save()
                            clock.mark('stop_requested')
                            pulse(clock, 'stop')
                        break
                    time.sleep(.04)
                for _ in range(60):
                    if recording(clock, 'after_stop_check') == 0:
                        clock.mark('native_rec_zero_after')
                        break
                    time.sleep(.05)
                else:
                    raise RuntimeError('Still recording; no toggle replayed')
                proof['native_rec_zero_after'] = True
                if trace_geometry:
                    proof['native_geometry'].append(read_geometry(live.putfile.mem_get, clock, 'native_rec_zero_after'))
                save()
                assert proc.wait(timeout=15) == 0
                clock.mark('capture_completed')
                assert raw.stat().st_size == 240*FRAME_BYTES
                proof['capture_frames'] = 240
                frames = np.memmap(raw,np.uint8,'r',shape=(240,576,1024,3))
                proof['overlay_after'] = [overlay_state(frame) for frame in frames[-5:]]
                del frames
                # Require three consecutive positive STBY observations at the
                # end. Earlier frames can still belong to the stop transition.
                proof['standby_after'] = all(frame['standby_visible'] for frame in proof['overlay_after'][-3:])
            finally:
                if proc.poll() is None:
                    # This process belongs to this runner, not an existing OBS.
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=5)
                save()
                clock.mark('capture_cleanup', returncode=proc.poll())
        time.sleep(1)
        proof['record_log'] = live.checked_sh('rec log-out')
        if not proof['standby_after']:
            proof['phase'] = 'stop_incomplete'
            save()
            raise RuntimeError('Native REC=0 but HDMI did not return to STBY; no further recording or file tools')
        if trace_geometry:
            proof['native_geometry'].append(read_geometry(live.putfile.mem_get, clock, 'standby_visible_after'))
        after = clips()
        proof['clips_after'] = after
        proof['new_clips'] = sorted(after.keys()-proof['clips_before'].keys())
        proof['runtime_after'] = guard.fps_state.snapshot()
        assert proof['runtime_after']['fps_state']['VRATE'] == rank
        assert proof['runtime_after']['engine_fps'] == expected_engine
        proof['phase'] = 'captured'
        save()
        assert proof['observed_recording'], 'REC=1 was not observed; retain capture for inspection'
        print(json.dumps({k:proof[k] for k in ('label','new_clips','capture_frames',
            'observed_recording','stop_sent','spontaneous_stop','phase') if k in proof},indent=2))


if __name__ == '__main__':
    main()
