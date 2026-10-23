"""Explicit one-file deployment with backup, complete readback and idle checks."""
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SHELL = ROOT / 'fpSup/fp_usb_shell'
sys.path.insert(0, str(SHELL))
import putfile as pf


def main():
    report_path = HERE / 'deployment.json'
    assert not report_path.exists(), 'never overwrite/replay a deployment'
    report = {'time': time.time(), 'commands': [], 'only_replaced': r'\fpSup\10LOSS.BIN'}

    def save(): report_path.write_text(json.dumps(report, indent=2) + '\n')
    def sh(command):
        reply = pf.sh(command, retries=0, timeout_ms=5000)
        report['commands'].append({'command': command, 'reply': reply, 'time': time.time()})
        save()
        assert reply.strip() and not reply.startswith('ERR'), reply
        return reply.strip()
    def idle():
        assert sh('status get is_recording') == 'is_recording -> 0'
        assert pf.mem_get(0xC358E140)[0] == 0
        assert pf.mem_get(0xC35A952C)[0] & 255 == 0
    def run(tool, args, label):
        result = subprocess.run([sys.executable, '-B', str(tool), *args], capture_output=True, text=True)
        (HERE / (label + '.log')).write_text(result.stdout + result.stderr)
        assert result.returncode == 0, 'STOP: uncertain transfer; preserve camera parameters and ' + label + '.log'
    def sizes():
        lines = sh('dir ' + chr(92) + 'fpSup').splitlines()
        return {p[-1]: int(p[-2]) for line in lines if len(p := line.split()) >= 4 and p[-2].isdigit()}

    with open('/tmp/fp-af-fusion.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            idle()
            candidate = HERE / 'expanded/10LOSS.BIN'
            build = json.loads(candidate.with_name('build.json').read_text())
            assert hashlib.sha256(candidate.read_bytes()).hexdigest() == build['sha256']
            old_size = sizes()['10LOSS.BIN']
            # Reviewed putfile.main stages and verifies first, then replace_if_shorter
            # deletes only this payload and confirms absence before the exact write.
            backup = HERE / 'before-10LOSS.BIN'
            run(HERE / 'read_file_once.py', [r'\fpSup\10LOSS.BIN', str(backup), '--size', str(old_size)], 'backup')
            report['backup_sha256'] = hashlib.sha256(backup.read_bytes()).hexdigest()
            report['backup_bytes'] = old_size
            stopfx_size = sizes()['05STOPFX.BIN']
            run(HERE / 'read_file_once.py', [r'\fpSup\05STOPFX.BIN', str(HERE / 'before-05STOPFX.BIN'), '--size', str(stopfx_size)], 'backup-stopfx')
            report['stopfx_sha256'] = hashlib.sha256((HERE / 'before-05STOPFX.BIN').read_bytes()).hexdigest()
            idle()
            run(SHELL / 'putfile.py', [str(candidate), r'\fpSup\10LOSS.BIN'], 'write')
            back = HERE / 'readback-10LOSS.BIN'
            run(HERE / 'read_file_once.py', [r'\fpSup\10LOSS.BIN', str(back), '--size', str(candidate.stat().st_size)], 'readback')
            assert back.read_bytes() == candidate.read_bytes()
            assert sizes()['10LOSS.BIN'] == candidate.stat().st_size
            idle()
            report.update(readback_verified=True, sha256=build['sha256'], bytes=candidate.stat().st_size,
                          boot_before=pf.mem_get(0xC072F6F8)[0], completed_at=time.time())
            save()
            print(json.dumps({k: v for k, v in report.items() if k != 'commands'}))
        except BaseException as exc:
            report['error'] = repr(exc)
            save()
            raise


if __name__ == '__main__': main()
