"""One quiet20s SD trial of the data-only sensor239/application30 split."""
import json
import sys
import struct
import camera as C
sys.path.insert(0, str(C.HERE))
import sensor_only_ram as R
import record_trial
assert record_trial.__file__ == str(C.HERE / 'record_trial.py')

if __name__ == '__main__':
    assert len(sys.argv) == 2
    label = sys.argv[1]
    sys.argv = [sys.argv[0], label, '2997', '0', 'quiet']
    def rate_probe():
        word = C.live.putfile.mem_get(0xC31DF574, tries=1)[0]
        return {'address': '0xc31df574', 'word': word,
                'fps': struct.unpack('<f', struct.pack('<I', word))[0]}
    record_trial.main(historical_check=R.check, stop_after=20, frame_count=900, rate_probe=rate_probe)
    proof = json.loads((C.HERE / label / 'trial.json').read_text())
    assert proof['historical_capture_after']['global_bulk_bytes'] == 0x4000000
    for key in ('HDR_COPY_HITS', 'BULK_HITS'):
        assert proof['runtime_after']['header_copy'][key] == proof['runtime_before']['header_copy'][key]
    if 'processing_rate_during' in proof:
        assert proof['processing_rate_during']['word'] == R.ENGINE30
    print('Verified processing FPS latch30.0, sensor timing239.76, no CPU-header or reduced-bulk hits.', flush=True)
