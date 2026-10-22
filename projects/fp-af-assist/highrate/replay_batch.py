"""Validate a saved AFB1 batch offline; never connects to a camera.

The expected nonce must come from the capture owner's independent run record,
not from the input header. A valid file proves neither USB completion nor AF
freshness. Existing output files are never overwritten.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat

if __package__:
    from . import af_batch
else:
    import af_batch


def replay(path, *, expected_nonce):
    # Validate the nonce before reading any data. Only bounded regular files
    # are accepted; no device/FIFO input or unbounded read into memory.
    receiver = af_batch.BatchReceiver(expected_nonce=expected_nonce)
    descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as source:
        if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
            raise ValueError('batch input must be a regular file')
        raw = source.read(af_batch.MAX_BATCH_BYTES + 1)
    if not raw or len(raw) > af_batch.MAX_BATCH_BYTES:
        raise af_batch.CaptureError('empty or oversized batch file')
    decoded = receiver.feed(raw)
    receiver.finish()
    return {'schema': 'fp-af-offline-replay-v1',
            'input_sha256': hashlib.sha256(raw).hexdigest(),
            'input_bytes': len(raw), 'expected_nonce': expected_nonce,
            'offline_only': True, 'camera_io_performed': False,
            'usb_completion_verified': False, 'capture': decoded}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--expected-nonce', required=True, type=lambda n: int(n, 0))
    parser.add_argument('--output', required=True, type=Path,
                        help='new JSON report; must not already exist')
    args = parser.parse_args(argv)
    try:
        if args.output.exists():
            raise ValueError('output already exists')
        result = replay(args.input, expected_nonce=args.expected_nonce)
        with args.output.open('x', encoding='utf-8') as output:
            json.dump(result, output, indent=2, sort_keys=True)
            output.write('\n')
    except (OSError, ValueError) as exc:
        parser.exit(2, f'rejected: {exc}\n')
    print(json.dumps({'output': str(args.output.resolve()),
                      'count': result['capture']['count'],
                      'input_sha256': result['input_sha256'],
                      'usable_for_af_control': False,
                      'usb_completion_verified': False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
