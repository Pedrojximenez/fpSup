#!/usr/bin/env python3
"""One finite CINE AF publication hook, owned USER memory, existing EP82 bulk.

The data path does not poll. The site is armed, the host stays off the wire for
the observation window, the site is restored, and the whole buffer comes back in
ONE bulk read; the committed prefix is whatever the producer managed. Guards are
checked before arming and after restoring, not in a loop, so the hook window has
no USB traffic competing with it.

EP83 is deliberately not claimed by this runner. No camera access on import or
--inspect. A live run retains all claimed memory through the current boot; it
never frees/reuses potentially suspended hook code or an uncertain DMA buffer.
Power-off restoration is the shared loader's job, not this trial's: the AF
callsite is declared on the card as a four-byte section holding the firmware's
own word, stage2 journals it before the entry runs, and the loader's callback
writes it back. This trial only VERIFIES that, by finding the journal in the
manager's own lists and reading the word out of it -- before its first write and
again immediately before arming. It registers nothing and spends no list slot.
The borrowed echo is not journalled (on a cold start it may still be lent to
`lboot` when stage2 runs, so journalling it would restore the wrong word); the
host restores it on every path, and it points at cave code, which survives a warm
restart intact. Warm power cycling preserves firmware/cave but rebuilds heap.
"""
from __future__ import annotations

import argparse
import contextlib
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
from focus_bridge import Transport, BridgeError, LOCK
import af_cine_baseline as cine
if __package__:
    from . import (af_batch as fmt, build_publication as build,
                   hook_site_section as sites, shutdown_restore as restore,
                   user_alloc)
else:
    import af_batch as fmt
    import build_publication as build
    import hook_site_section as sites
    import shutdown_restore as restore
    import user_alloc

SHELL = ROOT / 'fpSup/fp_usb_shell'
HELPER = HERE / 'af_probe_helper.S'
ECHO, ORIGINAL = 0xC0BAC2F8, 0xC03D99A0
DCACHE, ICACHE = 0xC000E91C, 0xC000EABC
ALLOC_BYTES, STATE_OFF, RECORDS_OFF = 0x10000, 0x1040, 0x1080
BOOT_STAMP, WORKER = 0xC072F6F8, 0xC072F050
ROM_GUARDS = ((fmt.CALLSITE-12, 28), (fmt.PRODUCER, 16),
              (0xC023EC18, 12), (DCACHE, 16), (ICACHE, 16),
              (0xC001D740, 16), (0xC001D7F0, 16))
SHUTDOWN_BLOCKER = ('the AF callsite is not in the shared loader journal; declare it '
                    'as a four-byte card section holding the stock word')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def verify_shutdown_restore(io, *, vbin=None):
    """The loader's journal must already hold the AF callsite's stock word.

    Read-only: it finds the journal block through the manager's two lists and
    reads the recorded word out of it. Not operator-overridable; there is no flag
    that skips it. A verdict covers the word it names in the boot it was taken
    in, and is neither a quiescence proof nor any cover for a battery pull, for
    which no power-off callback runs at all.
    """
    try:
        return restore.require_site(io.read, fmt.CALLSITE, fmt.ORIGINAL_WORD,
                                    vbin=vbin)
    except restore.ShutdownRestoreError as exc:
        raise BridgeError(f'{SHUTDOWN_BLOCKER}: {exc}') from exc


def offline_sources():
    rom = (ROOT / 'out/seg0_c0000000.bin').read_bytes()
    if digest(rom) != build.ROM_SHA256:
        raise ValueError('unsupported firmware image')
    asm = build._assembler()
    worker_source = SHELL / 'camera/worker.S'
    worker = asm.assemble(worker_source)
    symbols = asm.symbols(worker_source)
    body = worker[symbols['wbody']:symbols['wbody_end']]
    if not 0 < len(body) < 0x10000 or len(body) % 4:
        raise ValueError('unexpected worker body')
    return rom, asm, body


class TrialIO(Transport):
    """No retries; large raw replies are bounded separately from shell reads."""
    def __init__(self, event=lambda row: None):
        super().__init__(event=event)
        self.regions = []
        self.special = {ECHO: {ORIGINAL, DCACHE, ICACHE},
                        fmt.CALLSITE: {fmt.ORIGINAL_WORD}}

    def read(self, address, count=1):
        if type(count) is not int or not 1 <= count <= 4096 or address & 3:
            raise ValueError('invalid bounded read')
        out = []
        for offset in range(0, count, 16):
            take = min(16, count-offset)
            at = address+offset*4
            out += self._memory_words(self.shell(f'mem get 0x{at:08X},,0x{take*4:X}'), at, take)
        return out

    def word(self, address, value):
        if address & 3 or type(value) is not int or not 0 <= value <= 0xffffffff:
            raise ValueError('invalid word')
        allowed = any(a <= address and address+4 <= b for a, b in self.regions)
        allowed |= value in self.special.get(address, ())
        if not allowed:
            raise ValueError(f'unowned write {address:08X}')
        current = self.read(address)[0]
        if address in (ECHO, fmt.CALLSITE) and current not in self.special[address]:
            raise BridgeError(f'unknown owner at {address:08X}; not overwritten')
        if current != value:
            self.shell(f'mem set 0x{address:08X} 0x{value:08X}')
            if self.read(address)[0] != value:
                raise BridgeError(f'write did not verify: {address:08X}; no blind retry')

    def put(self, address, data):
        if len(data) % 4:
            raise ValueError('unaligned image')
        for offset in range(0, len(data), 4):
            self.word(address+offset, struct.unpack_from('<I', data, offset)[0])
        actual = struct.pack('<%dI' % (len(data)//4), *self.read(address, len(data)//4))
        if actual != data:
            raise BridgeError('image readback mismatch')

    def bulk(self, length):
        if not 64 <= length <= fmt.MAX_CAPTURE_BYTES:
            raise ValueError('invalid finite bulk length')
        self._wait_for_gap()
        started = time.monotonic()
        deadline = started+3.0
        line = f'TMO 1500 BULK {length} echo'
        try:
            with socket.socket(socket.AF_UNIX) as sock:
                sock.settimeout(3.0)
                sock.connect(self.path)
                sock.sendall((line+'\n').encode())
                raw = bytearray()
                while True:
                    remaining = deadline-time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError('bulk outcome uncertain')
                    sock.settimeout(remaining)
                    part = sock.recv(8192)
                    if not part:
                        break
                    raw += part
                    if len(raw) > 2*length+16:
                        raise BridgeError('oversized bulk reply')
            if not raw.startswith(b'OKX '):
                raise BridgeError(f'bulk rejected: {bytes(raw[:160])!r}')
            body = bytes.fromhex(raw[4:].decode('ascii').strip())
            if len(body) != length:
                raise BridgeError('short or oversized finite capture')
            elapsed = time.monotonic()-started
            self.event(dict(event='ep82_bulk', bytes=len(body), sha256=digest(body), elapsed_s=elapsed))
            return body, elapsed
        except BaseException:
            self._latch_transport_fault()
            raise
        finally:
            self._last_exchange_end = time.monotonic()


class Probe:
    def __init__(self, io, emit):
        self.io, self.emit = io, emit
        self.helper = self.param = self.veneer = None
        self.branch = None
        self.hook_touched = False
        self.echo_owned = False
        self.retained = []

    def echo(self, address):
        current = self.io.read(ECHO)[0]
        if current not in self.io.special[ECHO]:
            raise BridgeError('unknown echo owner')
        self.echo_owned = True
        self.io.word(ECHO, address)

    def publish(self):
        for function in (DCACHE, ICACHE):
            self.echo(function)
            self.io.shell('echo')
        self.echo(ORIGINAL)

    def claim(self, nonce):
        prefix = f'afhook.{nonce:08x}'
        self.helper, self.param, self.veneer = user_alloc.claim(
            self.io, self.emit,
            [(prefix+'.helper', 1536), (prefix+'.param', 128), (prefix+'.veneer', 8)],
            retained=self.retained)
        self.io.special[ECHO].add(self.helper)

    def cleanup(self):
        if self.io.transport_faulted:
            return dict(complete=False, reason='transport uncertain; no new cleanup exchanges',
                        resources_retained=self.retained, reclamation_proven=False)
        if self.hook_touched:
            value = self.io.read(fmt.CALLSITE)[0]
            if value not in (fmt.ORIGINAL_WORD,self.branch):
                raise BridgeError('unknown AF hook owner; not overwritten')
            self.io.word(fmt.CALLSITE,fmt.ORIGINAL_WORD)
            self.publish()
        if self.echo_owned:
            self.echo(ORIGINAL)
        restored = self.io.read(fmt.CALLSITE)[0] == fmt.ORIGINAL_WORD
        echo_restored = self.io.read(ECHO)[0] == ORIGINAL
        return dict(complete=restored and echo_restored, callsite_restored=restored,
                    echo_restored=echo_restored, resources_retained=self.retained,
                    reclamation_proven=False,
                    retention_reason='suspended hook / DMA lifetime not reclaimed',
                    warm_reboot_recovery_verified=False)


def run(io, emit, output, *, capacity=64, nonce, wait_seconds=10.0, vbin=None,
        level=fmt.LEVEL_COUNT, baseline=cine.collect, sleep=time.sleep,
        clock=time.monotonic):
    if type(capacity) is not int or not 1 <= capacity <= 256:
        raise ValueError('capacity must be 1..256')
    if not 0 < nonce <= 0xffffffff or not 0.1 <= wait_seconds <= 30:
        raise ValueError('invalid nonce/deadline')
    if level not in (fmt.LEVEL_COUNT, fmt.LEVEL_RECORD):
        raise ValueError('level must be 1 (count) or 3 (record)')
    rom, asm, worker_body = offline_sources()
    probe = Probe(io,emit)
    result = dict(schema='fp.af-hook-trial/v1',status='preparing',transport='EP82-raw-bulk',
                  ep83_delivery=False,nonce=nonce,capacity=capacity,
                  optical_alignment_verified=False,geometry_eligible=False,
                  recording_test=False,lens_commands=0,settings_writes=0,
                  shutdown_restore_verified=False,installation_performed=False,
                  level=level,data_path_polled=False)
    try:
        before = baseline(io,emit,samples=1)
        if not before.get('cine_baseline_verified'):
            raise BridgeError('CINE standby baseline required')
        result['baseline_before'] = before
        if io.read(ECHO)[0] != ORIGINAL:
            raise BridgeError('echo is borrowed')
        for at,size in ROM_GUARDS:
            expected=rom[at-0xc0000000:at-0xc0000000+size]
            if struct.pack('<%dI'%(size//4),*io.read(at,size//4)) != expected:
                raise BridgeError(f'ROM guard mismatch {at:08X}')
        boot=io.read(BOOT_STAMP)[0]
        pool,size,worker=io.read(WORKER,3)
        if not boot or size != 0x100000 or not 0x40000000 <= pool < 0x80000000-size or not 0x40000000 <= worker < 0x80000000-len(worker_body):
            raise BridgeError('current worker allocation identity rejected')
        actual=struct.pack('<%dI'%(len(worker_body)//4),*io.read(worker,len(worker_body)//4))
        if actual != worker_body:
            raise BridgeError('running worker body differs from reviewed CAP_PTR implementation')
        result['worker_body_sha256']=digest(actual)
        result['boot_stamp']=boot
        # Read-only, before the first write: the shared loader must already be
        # carrying this site in its journal, which means the card declared it.
        # Nothing is installed if it is not there.
        result['shutdown_restore']=verify_shutdown_restore(io,vbin=vbin)
        probe.claim(nonce)
        armed=build.branch_word(probe.veneer)
        result['installation_performed']=True
        state,raw,base=user_alloc.allocate(io,emit,
            helper_image=asm.assemble(HELPER,[f'AF_PROBE_P={probe.param}']),
            helper_at=probe.helper,param_at=probe.param,
            echo=lambda at: probe.echo(ORIGINAL if at is None else at),
            publish=probe.publish,
            exclude=((pool,size),(worker,len(worker_body))),
            retained=probe.retained,
            record=lambda words: result.update(allocation_receipt=words))
        result['allocation']=dict(raw=raw,base=base,bytes=ALLOC_BYTES,mapping_verified=True)
        code,initial,manifest=build.assemble(code_base=base,state_base=base+STATE_OFF,
             records_base=base+RECORDS_OFF,capacity=capacity,nonce=nonce,
             level=level,veneer_base=probe.veneer)
        probe.branch=manifest['candidate_branch_word']
        if probe.branch!=armed:
            raise BridgeError('armed word differs from the registered restore entry')
        io.special[fmt.CALLSITE].add(probe.branch)
        io.put(base,code)
        # Records need no initialization: each record is fully written before
        # commit. Only the header is initialized while the hook is absent.
        io.put(base+STATE_OFF,initial[:64])
        io.put(probe.veneer,bytes.fromhex(manifest['veneer_hex']))
        io.word(probe.param+0x18,nonce)
        io.word(probe.param+0x1c,capacity)
        probe.publish()
        if io.read(BOOT_STAMP)[0]!=boot or io.read(fmt.CALLSITE)[0]!=fmt.ORIGINAL_WORD:
            raise BridgeError('boot or hook owner changed before arm')
        # Read it again: the journal must still hold the stock word at the moment
        # the site is armed, not only when the run started. Only this second
        # verdict sets the flag.
        result['shutdown_restore_at_arm']=verify_shutdown_restore(io,vbin=vbin)
        result['shutdown_restore_verified']=True
        if io.read(0xC31C01B0)[0]!=1 or io.read(0xC31F86E0)[0]!=1:
            raise BridgeError('CINE mode changed before arm')
        if io.read(0xC30338C8)[0] or io.read(0xC30338D0)[0]&255 or io.read(0xC3033A6C)[0]:
            raise BridgeError('capture/shutter state changed before arm')
        probe.hook_touched=True  # Intent recorded before the write.
        emit(dict(event='hook_arm_intent',site=fmt.CALLSITE,original=fmt.ORIGINAL_WORD,
                  branch=probe.branch,manifest=manifest,retained=probe.retained))
        io.word(fmt.CALLSITE,probe.branch)
        probe.publish()
        # The observation window: one sleep, no exchanges. Nothing is read back
        # while the producer is writing, so the host cannot mistake a mid-body
        # header for a result and cannot contend with the hook on the bus.
        started=clock()
        emit(dict(event='observation_window_open',seconds=wait_seconds,level=level))
        sleep(wait_seconds)
        elapsed=clock()-started
        result['observation_window_s']=elapsed
        emit(dict(event='observation_window_closed',elapsed_s=elapsed))
        # Restore entry and publish it before export. Retain every resource,
        # including veneer: this is not a suspended-task quiescence proof.
        io.word(fmt.CALLSITE,fmt.ORIGINAL_WORD)
        probe.publish()
        for address,expected in ((0xC31C01B0,1),(0xC31F86E0,1)):
            if io.read(address)[0]!=expected:
                raise BridgeError('CINE mode changed during the standby trial')
        if io.read(0xC30338C8)[0] or io.read(0xC30338D0)[0]&255 or io.read(0xC3033A6C)[0]:
            raise BridgeError('capture/shutter state changed during the standby trial')
        io.word(probe.param,1)
        probe.echo(probe.helper)
        capture,bulk_elapsed=io.bulk(64+capacity*128)
        (output/'capture.afh').write_bytes(capture)
        decoded=fmt.decode_capture(capture,expected_nonce=nonce)
        probe.echo(ORIGINAL)
        export_state=io.read(probe.param,16)
        if export_state[1]!=0 or export_state[8:10]!=[base+STATE_OFF,len(capture)]:
            raise BridgeError('export receipt mismatch')
        result.update(status='captured',count=decoded['count'],bulk_elapsed_s=bulk_elapsed,
                      capture_sha256=digest(capture),capture_bytes=len(capture),decoded=decoded,
                      hits=decoded['hits'],overlaps=decoded['overlaps'],
                      in_body_after_restore=decoded['in_body'],
                      serialization_verified=decoded['serialization_verified'])
        if decoded['overlaps']:
            # The producer was re-entered: the bytes are kept, the ordering and
            # rate they imply are not usable.
            raise BridgeError(f"producer re-entered {decoded['overlaps']} time(s); "
                              'sequence and rate void, raw bytes retained')
        if decoded['in_body']:
            raise BridgeError('a producer body was still marked after the site was '
                              'restored; no quiescence claim')
        if level==fmt.LEVEL_RECORD and not decoded['count']:
            raise BridgeError('no record was committed in the observation window')
        if level==fmt.LEVEL_COUNT and not decoded['hits']:
            raise BridgeError('the producer did not run in the observation window')
    except BaseException as exc:
        result.update(status='failed',error=repr(exc))
    finally:
        try:
            result['cleanup']=probe.cleanup()
        except BaseException as exc:
            result['cleanup']=dict(complete=False,error=repr(exc),resources_retained=probe.retained,
                                   reclamation_proven=False)
        if result['cleanup'].get('complete') and not io.transport_faulted and 'baseline_before' in result:
            try:
                after=baseline(io,emit,samples=1)
                result['baseline_after']=after
                result['settings_equal']=after.get('settings')==result['baseline_before'].get('settings')
                if not after.get('cine_baseline_verified') or not result['settings_equal']:
                    result['status']='failed'
                    result['postcheck_error']='CINE/settings postcheck rejected'
            except BaseException as exc:
                result.update(status='failed',postcheck_error=repr(exc))
        result['transport_faulted']=io.transport_faulted
        if io.transport_faulted or not result['cleanup'].get('complete'):
            result['status']='failed'
        (output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--inspect',action='store_true')
    mode.add_argument('--run-live-hook',action='store_true')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--capacity',type=int,default=64,choices=range(1,257))
    # The ladder is not machine-enforced across runs: `record` should only follow
    # a `count` run that showed the producer running with overlaps=0.
    parser.add_argument('--level',default='count',choices=('count','record'))
    parser.add_argument('--window-seconds',type=float,default=10.0)
    # A local copy of the card's \\fpSup.BIN, only to state what the loader's
    # journal covers. Absent, the verdict records that it was not checked; it is
    # never a substitute for the manager lists read from the camera.
    parser.add_argument('--card-bin',type=Path)
    args=parser.parse_args(argv)
    args.output.mkdir(parents=True,exist_ok=False)
    rom,asm,worker=offline_sources()
    hashes={str(p.relative_to(ROOT)):digest(p.read_bytes()) for p in
            (Path(__file__),HELPER,build.SOURCE,Path(sites.__file__),
             Path(restore.__file__),SHELL/'camera/worker.S',SHELL/'cave.py')}
    (args.output/'sources.json').write_text(json.dumps(hashes,indent=2)+'\n')
    if args.inspect:
        helper=asm.assemble(HELPER,['AF_PROBE_P=0xC0801000'])
        result=dict(offline_only=True,helper_bytes=len(helper),worker_body_bytes=len(worker),
                    rom_sha256=digest(rom),ep83_delivery=False,
                    cave_claim_bytes=1536+128+8,
                    poff_manager=restore.MANAGER,list_slots=restore.LIST_SLOTS,
                    # Offline: nothing is verified here.
                    shutdown_restore_verified=False,
                    live_ready=True,live_gate=SHUTDOWN_BLOCKER,
                    shutdown_restore_mechanism='shared loader journal; this trial '
                        'registers nothing and spends no power-off list slot',
                    card_section='python3 highrate/hook_site_section.py --output DIR '
                                 'emits the four-byte section and its build argument',
                    live_requires=['the card declares 0x%08X as a four-byte section '
                                   'holding 0x%08X' % (fmt.CALLSITE,fmt.ORIGINAL_WORD),
                                   'the loader journal, found through both lists, '
                                   'holds that stock word',
                                   're-read and still holding it immediately before '
                                   'the site is armed'],
                    echo_restore='host only; not journalled, and it points at cave '
                        'code that survives a warm restart',
                    quiescence_proven=False,warm_boot_verified=False,
                    schema=fmt.SCHEMA,levels=dict(count=fmt.LEVEL_COUNT,
                                                  record=fmt.LEVEL_RECORD),
                    default_level='count',data_path_polled=False,
                    reentrancy_detection='in_body mark plus a latched overlaps '
                        'word; plain load/store, not a mutual-exclusion proof')
        (args.output/'inspect.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result))
        return 0
    with (args.output/'events.jsonl').open('x') as events,open(LOCK,'a+') as lock:
        fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        def emit(row):
            events.write(json.dumps(dict(at=dt.datetime.now().astimezone().isoformat(),**row))+'\n')
            events.flush()
            if row.get('event') in ('cave_claim','allocation_intent','hook_arm_intent'):
                os.fsync(events.fileno())
        result=run(TrialIO(event=emit),emit,args.output,capacity=args.capacity,
                   vbin=args.card_bin.read_bytes() if args.card_bin else None,
                   level=fmt.LEVEL_RECORD if args.level=='record' else fmt.LEVEL_COUNT,
                   wait_seconds=args.window_seconds,
                   nonce=secrets.randbelow(0xffffffff)+1)
    print(json.dumps({k:result[k] for k in ('status','transport','ep83_delivery','transport_faulted')}))
    return 0 if result['status']=='captured' else 1


if __name__=='__main__':
    raise SystemExit(main())
