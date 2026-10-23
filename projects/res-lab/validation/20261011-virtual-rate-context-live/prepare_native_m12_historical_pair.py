"""Prepare one data-only native12/H2 comparison; never starts recording.

Requires H2 selected through normal UI, application2997, LosslessOFF and the
original reconstructed H2 engine239.76/nominal240. Refuses a prior manifest,
an unknown resident image, changed entry, busy writer or non-STBY LCD.
"""
import fcntl
import json
import sys
import camera as C
sys.path.insert(0, str(C.HERE))
import native_lcd as LCD
import sensor_only_ram as R
from ogc_layout import ENT

DEST = C.HERE / 'native-m12-historical-pair-ram'


def prepare():
    assert sys.argv[1:] == ['prepare']
    assert 'OK' in (C.HERE / 'native-m12-historical-pair-offline.txt').read_text()
    DEST.mkdir()
    proof = {'phase': 'preflight', 'recording_started': False,
             'scope': 'one consumer-owned entry MODE word; temporary RAM only',
             'application_rate': '30000/1001', 'processing_fps_inferred_predecessor': 240000/1001,
             'nominal': 240, 'exact_old_binary_identified': False}
    save = lambda: (DEST / 'patch.json').write_text(json.dumps(proof, indent=2) + '\n')
    save()
    with open('/tmp/fp-af-fusion.lock') as lease:
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        proof['idle_before'] = LCD.idle()
        r = C.snapshot()
        proof['runtime_before'] = r
        save()
        before = R.owned(r, False)
        proof['owned_before'] = before
        import lossless_snapshot
        proof['lossless_before'] = lossless_snapshot.snapshot()
        assert proof['lossless_before']['fields']['settings_on'] == 0
        assert proof['lossless_before']['on_getter'] == 0
        assert r['screen'] == 'LV_CINE_MEDIUM'
        assert r['producer']['applied_valid'] == 0 and r['registry']['provider'] == 0
        # Validate the fixed native descriptor and unchanged native TIM before
        # the write as well as afterwards. R.owned checks all clone bounds.
        pf = C.live.putfile
        assert pf.mem_get(0xC343B588, tries=1) == [0xC2F1E654]
        assert pf.mem_get(0xC2F1E654, 2, tries=1) == [0xC0B59500, 70]
        native = pf.mem_get(0xC0B59A40, 8, tries=1)
        import struct
        with (C.ROOT / 'out/MAIN_c0000000.bin').open('rb') as rom:
            rom.seek(0xB59A40)
            assert native == list(struct.unpack('<8I', rom.read(32)))
        assert native[0] == 12 and native[1:3] == [R.WANT['w0'], R.WANT['w1']]
        proof['native_timing_before'] = native
        proof['standby_before'] = LCD.shot('native-m12-historical-before', DEST)
        address = int(before['entry'], 16) + ENT['MODE']
        original = r['picked_entry']['MODE']
        assert 230 <= original <= 245
        proof['write'] = {'address': hex(address), 'before': original, 'after': 12, 'verified': False}
        proof['idle_at_write'] = LCD.idle()
        assert pf.mem_get(address, tries=1) == [original]
        proof['phase'] = 'write_requested'
        save()
        pf.mem_set(address, 12)
        assert pf.mem_get(address, tries=1) == [12]
        proof['write']['verified'] = True
        proof['runtime_after'] = C.snapshot()
        proof['owned_after'] = R.owned(proof['runtime_after'], False, native_identity=True)
        proof['standby_after'] = LCD.shot('native-m12-historical-after', DEST)
        proof['phase'] = 'prepared_not_recorded'
        save()
    print(json.dumps(proof['write']), flush=True)


if __name__ == '__main__':
    prepare()
