"""Restricted, exclusive, single-use fp 5.02 RAM call bridge.

No connection or mutation at import. This development version exposes only
audited getters until the separately reviewed movement operations are enabled.
Shell timeout is never a lens-stop acknowledgement.
"""
import contextlib
import fcntl
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import secrets
import socket
import struct
import time

P = 0xC072F700
CODE = 0xC072F800
SNAPSHOT = 0xC072F740
END = 0xC072FA00
ECHO = 0xC0BAC2F8
ORIGINAL = 0xC03D99A0
DCACHE = 0xC000E91C
ICACHE = 0xC000EABC
MAGIC = 0x31424641
LOCK = '/tmp/fp-af-fusion.lock'
SETTINGS = ('menu SetFocusPosition', 'menu SetFocusMode',
            'menu SetFocusArea', 'menu SetFocusAreaSize')
SOURCE = Path(__file__).with_suffix('.S')
SNAPSHOT_SOURCE = Path(__file__).with_name('focus_snapshot.S')


class BridgeError(RuntimeError):
    pass


class GuardRejected(BridgeError):
    """The camera-side wrapper returned without dispatching a lens command."""


def signed(value):
    return value - 0x100000000 if value & 0x80000000 else value


class Transport:
    """One bounded exchange, no automatic re-dispatch of uncertain commands."""
    def __init__(self, path='/tmp/fpshd.sock', event=None, *, spacing_s=0.005):
        if (isinstance(spacing_s, bool) or not isinstance(spacing_s, (int, float))
                or not math.isfinite(spacing_s) or not 0.005 <= spacing_s <= 0.020):
            raise ValueError('transport spacing must be 5..20 ms')
        self.path = path
        self.event = event or (lambda item: None)
        self.spacing_s = spacing_s
        self._last_exchange_end = None

    def request(self, line, timeout=2.0):
        self._wait_for_gap()
        return self._exchange(line, timeout)

    def _wait_for_gap(self):
        if self._last_exchange_end is not None:
            time.sleep(max(0.0, self.spacing_s - (time.monotonic() - self._last_exchange_end)))

    def _exchange(self, line, timeout):
        # Internal primitive only: public request() always applies pacing.
        # The sole unpaced caller is the fixed four-read H/L bracket below.
        started = time.monotonic()
        try:
            with socket.socket(socket.AF_UNIX) as connection:
                connection.settimeout(timeout)
                connection.connect(self.path)
                connection.sendall((line + '\n').encode('ascii'))
                result = bytearray()
                while True:
                    remaining = timeout - (time.monotonic() - started)
                    if remaining <= 0:
                        raise TimeoutError('USB shell outcome uncertain; no retry')
                    connection.settimeout(remaining)
                    block = connection.recv(4096)
                    if not block:
                        break
                    result.extend(block)
                    if len(result) > 16384:
                        raise BridgeError('oversized daemon reply')
        except BaseException as exc:
            self._last_exchange_end = time.monotonic()
            with contextlib.suppress(Exception):
                self.event({'event': 'exchange_uncertain', 'request': line,
                            'error': repr(exc), 'elapsed_s': time.monotonic() - started})
            raise
        self._last_exchange_end = time.monotonic()
        raw = bytes(result)
        self.event({'event': 'exchange', 'request': line, 'reply': raw.decode('ascii', 'replace'),
                    'elapsed_s': time.monotonic() - started})
        return raw

    def shell(self, command, timeout_ms=1000):
        raw = self.request('TMO %d SHL %s' % (timeout_ms, command), timeout_ms / 1000 + 1)
        return self._decode_shell_reply(raw)

    @staticmethod
    def _decode_shell_reply(raw):
        if raw.startswith(b'OKX '):
            try:
                return bytes.fromhex(raw[4:].decode().strip()).decode('latin1')
            except ValueError as exc:
                raise BridgeError('invalid hex reply') from exc
        if not raw.startswith(b'OK '):
            raise BridgeError('shell response not successful: %r' % raw)
        return raw[3:].decode('ascii').replace('\\n', '\n').rstrip('\n')

    def read_h_bracket(self):
        """Four fixed read-only exchanges; no internal pacing or read retries.

        The first exchange and any following ordinary request/burst preserve
        the configured completion-to-start gap.  Only the three gaps *inside*
        this fixed burst are omitted.  No addresses, commands, or counts are
        accepted from callers.  Any failed/invalid reply aborts the burst.
        Matching phases are evidence for the caller, not a seqlock guarantee.
        """
        reads = ((0xC31F8CB4, 2), (0xC32985E8, 1),
                 (0xC32986B4, 1), (0xC31F8CB4, 2))
        self._wait_for_gap()
        started = time.monotonic()
        values = []
        for address, count in reads:
            line = 'TMO 1000 SHL mem get 0x%08X,,0x%X' % (address, count * 4)
            reply = self._decode_shell_reply(self._exchange(line, 2.0))
            lines = reply.splitlines()
            if len(lines) != count:
                raise BridgeError('incomplete/extra H bracket memory response')
            words = []
            for index, item in enumerate(lines):
                match = re.fullmatch(r'\s*get\s*:\s*A:0x([0-9a-fA-F]{1,8}),\s*D:0x([0-9a-fA-F]{1,8})\s*', item)
                if match is None or int(match[1], 16) != address + 4 * index:
                    raise BridgeError('invalid/address-mismatched H bracket memory response')
                words.append(int(match[2], 16))
            values.append(words)
        return {'phase_before': values[0][0], 'mode_before': values[0][1],
                'h': values[1][0], 'l': values[2][0],
                'phase_after': values[3][0], 'mode_after': values[3][1],
                'started_at': started, 'finished_at': time.monotonic()}

    def read(self, address, count=1):
        if type(count) is not int or not 1 <= count <= 192 or address & 3:
            raise ValueError('bounded aligned read required')
        values = []
        for offset in range(0, count, 32):
            take = min(32, count - offset)
            base = address + 4 * offset
            for attempt in range(3):
                try:
                    reply = self.shell('mem get 0x%08X,,0x%X' % (base, take * 4))
                    break
                except (BridgeError, OSError):
                    if attempt == 2:
                        raise
            pairs = re.findall(r'A:0x([0-9a-fA-F]+),\s*D:0x([0-9a-fA-F]+)', reply)
            actual = [(int(a, 16), int(v, 16)) for a, v in pairs]
            if len(actual) != take or [a for a, v in actual] != list(range(base, base + take * 4, 4)):
                raise BridgeError('incomplete/duplicate/address-mismatched memory response')
            values.extend(v for a, v in actual)
        return values

    def ensure(self, address, value):
        if not (P <= address < END or address == ECHO) or address & 3:
            raise ValueError('write outside approved RAM lease')
        if type(value) is not int or not 0 <= value <= 0xffffffff:
            raise ValueError('word required')
        # Only idempotent writes are repaired, and only after a fresh read.
        for attempt in range(3):
            if self.read(address)[0] == value:
                return
            try:
                self.shell('mem set 0x%08X 0x%08X' % (address, value))
            except (BridgeError, OSError):
                # An uncertain idempotent word write is not blindly resent.
                # The next iteration reads first; three failures stop the run.
                pass
        if self.read(address)[0] != value:
            raise BridgeError('RAM readback failed at 0x%08X' % address)


def assemble(shell_dir, *, source=SOURCE, max_bytes=END-CODE):
    module_path = Path(shell_dir) / 'armasm.py'
    spec = importlib.util.spec_from_file_location('fp_assist_armasm', module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    code = module.assemble(source)
    if not code or len(code) & 3 or len(code) > max_bytes:
        raise BridgeError('code exceeds its approved RAM subregion')
    return code


class FocusBridge:
    def __init__(self, transport, code, event=None, *, snapshot_code=None):
        self.io = transport
        self.code = bytes(code)
        self.snapshot_code = bytes(snapshot_code) if snapshot_code is not None else None
        if self.snapshot_code is not None and (not self.snapshot_code or len(self.snapshot_code) & 3
                                              or len(self.snapshot_code) > CODE - SNAPSHOT):
            raise BridgeError('snapshot code exceeds F740..F7FF')
        self.event = event or (lambda item: None)
        self.leased = False
        self.backup = None
        self.baseline = None
        self.motion_enabled = False
        self.quarantined = False
        self.movement_owned = False
        self.motion_origin = None
        self.cleanup_complete = False
        self.control_fault = False
        self.abort_attempted = False

    def emit(self, kind, **details):
        self.event(dict(event=kind, **details))

    def ownership(self, expected):
        actual = self.io.read(ECHO)[0]
        if actual not in expected:
            raise BridgeError('unknown echo owner 0x%08X; not overwritten' % actual)
        return actual

    def settings(self):
        return {command: self.io.shell(command) for command in SETTINGS}

    def known_owners(self):
        return {ORIGINAL, DCACHE, ICACHE, CODE} | ({SNAPSHOT} if self.snapshot_code else set())

    def publish(self):
        # Bootstrap with existing ROM functions, never stale RAM instructions.
        # Native mem set and putfile.put_slow do NOT publish the instruction cache.
        for function in (DCACHE, ICACHE):
            self.ownership(self.known_owners())
            self.io.ensure(ECHO, function)
            try:
                self.io.shell('echo')
            except BaseException:
                self.quarantined = True
                raise
        self.io.ensure(ECHO, ORIGINAL)

    @contextlib.contextmanager
    def lease(self):
        with open(LOCK, 'a+') as lock:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise BridgeError('another AF tool owns the camera lease') from exc
            self.ownership({ORIGINAL})
            version = self.io.shell('version')
            if not all(item in version for item in ('w71c1', '5.02.0.V91', '13aa6210')):
                raise BridgeError('not verified SIGMA fp 5.02 build')
            self.baseline = self.settings()
            self.native_identity()
            self.backup = self.io.read(P, (END - P) // 4)
            self.emit('lease_prepared', version=version, settings=self.baseline,
                      original_words=self.backup,
                      code_sha256=hashlib.sha256(self.code).hexdigest(),
                      snapshot_sha256=(hashlib.sha256(self.snapshot_code).hexdigest()
                                       if self.snapshot_code else None))
            try:
                images = [(CODE, self.code)]
                if self.snapshot_code:
                    images.append((SNAPSHOT, self.snapshot_code))
                for address, blob in images:
                    words = struct.unpack('<%dI' % (len(blob) // 4), blob)
                    for index, word in enumerate(words):
                        self.io.ensure(address + index * 4, word)
                    if self.io.read(address, len(words)) != list(words):
                        raise BridgeError('code verification failed')
                self.publish()
                self.leased = True
                yield self
            finally:
                self.leased = False
                try:
                    self._restore_lease()
                except BaseException as exc:
                    self.quarantined = True
                    with contextlib.suppress(Exception):
                        self.emit('cleanup_failed', cleanup_complete=False, error=repr(exc))
                    raise

    def _restore_lease(self):
        # A fresh reply from the same serialized worker is a quiescence barrier:
        # it cannot dispatch this command until the earlier handler returned.
        # Physical lens completion is separate. Conservatively quarantine an
        # uncertain call anyway; do not erase its diagnostic code/parameters.
        self.ownership(self.known_owners())
        self.io.ensure(ECHO, ORIGINAL)
        if self.quarantined:
            self.emit('lease_quarantined', echo_verified=True, scratch_restored=False,
                      reason='uncertain execution; retain code and parameters for diagnosis')
            raise BridgeError('uncertain execution: echo restored, scratch retained for diagnosis')
        for index, word in enumerate(self.backup):
            self.io.ensure(P + index * 4, word)
        self.publish()
        if self.io.read(P, len(self.backup)) != self.backup:
            raise BridgeError('scratch restoration mismatch')
        self.ownership({ORIGINAL})
        final_settings = self.settings()
        self.emit('lease_restored', scratch_verified=True, echo_verified=True,
                  settings_unchanged=final_settings == self.baseline, settings=final_settings)
        if final_settings != self.baseline:
            raise BridgeError('camera settings changed during lease')
        self.cleanup_complete = True

    def call(self, operation):
        if self.quarantined or not self.leased or type(operation) is not int or not 0 <= operation <= 6:
            raise BridgeError('operation not in audited read-only whitelist')
        return self._dispatch(operation)

    def _dispatch(self, operation, target=0, expected=0):
        if self.quarantined or not self.leased:
            raise BridgeError('bridge unavailable or quarantined')
        if operation == 9 and not self.snapshot_code:
            raise BridgeError('camera snapshot is not installed')
        entry = SNAPSHOT if operation == 9 else CODE
        count = 15 if operation == 9 else 12
        self.ownership({ORIGINAL})
        nonce = secrets.randbelow(0xfffffffe) + 1
        params = [0, nonce, operation, target & 0xffffffff, expected & 0xffffffff,
                  0, 0, 0, 0, 0, 0, 0]
        params.extend([0] * (count-len(params)))
        for index, word in enumerate(params):
            self.io.ensure(P + index * 4, word)
        self.io.ensure(P, MAGIC)
        if self.io.read(P, count) != [MAGIC] + params[1:]:
            raise BridgeError('request parameter verification failed')
        try:
            self.io.ensure(ECHO, entry)
            try:
                # Native move/abort can wait internally. This deadline is NOT a
                # guarantee of physical completion or firmware wait-time units.
                self.io.shell('echo', timeout_ms=10000 if operation in (7, 8) else 1000)
            except BaseException:
                self.quarantined = True
                raise
        finally:
            self.ownership({entry, ORIGINAL})
            self.io.ensure(ECHO, ORIGINAL)
        try:
            result = self.io.read(P, count)
        except BaseException:
            self.quarantined = True
            raise
        allowed_states = (2,) if operation == 9 else (2, 3)
        if result[0] != 0 or result[6] != nonce or result[7] not in allowed_states:
            self.quarantined = True
            raise BridgeError('call did not return with matching completion nonce')
        self.emit('bridge_call_returned', operation=operation, words=result)
        if result[7] == 3:
            raise GuardRejected('camera-side safety guard rejected operation')
        return result[8], result[9:count]

    def read_h_bracket(self):
        """Fixed camera-side copy; timestamps cover the whole paced RPC."""
        started = time.monotonic()
        returned, values = self._dispatch(9)
        if returned != 0 or len(values) != 6:
            self.quarantined = True
            raise BridgeError('invalid native snapshot result')
        return dict(zip(('phase_before', 'mode_before', 'h', 'l', 'phase_after', 'mode_after'), values),
                    started_at=started, finished_at=time.monotonic(),
                    method='camera_fixed_copy', timing_scope='whole_host_rpc')

    def flags(self, operation):
        result, reference = self.call(operation)
        if result != 1:
            raise BridgeError('native event-reference failed')
        return reference[2]

    def native_identity(self):
        if self.io.read(0xC3476408)[0] != 1 or self.io.read(0xC3476414)[0] != 0xC0B8EEEC:
            raise BridgeError('not the verified initialized native-L focus driver')

    def capture_state(self):
        busy = self.io.read(0xC30338C8)[0]
        recording = self.io.read(0xC30338D0)[0] & 0xff
        sequence = self.io.read(0xC3033A6C)[0]
        return {'still_exposing': bool(busy & 0xff),
                'still_saving': bool((busy >> 8) & 0xff),
                'movie_saving': bool((busy >> 16) & 0xff),
                'still_processing': bool((busy >> 24) & 0xff),
                'movie_recording': bool(recording), 'shutter_sequence': sequence,
                'capture_idle': busy == 0 and recording == 0 and sequence == 0}

    def read_state(self):
        self.native_identity()
        ready, _ = self.call(3)
        if ready != 1:
            raise BridgeError('native lens controller not ready')
        position, _ = self.call(0)
        minimum, _ = self.call(1)
        maximum, _ = self.call(2)
        prop, _ = self.call(4)
        result = {'position': signed(position), 'min_position': signed(minimum),
                  'max_position': signed(maximum), 'lens_ready': ready,
                  'property_predicate': prop, 'focus_flags': self.flags(5),
                  'lens_sync_flags': self.flags(6)}
        result['native_done'] = result['focus_flags'] == 3
        result.update(self.capture_state())
        result['af_route'] = self.io.read(0xC32915B0)[0]
        self.emit('lens_state', **result)
        return result

    def submit_validation_move(self, target):
        """LAB ONLY: explicit small-step validation, not the UI control route.

        motion_enabled must be deliberately set by an authorized validation
        runner; default False. No native waitFocusDrive or PTP worker is called.
        """
        if (not self.motion_enabled or self.control_fault or self.movement_owned or
                type(target) is not int):
            raise BridgeError('experimental motion validation not enabled')
        state = self.read_state()
        if (not state['capture_idle'] or not state['native_done'] or
                state['lens_sync_flags'] & 1 == 0 or state['property_predicate'] != 0 or
                state['af_route'] != 14 or self.settings() != self.baseline):
            raise BridgeError('unsupported or changing pre-move state')
        # Re-read cached position after the done flag. Still not optical truth.
        position = signed(self.call(0)[0])
        if position != state['position']:
            raise BridgeError('position changed during preflight')
        origin = position if self.motion_origin is None else self.motion_origin
        if not (state['min_position'] <= target <= state['max_position'] and
                0 < abs(target - position) <= 100 and abs(target - origin) <= 100):
            raise BridgeError('small-step/radius/native-bound guard rejected target')
        self.motion_origin = origin
        self.abort_attempted = False
        self.movement_owned = True  # Uncertain dispatch must not be retried.
        try:
            self._dispatch(7, target, position)
        except GuardRejected:
            self.movement_owned = False
            self.control_fault = True
            raise
        except BaseException:
            self.control_fault = True
            raise
        return {'submitted_target': target, 'from': position, 'completion_confirmed': False}

    def request_validation_stop(self):
        if not self.motion_enabled or not self.movement_owned:
            raise BridgeError('no owned experimental movement to stop')
        if self.abort_attempted:
            raise BridgeError('abort already attempted; only completion polling is permitted')
        self.native_identity()
        self.abort_attempted = True  # Latch BEFORE an uncertain dispatch.
        returned, _ = self._dispatch(8)
        return {'abort_wrapper_returned': True, 'native_return': returned,
                'native_abort_accepted': returned == 1,
                'physical_stop_confirmed': False}

    def confirm_done(self, expected=None, timeout=2.0, cancel=None):
        """Deadline-checked host polling, not a native call-duration bound.

        A synchronous operation cannot be preempted here, but a late return is
        rejected before another operation or any completion claim. The timeout
        must be finite and positive; no new arbitrary upper limit is imposed.
        """
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
            raise BridgeError('completion timeout must be finite and positive')
        try:
            duration = float(timeout)
        except (OverflowError, ValueError) as exc:
            raise BridgeError('completion timeout must be finite and positive') from exc
        if not math.isfinite(duration) or duration <= 0:
            raise BridgeError('completion timeout must be finite and positive')
        deadline = time.monotonic() + duration
        if not math.isfinite(deadline):
            raise BridgeError('completion timeout exceeds representable host deadline')

        def remaining():
            budget = deadline - time.monotonic()
            if budget <= 0:
                self.control_fault = True
                raise BridgeError('native completion not observed before host deadline; no further move')
            return budget

        def invoke(function, *args):
            remaining()
            try:
                result = function(*args)
            except BaseException:
                # Preserve the original operation error, while still latching
                # a deadline exceeded by that failed synchronous operation.
                if time.monotonic() >= deadline:
                    self.control_fault = True
                raise
            remaining()
            return result

        def pause(duration):
            # Never begin an unbounded sleep or a further read once expired.
            time.sleep(min(duration, remaining()))
            remaining()

        states = []
        stop_requested = False
        while True:
            remaining()
            cancelled = invoke(cancel) if cancel is not None else False
            if cancelled and not stop_requested and self.movement_owned:
                if not self.abort_attempted:
                    invoke(self.request_validation_stop)
                stop_requested = True
                expected = None
            flags = invoke(self.flags, 5)
            position = signed(invoke(self.call, 0)[0])
            states.append({'flags': flags, 'position': position})
            if flags == 3:
                pause(0.03)
                flags2 = invoke(self.flags, 5)
                position2 = signed(invoke(self.call, 0)[0])
                if flags2 == 3 and position2 == position:
                    remaining()
                    if expected is not None and position != expected:
                        self.control_fault = True
                        raise BridgeError('completed cached position does not match target')
                    self.movement_owned = False
                    self.emit('native_completion_observed', position=position, polls=states)
                    return {'native_done': True, 'position': position,
                            'optical_focus_verified': False, 'polls': states,
                            'cancel_stop_requested': stop_requested}
            pause(0.01)
