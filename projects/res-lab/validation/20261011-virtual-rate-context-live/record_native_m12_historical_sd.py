"""One20-second native12/H2 SD comparison, using native LCD drain guards.

No buffer, writer, new camera code, rate-word override, or SSD swap. The
separate prepared manifest must identify a verified one-word MODE change.
"""
import fcntl
import json
import re
import struct
import sys
import time
import camera as C
sys.path.insert(0, str(C.HERE))
import native_lcd as LCD
import sensor_only_ram as R
import record_trial as T

DEST = C.HERE / 'native-m12-historical-sd-quiet20'
PATCH = C.HERE / 'native-m12-historical-pair-ram/patch.json'


def check(r):
    result = R.owned(r, False, native_identity=True)
    assert r['rate_notification']['RATE_LVOWED'] == 0
    assert r['producer']['applied_valid'] == 0 and r['registry']['provider'] == 0
    assert r['sensorlab_profile']['M12_LEGACY_HITS'] == 0
    return result


def main():
    assert sys.argv[1:] == ['run']
    patch = json.loads(PATCH.read_text())
    assert patch['phase'] == 'prepared_not_recorded' and patch['write']['verified']
    assert patch['write']['after'] == 12
    DEST.mkdir()
    proof = {'phase': 'preflight', 'label': DEST.name, 'patch_manifest': str(PATCH),
             'stop_after_seconds': 20, 'start_sent': False, 'stop_sent': False,
             'spontaneous_stop': False, 'scope': 'native mode12; H2 sensor and processing239.76; nominal240; application2997; LosslessOFF; SD; original64MiB',
             'one_fixed_processing_rate_read': True, 'polling_during_capture': False,
             'no_new_camera_code_or_pipeline_patch': True}
    save = lambda: (DEST / 'trial.json').write_text(json.dumps(proof, indent=2) + '\n')
    save()
    with open('/tmp/fp-af-fusion.lock') as lease:
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        proof['idle_before'] = LCD.idle()
        r = C.snapshot()
        proof['runtime_before'] = r
        proof['checks_before'] = check(r)
        assert r['screen'] == 'LV_CINE_MEDIUM'
        assert re.fullmatch(r'\s*app_current -> 2\s*', C.live.checked_sh('status get app_current'))
        assert 'slot = sd0' in C.live.checked_sh('sdcard slot')
        proof['audio_getter'] = C.live.checked_sh('menu SetAudioRecSupport').strip()
        assert proof['audio_getter'] == '1'
        proof['lcd_before'] = LCD.shot('native-m12-historical-before-record', DEST)
        proof['clips_before'] = T.clips()
        clock = T.TrialClock(DEST / 'timeline.jsonl', DEST / 'unused.raw', 1)
        assert T.rec(clock, 'before_start') == 0
        proof.update(phase='record_start', start_sent=True)
        save()
        start = time.monotonic()
        T.pulse(clock, 'start')
        time.sleep(max(0, .20 - (time.monotonic() - start)))
        current = T.rec(clock, 'before_one_processing_rate_read')
        proof['recording_at_one_rate_read'] = current
        if current:
            word = C.live.putfile.mem_get(0xC31DF574, tries=1)[0]
            proof['processing_rate_during'] = {'address': '0xc31df574', 'word': word,
                                               'fps': struct.unpack('<f', struct.pack('<I', word))[0],
                                               'matches_expected': word == R.WANT['engfps']}
            # A mismatch is evidence, not an excuse to leave a started take
            # uncontrolled. Complete the same bounded stop procedure below.
        save()
        time.sleep(max(0, 20 - (time.monotonic() - start)))
        current = T.rec(clock, 'at_target20')
        proof['recording_at_target'] = current
        proof['elapsed_at_target'] = time.monotonic() - start
        if current:
            assert T.rec(clock, 'before_stop') == 1
            proof['stop_sent'] = True
            save()
            T.pulse(clock, 'stop')
        else:
            proof['spontaneous_stop'] = True
        for _ in range(10):
            if T.rec(clock, 'after_stop') == 0:
                break
            time.sleep(.5)
        else:
            raise RuntimeError('REC remains positive; no toggle replay or restore')
        proof['native_rec_zero_after'] = True
        proof['phase'] = 'drain_check'
        save()
        for attempt in range(6):
            try:
                proof['idle_after'] = LCD.idle()
                break
            except AssertionError as exc:
                proof['idle_pending'] = repr(exc)
                save()
                if attempt == 5:
                    raise
                time.sleep(2)
        proof['record_log'] = C.live.checked_sh('rec log-out')
        save()
        match = re.search(r'req_cnt=(\d+), fin_cnt=(\d+),', proof['record_log'])
        assert match, 'Missing native log; no clip reads or mode restore'
        req, fin = map(int, match.groups())
        proof['requested'], proof['finished'] = req, fin
        save()
        assert req == fin and req > 0, (req, fin)
        proof['lcd_after'] = LCD.shot('native-m12-historical-after-record', DEST)
        proof['standby_after'] = True
        proof['clips_after'] = T.clips()
        proof['new_clips'] = sorted(proof['clips_after'].keys() - proof['clips_before'].keys())
        r = C.snapshot()
        proof['runtime_after'] = r
        proof['checks_after'] = check(r)
        for key in ('HDR_COPY_HITS', 'BULK_HITS'):
            assert r['header_copy'][key] == proof['runtime_before']['header_copy'][key]
        assert proof['checks_after']['global_bulk_bytes'] == 0x4000000
        proof['twenty_second_recording_completed'] = bool(current and proof['stop_sent'])
        proof['phase'] = 'captured'
        save()
        print(json.dumps({key: proof[key] for key in ('phase', 'recording_at_target', 'stop_sent',
                         'spontaneous_stop', 'requested', 'finished', 'new_clips', 'record_log')}, indent=2), flush=True)


if __name__ == '__main__':
    main()
