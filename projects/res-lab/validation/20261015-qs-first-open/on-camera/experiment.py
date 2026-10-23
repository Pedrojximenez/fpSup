"""Bounded QS A/B trial: preserve the current card, exact writes, single toggles."""
import argparse
import fcntl
import hashlib
import importlib
import json
from pathlib import Path
import socket
import struct
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path.insert(0, str(ROOT / 'projects/res-lab/validation/20261009-oncamera'))
sys.path.insert(0, str(ROOT / 'projects/res-lab/validation/20261012-m12-240-live'))
sys.path.insert(0, str(HERE.parent / 'legacy-fps-root/projects/open-gate/build/res-custom'))
import live_camera as live
import backup as B
import ogc_layout as L
from armasm import assemble
import cave

pf = live.putfile
live.LOG = HERE / 'commands.jsonl'
B.live = live
OWNER = HERE / 'daemon-owner.json'


def daemon():
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
        conn.settimeout(5)
        conn.connect(pf.SOCK)
        pid = struct.unpack('i', conn.getsockopt(0, 2, 4))[0]
        conn.sendall(b'STATUS\n')
        status = conn.recv(4096).decode()
    expected = json.loads(OWNER.read_text())['pid'] if OWNER.exists() else 82146
    assert pid == expected, (pid, expected)
    text = subprocess.check_output(['lsof', '-a', '-p', str(pid), '-d', 'txt', '-Fn'], text=True)
    assert 'n' + str(live.SHELL / 'fpshd') in text.splitlines(), text
    assert 'quarantine=0 fault=none' in status, status
    return pid, status


def fetch(remote, filename, size):
    return B.fetch(remote, HERE / filename, size)


def deploy(variant):
    B.idle()
    assert json.loads((HERE / 'backup/manifest.json').read_text())['phase'] == 'complete'
    assert (HERE / 'pair-verification.json').exists()
    folder = HERE / variant
    meta = json.loads((folder / 'build.json').read_text())['files']
    target = '\\fpSup\\32RESCUS.BIN'
    oldsize = pf.remote_file_size(target)
    new = (folder / '32RESCUS.BIN').read_bytes()
    assert hashlib.sha256(new).hexdigest() == meta['32RESCUS.BIN']['sha256']
    proof = {'variant': variant, 'phase': 'preflight', 'existing_size': oldsize,
             'written': {}, 'daemon': daemon()}
    report = HERE / ('deployment-' + variant + '.json')
    assert not report.exists(), report
    save = lambda: report.write_text(json.dumps(proof, indent=2) + '\n')
    if variant == 'baseline':
        assert oldsize is None, 'baseline addition must start without RES-Custom'
        listing = live.checked_sh('dir \\fpSup')
        assert 'RESCUS' not in listing
        live.checked_sh('mkdir \\fpSup\\RESCUS')
        assert 'RESCUS' in live.checked_sh('dir \\fpSup')
    else:
        assert oldsize is not None
        old = fetch(target, 'before-' + variant + '-32RESCUS.BIN', oldsize)
        previous = {'combined': 'optimized', 'combined-fix1': 'combined',
                    'combined-fix2': 'combined-fix1',
                    'combined-fix3': 'combined-fix2',
                    'combined-fix4': 'combined-fix3',
                    'combined-fix5': 'combined-fix4',
                    'combined-fix6': 'combined-fix5',
                    'combined-fix7': 'combined-fix6',
                    'combined-fix8': 'combined-fix7',
                    'combined-fix9': 'combined-fix8',
                    'combined-fix10': 'combined-fix9',
                    'combined-fix11': 'combined-fix10',
                    'combined-fix12': 'combined-fix11'}.get(variant, 'baseline')
        if variant.startswith('combined'):
            assert (HERE / (variant + '-verification.json')).exists()
        expected = (HERE / ('prepared-' + previous + '-32RESCUS.BIN')).read_bytes()
        assert old[:32] == expected[:32] and old[128:] == expected[128:]
        new = new[:32] + old[32:128] + new[128:]
        proof['preserved_cfg_sha256'] = hashlib.sha256(old[32:128]).hexdigest()
    prepared = HERE / ('prepared-' + variant + '-32RESCUS.BIN')
    prepared.write_bytes(new)
    sources = {target: prepared}
    if variant == 'baseline':
        sources.update({'\\fpSup\\' + n.replace('/', '\\'): folder / n
                        for n in meta if n.startswith('RESCUS/')})
    save()
    for remote, source in sources.items():
        B.idle()
        proof['phase'] = 'writing ' + remote
        save()
        sys.argv = ['putfile.py', str(source), remote]
        assert pf.main() == 0
        got = fetch(remote, 'installed-' + variant + '-' + source.name, source.stat().st_size)
        assert got == source.read_bytes()
        proof['written'][remote] = {'bytes': len(got), 'sha256': hashlib.sha256(got).hexdigest()}
        save()
    proof['phase'] = 'verified'
    save()
    print(json.dumps(proof, indent=2), flush=True)


def reboot():
    pid, status = daemon()
    B.idle()
    # One request only: disconnect is uncertain and never causes a replay.
    try:
        print('Single reboot request:', repr(live.checked_sh('reboot')), flush=True)
    except RuntimeError as exc:
        print(str(exc), flush=True)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
        conn.settimeout(5)
        conn.connect(pf.SOCK)
        assert struct.unpack('i', conn.getsockopt(0, 2, 4))[0] == pid
        conn.sendall(b'QUIT\n')
        assert conn.recv(1024).decode().strip() == 'OK bye'
    print('Waiting for the camera boot; other daemons preserved.', flush=True)
    time.sleep(25)
    with (HERE / 'daemon.log').open('ab') as log:
        process = subprocess.Popen([str(live.SHELL / 'fpshd')], cwd=live.SHELL,
                                   stdout=log, stderr=log, start_new_session=True)
    OWNER.write_text(json.dumps({'pid': process.pid, 'previous_pid': pid,
                                 'previous_status': status}, indent=2) + '\n')
    time.sleep(2)
    assert process.poll() is None
    print('Reconnected:', daemon(), flush=True)
    B.idle()


def core_state(variant):
    meta = json.loads((HERE / variant / 'build.json').read_text())['files']['32RESCUS.BIN']['facts']
    site = 0xC043CCF8
    word = pf.mem_get(site, tries=1)[0]
    assert word & 0xff000000 == 0xea000000, hex(word)
    displacement = word & 0xffffff
    if displacement & 0x800000:
        displacement -= 0x1000000
    veneer = site + 8 + 4 * displacement
    assert cave.CAVE_ARENA <= veneer < cave.CAVE_ARENA_END
    words = pf.mem_get(veneer, 2, tries=1)
    assert words[0] == 0xe51ff004, words
    state = words[1] - (L.LAYOUT0 + meta['shims']['picker']) + L.S_COORD
    base = state - (meta['img_off'] + L.S_COORD - L.LAYOUT0)
    expected = (HERE / ('prepared-' + variant + '-32RESCUS.BIN')).read_bytes()
    assert struct.pack('<8I', *pf.mem_get(base, 8, tries=1)) == expected[:32]
    end = 128 + meta['text']
    assert pf.read_bulk(base + 128, end - 128, 'core') == expected[128:end]
    nrows = pf.mem_get(state + L.S['NROWS'], tries=1)[0]
    assert nrows == 5, nrows
    return state, {'base': hex(base), 'state': hex(state), 'nrows': nrows,
                   'immutable_code_sha256': hashlib.sha256(expected[128:end]).hexdigest()}


def publish_rom_caches():
    for function in (0xC000E91C, 0xC000EABC):
        assert pf.mem_get(pf.ECHO_SLOT, tries=1) == [pf.ECHO_ORIG]
        try:
            pf.set_echo_handler(function)
            reply = live.checked_sh('echo', timeout_ms=2000)
            assert not reply.strip(), repr(reply)
        finally:
            owner = pf.mem_get(pf.ECHO_SLOT, tries=1)[0]
            assert owner in (pf.ECHO_ORIG, function), hex(owner)
            pf.set_echo_handler(pf.ECHO_ORIG)


def measure(variant, resume=False):
    B.idle()
    state, identity = core_state(variant)
    before = {k: pf.mem_get(state + L.S[k], tries=1)[0]
              for k in ('QS_BOOT', 'QS_RELOADS', 'QS_HITS', 'QS_N', 'QS_READY')}
    code_at = cave.claim('qs.firstopen.screen', 320)
    parm = pf.P
    code = assemble(HERE / 'screen_snapshot.S', [f'P={parm}'])
    assert len(code) <= 320
    pf.put(code_at, code, 'screen')
    publish_rom_caches()
    assert pf.mem_get(pf.ECHO_SLOT, tries=1) == [pf.ECHO_ORIG]
    record = {'variant': variant, 'identity': identity, 'before': before,
              'endpoint': 'active_screen_name', 'LCD_scanout_measured': False,
              'poll_interval_seconds': 0.075, 'opens': []}
    report = HERE / ('timing-' + variant + '.json')
    if resume:
        saved = json.loads(report.read_text())
        assert saved['identity'] == identity and len(saved['opens']) == 1
        assert 'after' not in saved
        record = saved
        record['resume_reason'] = 'QSOFF acknowledged without changing QS screen; use QSON for next press'
    else:
        assert not report.exists(), report
    save = lambda: report.write_text(json.dumps(record, indent=2) + '\n')
    def screen():
        live.checked_sh('echo', timeout_ms=2000)
        values = pf.mem_get(parm + 0x40, 12, tries=1)
        assert len(values) == 12 and None not in values
        assert values[3] == 1, values
        name = struct.pack('<8I', *values[4:]).split(b'\0')[0].decode('ascii')
        assert name and len(name) < 32
        return name
    def transition(key, prefix):
        start = time.monotonic()
        live.checked_sh('key ' + key, timeout_ms=30000)
        acknowledged = time.monotonic() - start
        last_non_target = 0.0
        samples = []
        while time.monotonic() - start < 30:
            observed = screen()
            elapsed = time.monotonic() - start
            samples.append([elapsed, observed])
            if observed.startswith(prefix):
                # This card's QSOFF was verified to release without closing QS.
                # Complete each press, then verify release did not toggle.
                live.checked_sh('key QSOFF', timeout_ms=30000)
                released = screen()
                assert released.startswith(prefix), ('release changed screen', released)
                return {'key': key, 'ack_seconds': acknowledged,
                        'observed_seconds': elapsed, 'last_non_target_seconds': last_non_target,
                        'screen': observed, 'samples': samples, 'release_screen': released}
            last_non_target = elapsed
            time.sleep(0.075)
        raise RuntimeError('Screen transition not observed; key is not replayed')
    try:
        pf.set_echo_handler(code_at)
        initial = screen()
        assert initial.startswith('QS_CINE' if resume else 'LV_CINE'), initial
        if resume:
            record['opens'][0]['close'] = transition('QSON', 'LV_CINE')
        else:
            record['initial_screen'] = initial
        save()
        for index in range(1 if resume else 0, 2):
            opened = transition('QSON', 'QS_CINE')
            opened['index'] = index + 1
            record['opens'].append(opened)
            save()
            print(variant, 'QS open', index + 1, opened['observed_seconds'], flush=True)
            time.sleep(1)
            closed = transition('QSON', 'LV_CINE')
            opened['close'] = closed
            save()
            time.sleep(1)
        record['final_screen'] = screen()
    finally:
        owner = pf.mem_get(pf.ECHO_SLOT, tries=1)[0]
        assert owner in (pf.ECHO_ORIG, code_at), hex(owner)
        pf.set_echo_handler(pf.ECHO_ORIG)
        assert pf.mem_get(pf.ECHO_SLOT, tries=1) == [pf.ECHO_ORIG]
    record['after'] = {k: pf.mem_get(state + L.S[k], tries=1)[0] for k in before}
    B.idle()
    record['echo_restored'] = True
    save()
    print(json.dumps(record, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('deploy', 'reboot', 'measure'))
    parser.add_argument('variant', nargs='?', choices=('baseline', 'optimized', 'combined', 'combined-fix1', 'combined-fix2', 'combined-fix3', 'combined-fix4', 'combined-fix5', 'combined-fix6', 'combined-fix7', 'combined-fix8', 'combined-fix9', 'combined-fix10', 'combined-fix11', 'combined-fix12'))
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    with open('/tmp/fp-af-fusion.lock', 'r') as lease:
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        daemon()
        if args.action == 'reboot':
            assert args.variant is None
            assert not args.resume
            reboot()
        else:
            assert args.variant is not None
            if args.action == 'deploy':
                assert not args.resume
                deploy(args.variant)
            else:
                measure(args.variant, resume=args.resume)


if __name__ == '__main__':
    main()
