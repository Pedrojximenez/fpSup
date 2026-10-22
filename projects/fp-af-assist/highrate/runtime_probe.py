"""Explicit, bounded, read-only fp 5.02 endpoint/pool diagnostic.

No I/O at import. Only STATUS, native version, and the two approved memory
reads are sent. No retries, pool dereference, echo borrowing, or USB opening.
The AF advisory lock does not exclude clients which ignore it; inspect owners
before running. A successful read is not a DMA lease or endpoint idle proof.
"""
import argparse
import fcntl
import json
from pathlib import Path
import sys
import time

CONTEXT_BASE = 0xC31E3888
POOL_POINTER = 0xC3757A7C
READS = ((CONTEXT_BASE, 28), (POOL_POINTER, 1))
BUILD_ID = '13aa621060efff11aaba9b21ad925005302605cf'


def probe(io):
    """Use existing Transport parsing, but deliberately bypass read retries."""
    status = io.request('STATUS', timeout=2.0).decode('ascii')
    if not status.startswith('OK ') or 'camera=open' not in status:
        raise RuntimeError('existing daemon has no open camera; no live reads')
    version = io.shell('version', timeout_ms=1000)
    if not all(part in version for part in ('w71c1', '5.02.0.V91', BUILD_ID)):
        raise RuntimeError('not the verified fp 5.02 build; no memory reads')
    blocks = []
    for address, count in READS:
        reply = io.shell('mem get 0x%08X,,0x%X' % (address, count * 4),
                         timeout_ms=1000)
        words = io._memory_words(reply, address, count)
        blocks.append({'address': address, 'words': words})
    contexts = []
    for index in range(7):
        mode, direction, endpoint, fourth = blocks[0]['words'][4*index:4*index+4]
        contexts.append({'index': index, 'mode': mode, 'direction': direction,
                         'endpoint': endpoint, 'fourth_word_raw': fourth})
    return {'schema': 'fp-af-runtime-read-v1', 'status': status,
            'version': version, 'blocks': blocks, 'contexts': contexts,
            'pool_pointer_raw': blocks[1]['words'][0],
            'camera_ram_writes': 0, 'lens_commands': 0,
            'endpoint_exclusive': False, 'pool_lease_verified': False,
            'controller_registers_read': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path,
                        help='new JSONL transcript; existing paths refused')
    parser.add_argument('--run-approved-read', action='store_true',
                        help='explicitly perform the documented live reads')
    args = parser.parse_args(argv)
    if not args.run_approved_read:
        parser.error('live read requires --run-approved-read')
    # Import of Transport is inert; do not create a FocusBridge RAM lease.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from focus_bridge import LOCK, Transport
    with args.output.open('x', encoding='utf-8') as output:
        def emit(event):
            output.write(json.dumps({'host_monotonic_s': time.monotonic(),
                                     **event}, sort_keys=True) + '\n')
            output.flush()
        emit({'event': 'scope', 'reads': READS, 'camera_ram_writes': 0,
              'retries': 0, 'socket': '/tmp/fpshd.sock'})
        try:
            with open(LOCK, 'a+') as lock:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                result = probe(Transport(event=emit))
                emit({'event': 'result', 'result': result})
            print(json.dumps(result, indent=2))
            return 0
        except Exception as exc:
            emit({'event': 'failed', 'error': repr(exc), 'retry_permitted': False})
            print(str(exc), file=sys.stderr)
            return 1


if __name__ == '__main__':
    raise SystemExit(main())
