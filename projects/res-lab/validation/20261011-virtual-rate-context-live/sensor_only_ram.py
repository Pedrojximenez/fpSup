"""Task-scoped data-only patch of four words in the pinned v17 consumer.

Native30 and the H2 row must first be selected using normal camera UI.
No code, native firmware word, writer, allocator or RCD file is changed.
No write replay; a failed readback leaves an explicit uncertain outcome.
"""
import fcntl
import json
import struct
import subprocess
import sys
import camera as C
from ogc_layout import S, ENT, VM, VM_BUF

sys.path.insert(0, str(C.HERE))
import record_trial
assert record_trial.__file__ == str(C.HERE / 'record_trial.py')

# Native29.97's processing profile declares exactly30.0. Writing29.97 would
# enter the firmware's fps<30 branch, unlike the native carrier profile.
ENGINE30 = 0x41F00000
MANIFEST = json.loads((C.HERE / 'h2-success-rcd/manifest.json').read_text())
WANT = MANIFEST['tested_entry']
OUT = C.HERE / 'sensor-only-ram'


def owned(r, patched, native_identity=False):
    assert C.recording() == 0
    assert C.value('MV_fpLossless') == 0
    assert r['quality_getter'].strip() == '0'
    assert r['fps_getter'].strip() == '3' and C.value('MV_FrameRate') == 3
    assert r['registry']['lock'] == 0
    # A registered RES-Lab recipe may remain idle on its separate row.
    # It cannot be the row selected for this static H2 experiment.
    assert r['registry']['provider'] in (0, 0x42414c52)
    if r['registry']['provider']:
        assert r['registry']['row'] != r['consumer']['current'] - 1
    assert r['consumer']['flag'] == 1 and r['consumer']['current'] > 0
    row = r['rows'][r['consumer']['current'] - 1]
    assert [row[k] for k in ('label', 'width', 'height', 'on')] == ['H2S240', 992, 662, 1]
    assert r['fps_state']['VRATE'] == 0 and r['picked_entry']['VRATE'] == 0
    e = r['picked_entry']
    assert [e[k] for k in ('W0', 'W1')] == [WANT['w0'], WANT['w1']]
    assert [e[k] for k in ('ENGFPS', 'NOMINAL')] == ([ENGINE30, 30] if patched else [WANT['engfps'], 240])
    assert r['fps_state']['FPSLATCH'] == e['ENGFPS']
    core, s = int(r['consumer_base'], 16), int(r['consumer_state'], 16)
    pf = C.live.putfile
    # Offsets are validated against this exact verified resident allocation.
    end = pf.mem_get(s + S['S_END'], tries=1)[0]
    block = C.inspect.FACT['rescustom']['block']
    assert S['BODY'] < end and s + end <= core + block
    entry = s + r['fps_state']['LAST_ENT']
    assert s + S['BODY'] <= entry and entry + ENT['SIZE'] <= s + end
    ew = pf.mem_get(entry, ENT['SIZE'] // 4, tries=1)
    key = b''.join(w.to_bytes(4, 'little') for w in ew[5:9]).split(b'\0')[0]
    assert key == b'H2S24030'
    vms = pf.mem_get(s + S['VMS'], tries=1)[0]
    nvm = pf.mem_get(s + S['NVM'], tries=1)[0]
    assert 0 < nvm <= 16 and 0 <= e['VM'] < nvm
    assert S['BODY'] <= vms and vms + nvm * VM['SIZE'] <= end
    vm = s + vms + e['VM'] * VM['SIZE']
    vw = pf.mem_get(vm, 16, tries=1)
    clone_id = vw[VM['ID']//4]
    assert [vw[VM[k] // 4] for k in ('DONOR', 'FILLED')] == [12, 1]
    if native_identity:
        assert e['MODE'] == 12 and 230 <= clone_id <= 245
    else:
        assert clone_id == e['MODE']
    assert [vw[VM[k] // 4] for k in ('TW0', 'TW1', 'NOM')] == [WANT['w0'], WANT['w1'], 30 if patched else 240]
    tim = vw[VM['PTR'] // 4]
    assert vm + VM_BUF['TIM'] <= tim and tim + 32 <= vm + VM_BUF['TIM'] + 64
    tw = pf.mem_get(tim, 8, tries=1)
    assert tw[1:3] == [WANT['w0'], WANT['w1']]
    if native_identity:
        desc = pf.mem_get(0xC343B588, tries=1)[0]
        # Fixed native descriptor; refuse an unknown owner rather than walk it.
        assert desc == 0xC2F1E654
        assert pf.mem_get(0xC2F1E654, 2, tries=1) == [0xC0B59500, 70]
        native_tim = 0xC0B59A40
        native_words = pf.mem_get(native_tim,8,tries=1)
        with (C.ROOT/'out/MAIN_c0000000.bin').open('rb') as rom:
            rom.seek(native_tim-0xc0000000)
            original = list(struct.unpack('<8I',rom.read(32)))
        assert native_words == original and native_words[0] == 12
        assert native_words[1:3] == [WANT['w0'], WANT['w1']]
        tim,tw = native_tim,native_words
    bulk = pf.mem_get(0xC0B9E5D8, tries=1)[0]
    # The released Lossless REC hook restores stock64MiB for every OFF take.
    # The previous ON take can leave4MiB visible in standby until that hook.
    assert bulk in (0x400000, 0x4000000), hex(bulk)
    actual_engine = pf.mem_get(0xC31DF574, tries=1)[0]
    return {'state': hex(s), 'entry': hex(entry), 'entry_words': ew,
            'vm': hex(vm), 'vm_words': vw, 'tim': hex(tim), 'tim_words': tw,
            'sensor_timing_fps': 72000000 / ((tw[1] & 65535) * ((tw[2] & 65535) - 1) + (tw[1] >> 16)),
            'native_engine_word': actual_engine,
            'native_engine_fps': struct.unpack('<f', struct.pack('<I', actual_engine))[0],
            'consumer_canvas_fps': r['engine_fps'], 'global_bulk_bytes': bulk,
            'native_application_rate': '30000/1001', 'shutter_nominal': 30 if patched else 240,
            'sensor_mode_id':e['MODE'],'native_identity':native_identity,
            'nominal_note':'Virtual nominal setting is unused by native12 lookup.' if native_identity else 'Virtual clone nominal setting is active.',
            'sensor_cadence_measured': False}


def visible_standby():
    import numpy as np
    raw = OUT / 'preflight.rgb'
    with (OUT / 'preflight-ffmpeg.txt').open('w') as log:
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'info',
            '-f', 'avfoundation', '-framerate', '30', '-pixel_format', 'uyvy422',
            '-i', 'AVerMedia ExtremeCap UVC:none', '-vf', 'scale=1024:576',
            '-frames:v', '24', '-pix_fmt', 'rgb24', '-f', 'rawvideo', str(raw)],
            stdout=subprocess.DEVNULL, stderr=log, check=True, timeout=12)
    assert raw.stat().st_size == 24 * record_trial.FRAME_BYTES
    frames = np.memmap(raw, np.uint8, 'r', shape=(24, 576, 1024, 3))
    result = [record_trial.overlay(f) for f in frames[-3:]]
    assert all(o['standby_visible'] for o in result)
    del frames
    assert C.recording() == 0
    return result


def prepare(output_dir=None, standby_check=None):
    dest = output_dir or OUT
    dest.mkdir(exist_ok=True)
    assert not any(dest.iterdir()), 'Refusing to replay or overwrite a previous patch'
    proof = {'phase': 'preflight', 'writes': [], 'scope': 'four consumer-owned data words; temporary RAM only'}
    save = lambda: (dest / 'patch.json').write_text(json.dumps(proof, indent=2) + '\n')
    with open('/tmp/fp-af-fusion.lock') as lease:
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        r = C.snapshot()
        proof['runtime_before'] = r
        save()
        import lossless_snapshot
        proof['lossless_before'] = lossless_snapshot.snapshot()
        assert proof['lossless_before']['fields']['settings_on'] == 0
        assert r['screen'] == 'LV_CINE_MEDIUM'
        old = owned(r, False)
        proof['owned_before'] = old
        proof['standby_before'] = (standby_check or visible_standby)()
        save()
        s, e, vm = (int(old[k], 16) for k in ('state', 'entry', 'vm'))
        edits = [(e + ENT['ENGFPS'], WANT['engfps'], ENGINE30),
                 (e + ENT['NOMINAL'], 240, 30),
                 (s + S['FPSLATCH'], WANT['engfps'], ENGINE30),
                 (vm + VM['NOM'], 240, 30)]
        for address, expected, new in edits:
            assert C.recording() == 0
            assert C.live.putfile.mem_get(address, tries=1) == [expected]
            proof['phase'] = 'write_requested'
            proof['writes'].append({'address': hex(address), 'before': expected, 'after': new, 'verified': False})
            save()
            C.live.putfile.mem_set(address, new)
            got = C.live.putfile.mem_get(address, tries=1)
            assert got == [new], (hex(address), got, new)
            proof['writes'][-1]['verified'] = True
            save()
        r = C.snapshot()
        proof['runtime_after'] = r
        proof['owned_after'] = owned(r, True)
        proof['phase'] = 'patched'
        save()
        print(json.dumps(proof['owned_after'], indent=2), flush=True)


def check(r, quality):
    assert quality == 0
    result = owned(r, True)
    assert r['rate_notification']['RATE_LVOWED'] == 0
    assert r['sensorlab_profile']['M12_LEGACY_HITS'] == 0
    return result


if __name__ == '__main__':
    assert sys.argv[1:] == ['prepare']
    prepare()
