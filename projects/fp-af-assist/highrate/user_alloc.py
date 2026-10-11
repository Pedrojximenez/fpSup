#!/usr/bin/env python3
"""Boot-scoped cave claims and one owned USER allocation, in one place.

Two callers need exactly this and must not drift: the AF publication trial and
the EP83 T0 transport trial. Both go through the maintained cave allocator
(fp_usb_shell/cave.py) rather than naming an address, and both make at most ONE
allocation attempt per parameter block -- a timeout is an uncertain outcome, not
a reason to ask again.

Nothing here frees, reuses or reclaims. Every claim and every allocation is kept
for the rest of the boot; a host handle proves nothing about what the camera
still owns.
"""
from __future__ import annotations

from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SHELL = ROOT / 'fpSup/fp_usb_shell'
sys.path.insert(0, str(ROOT / 'research/autofocus'))
from focus_bridge import BridgeError

ALLOC_BYTES = 0x10000
DMA_LOW, DMA_HIGH = 0x40000000, 0x80000000


def claim(io, emit, claims, *, retained=None):
    """Take each (name, bytes) from the camera's own bump allocator.

    The allocator's host register is a file; the camera holds one number. The
    strict transport is injected so its own retries cannot conceal an uncertain
    exchange, and the only write it may make is the bump pointer itself.
    """
    sys.path.insert(0, str(SHELL))
    import cave
    cave._check_agrees()
    old = cave._sh

    def command(*args, **kwargs):
        if args[:2] == ('mem', 'get'):
            address, _, size = args[2].partition(',,')
            at, count = int(address, 0), int(size, 0) // 4
            values = io.read(at, count)
            return '\n'.join(f'get : A:0x{at+i*4:08X}, D:0x{v:08X}'
                             for i, v in enumerate(values))
        if args[:2] == ('mem', 'set'):
            at, value = int(args[2], 0), int(args[3], 0)
            if at != cave.CAVE_BUMP or not cave.CAVE_ARENA <= value <= cave.CAVE_ARENA_END:
                raise ValueError('unexpected cave allocator write')
            io.special.setdefault(at, set()).add(value)
            io.word(at, value)
            return ''
        raise ValueError('unexpected cave operation')

    cave._sh = command
    try:
        before = cave.claims()
        if any(name in before for name, _ in claims):
            raise BridgeError('these claims already exist this boot; use a new nonce')
        out = []
        for name, size in claims:
            at = cave.claim(name, size)
            io.regions.append((at, at + size))
            entry = dict(name=name, address=at, bytes=size)
            if retained is not None:
                retained.append(entry)
            emit(dict(event='cave_claim', **entry))
            out.append(at)
        return out
    finally:
        cave._sh = old


def allocate(io, emit, *, helper_image, helper_at, param_at, echo, publish,
             exclude=(), retained=None, record=None):
    """One USER allocation through the reviewed helper. Never a second attempt.

    `echo(address)` borrows the echo handler, `publish()` performs the D/I cache
    maintenance; both come from the caller so there is one owner of that borrow.
    `exclude` is a list of (address, bytes) the allocator must not have handed
    back -- the worker's own pool and body. `record` is called with the raw
    receipt before any of it is judged, so a refusal still leaves the evidence
    behind. Returns (receipt, raw, base).
    """
    if len(helper_image) > 1536:
        raise BridgeError('helper exceeds its claimed region')
    io.put(param_at, bytes(64))
    io.put(helper_at, helper_image)
    publish()
    echo(helper_at)
    emit(dict(event='allocation_intent', helper=helper_at, param=param_at,
              bytes=ALLOC_BYTES))
    io.shell('echo')          # One allocation invocation; never repeated.
    echo(None)
    receipt = io.read(param_at, 16)
    if record is not None:
        record(receipt)
    if receipt[3] and retained is not None:
        # Keep even a refused mapping's raw receipt. It is never permission to
        # access or release that span.
        retained.append(dict(name='USER allocation receipt', address=receipt[3],
                             bytes=receipt[5], validated=False))
    if receipt[1] != 0 or receipt[2] != 1 or receipt[5] != ALLOC_BYTES or receipt[11] != 1:
        raise BridgeError(f'allocation/mapping refused: {receipt}')
    raw, base = receipt[3:5]
    if not DMA_LOW <= raw <= DMA_HIGH - ALLOC_BYTES or base != (raw + 127) & ~127:
        raise BridgeError('allocation result invalid')
    if any(raw < start + size and raw + ALLOC_BYTES > start for start, size in exclude):
        raise BridgeError('allocator returned an existing worker region')
    io.regions.append((raw, raw + ALLOC_BYTES))
    if retained is not None and retained and retained[-1].get('address') == raw:
        retained[-1].update(name='USER allocation', validated=True)
    return receipt, raw, base
