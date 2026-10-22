#!/usr/bin/env python3
"""T0: one bounded EP83 transfer of bytes the host itself wrote.

This isolates the transport. No hook, no AF data, no capture format: the host
writes a known pattern into its own DMA-capable allocation, asks the camera to
start one EP83 transfer of exactly that many bytes, and compares what comes back.
A pass means the endpoint, the TRB, the DMA and the daemon's framing work
together once. It means nothing about AF, and it is not a continuous session.

Single owner throughout: the maintained text worker keeps EP 0x01 and EP 0x82,
and the sender is reached through the borrowed echo inside one ordinary `shl`
command, so the daemon's terminal is the worker's own reply frame. The mode-5
CMD4 adapter is deliberately not used; two owners of EP01/EP82 is what the
transport audit forbids.

Nothing here is retried. An uncertain OUT, an uncertain EP83 read or a missing
terminal leaves the camera possibly still owning the buffer, so the run stops and
the allocation is retained for the rest of the boot.
"""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import struct
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(ROOT / 'research/autofocus'))
from focus_bridge import BridgeError, LOCK

if __package__:
    from . import af_hook_trial as trial, user_alloc
else:
    import af_hook_trial as trial
    import user_alloc

SHELL = ROOT / 'fpSup/fp_usb_shell'
SENDER = HERE / 'ep83_send.S'
ECHO, ORIGINAL = trial.ECHO, trial.ORIGINAL
DCACHE, ICACHE = trial.DCACHE, trial.ICACHE
SENDER_MAX = 512
PARAM_BYTES = 32
MAX_BYTES = 0x10000
# The host daemon must be one that speaks EP83. The binary that has been running
# since 2026-09-25 does not; STATUS reports transport=EP01-EP82 and the image has
# no EP83 string at all. Rebuilding and restarting it is a live step of its own.
DAEMON_REQUIREMENT = 'fpshd built from a source containing the EP83 consumer'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def pattern(length, nonce):
    """A payload only this run could have produced, and cheap to verify."""
    if length % 4 or not 4 <= length <= MAX_BYTES:
        raise ValueError('length must be a multiple of 4 in 4..65536')
    words = [(nonce ^ (index * 0x9E3779B9)) & 0xffffffff
             for index in range(length // 4)]
    return struct.pack('<%dI' % len(words), *words)


def sender_bytes():
    """The sender's size, which every parameter address produces: for the claim."""
    return len(sender_image(0xC072E400))


def sender_image(param):
    asm = trial.build._assembler()
    code = asm.assemble(SENDER, [f'EP83_P={param}'])
    if not 0 < len(code) <= SENDER_MAX or len(code) % 4:
        raise ValueError('sender image size rejected')
    return code


class T0IO(trial.TrialIO):
    """The trial transport, without any authority over the AF callsite."""

    def __init__(self, event=lambda row: None):
        super().__init__(event=event)
        self.special.pop(trial.fmt.CALLSITE, None)

    def ep83(self, length, line='echo', *, timeout=4.0):
        """`EP83 <bytes> <shellline>` -> OK83 header, then exactly <bytes>."""
        if not 1 <= length <= MAX_BYTES:
            raise ValueError('invalid EP83 length')
        self._wait_for_gap()
        started = time.monotonic()
        deadline = started + timeout
        try:
            with socket.socket(socket.AF_UNIX) as sock:
                sock.settimeout(timeout)
                sock.connect(self.path)
                sock.sendall(f'EP83 {length} {line}\n'.encode())
                raw = bytearray()
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError('EP83 outcome uncertain')
                    sock.settimeout(remaining)
                    part = sock.recv(8192)
                    if not part:
                        break
                    raw += part
                    if b'\n' in raw and len(raw) >= raw.index(b'\n') + 1 + length:
                        break
                    if len(raw) > length + 256:
                        raise BridgeError('oversized EP83 reply')
            if not raw.startswith(b'OK83 '):
                raise BridgeError(f'EP83 rejected: {bytes(raw[:200])!r}')
            head, _, rest = bytes(raw).partition(b'\n')
            fields = head.split()
            if len(fields) != 3 or int(fields[1]) != length or len(rest) != length:
                raise BridgeError(f'EP83 header/body mismatch: {head!r} {len(rest)}')
            elapsed = time.monotonic() - started
            self.event(dict(event='ep83_receive', bytes=len(rest), sequence=int(fields[2]),
                            sha256=digest(rest), elapsed_s=elapsed))
            return rest, int(fields[2]), elapsed
        except BaseException:
            self._latch_transport_fault()
            raise
        finally:
            self._last_exchange_end = time.monotonic()


class Borrow:
    """The single owner of the echo handler for this run."""

    def __init__(self, io):
        self.io, self.held = io, False

    def echo(self, address):
        current = self.io.read(ECHO)[0]
        if current not in self.io.special[ECHO]:
            raise BridgeError('unknown echo owner')
        self.held = address is not None and address != ORIGINAL
        self.io.word(ECHO, ORIGINAL if address is None else address)

    def publish(self):
        for function in (DCACHE, ICACHE):
            self.echo(function)
            self.io.shell('echo')
        self.echo(None)


def boot_allocator(nonce, *, borrow=None):
    """Claim this boot's cave blocks and take one owned DMA-capable allocation.

    The sender and its parameters live in the cave; the payload buffer is the
    128-byte-aligned base of a 64 KiB USER allocation the reviewed helper took
    and whose non-cached mapping it verified. Nothing is freed afterwards.
    """
    def allocate(io, emit):
        prefix = f'ep83t0.{nonce:08x}'
        param, code_at, helper, helper_param = user_alloc.claim(
            io, emit,
            [(prefix + '.param', PARAM_BYTES), (prefix + '.sender', sender_bytes()),
             (prefix + '.helper', 1536), (prefix + '.helper_param', 128)])
        owner = borrow or Borrow(io)
        io.special[ECHO].update({code_at, helper})
        asm = trial.build._assembler()
        # The worker's own pool and body: the allocator must not hand either back.
        pool, size, worker = io.read(trial.WORKER, 3)
        worker_body = trial.offline_sources()[2]
        _receipt, _raw, base = user_alloc.allocate(
            io, emit, helper_image=asm.assemble(trial.HELPER, [f'AF_PROBE_P={helper_param}']),
            helper_at=helper, param_at=helper_param,
            echo=owner.echo, publish=owner.publish,
            exclude=((pool, size), (worker, len(worker_body))))
        return param, code_at, base
    return allocate


def run(io, emit, output, *, length=4096, nonce, allocate, borrow=None):
    """`allocate` returns (param, code, buffer) for this boot; it owns the memory."""
    result = dict(schema='fp.ep83-t0/v1', status='preparing', transport='EP83',
                  af_data=False, continuous_session=False, bytes=length, nonce=nonce,
                  single_owner='maintained text worker; sender reached through echo')
    payload = pattern(length, nonce)
    retained = []
    owner = borrow or Borrow(io)
    try:
        if io.read(ECHO)[0] != ORIGINAL:
            raise BridgeError('echo is borrowed')
        param, code_at, buffer = allocate(io, emit)
        retained = [dict(name='sender parameters', address=param, bytes=PARAM_BYTES),
                    dict(name='sender code', address=code_at, bytes=SENDER_MAX),
                    dict(name='DMA buffer', address=buffer, bytes=length)]
        result['allocation'] = dict(param=param, code=code_at, buffer=buffer)
        image = sender_image(param)
        io.put(code_at, image)
        io.put(param, bytes(PARAM_BYTES))
        io.put(buffer, payload)
        result['sender_sha256'] = digest(image)
        result['payload_sha256'] = digest(payload)
        owner.publish()
        io.word(param + 8, buffer)
        io.word(param + 0xC, length)
        io.word(param + 0x10, 1500)
        io.word(param, 1)
        emit(dict(event='ep83_send_intent', param=param, buffer=buffer, bytes=length,
                  sender=code_at, retained=retained))
        owner.echo(code_at)
        received, sequence, elapsed = io.ep83(length)
        owner.echo(None)
        receipt = io.read(param, PARAM_BYTES // 4)
        result.update(receipt=receipt, sequence=sequence, elapsed_s=elapsed,
                      received_sha256=digest(received))
        (output / 'received.bin').write_bytes(received)
        if receipt[1] != 0:
            raise BridgeError(f'sender status {receipt[1]}; see ep83_send.S')
        if received != payload:
            first = next((i for i in range(len(payload)) if received[i:i+1] != payload[i:i+1]), None)
            raise BridgeError(f'payload mismatch at byte {first}')
        result.update(status='delivered', bytes_per_second=length / elapsed if elapsed else None)
    except BaseException as exc:
        result.update(status='failed', error=repr(exc))
    finally:
        if owner.held and not io.transport_faulted:
            try:
                owner.echo(None)
            except BaseException as exc:
                result['echo_error'] = repr(exc)
        result['echo_restored'] = (not io.transport_faulted
                                   and io.read(ECHO)[0] == ORIGINAL)
        result['transport_faulted'] = io.transport_faulted
        # Every claim is kept for the rest of the boot: an uncertain transfer may
        # still own the buffer, and nothing here can prove the controller is done.
        result['resources_retained'] = retained
        result['reclamation_proven'] = False
        (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--inspect', action='store_true')
    mode.add_argument('--run-live', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--bytes', type=int, default=4096)
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=False)
    if args.inspect:
        image = sender_image(0xC072E400)
        report = dict(offline_only=True, sender_bytes=len(image),
                      sender_sha256=digest(image),
                      source_sha256=digest(SENDER.read_bytes()),
                      endpoint=dict(address=0x83, logical=3, physical=7,
                                    trb_table=0xC31E3270, control=0x813),
                      af_data=False, continuous_session=False,
                      delivery_verified=False,
                      requires=[DAEMON_REQUIREMENT,
                                'a cave claim for the sender and its parameters',
                                'a DMA-capable allocation the caller owns',
                                'the stock PTP event sender shown not to contend '
                                'for the same TRB in this boot'])
        (args.output / 'inspect.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2))
        return 0
    raise SystemExit('--run-live needs an allocator for this boot; see run(); '
                     'no camera operation is performed by this entry point')


if __name__ == '__main__':
    raise SystemExit(main())
