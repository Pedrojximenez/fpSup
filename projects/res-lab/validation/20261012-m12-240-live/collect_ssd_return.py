"""Collect preserved native logs and exact current identity after USB returns.

No keys, record toggles, reboot, log clearing or setting writes. The immutable
core is checked before any task-owned consumer diagnostic fields are read.
"""
import fcntl
import json
import sys

import camera as C


def main():
    assert sys.argv[1:] == ['after-control-reconnect']
    dest = C.HERE / 'ssd-camera-return.json'
    assert not dest.exists()
    proof = {'camera_mutations': False, 'phase': 'preflight'}
    save = lambda: dest.write_text(json.dumps(proof, indent=2) + '\n')
    with open('/tmp/fp-af-fusion.lock') as lease:
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        proof['idle'] = C.idle()
        proof['record_log'] = C.live.checked_sh('rec log-out')
        save()
        proof['slot'] = C.live.checked_sh('sdcard slot')
        try:
            proof['snapshot'] = C.snapshot()
            state = int(proof['snapshot']['consumer_state'], 16)
            keys = ('HDR_COPY_CALLS', 'HDR_COPY_HITS', 'HDR_COPY_SRC',
                    'HDR_COPY_DST', 'HDR_COPY_BYTES', 'HDR_COPY_WHY',
                    'HDR_COPY_FRAME', 'BULK_HITS', 'BULK_LAST', 'M12_LEGACY_HITS')
            proof['header_diagnostics'] = {k: C.live.putfile.mem_get(
                state + C.L.S[k], tries=1)[0] for k in keys}
            proof['phase'] = 'read_completed'
        except Exception as exc:
            proof['identity_or_read_error'] = type(exc).__name__ + ': ' + str(exc)
            proof['phase'] = 'native_log_saved_identity_unverified'
            save()
            raise
        save()
    print(json.dumps(proof, indent=2), flush=True)


if __name__ == '__main__':
    main()
