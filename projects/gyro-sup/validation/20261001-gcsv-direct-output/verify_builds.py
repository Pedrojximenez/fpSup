#!/usr/bin/env python3
"""Reproduce this offline before/after audit using the existing product builder.

No product packaging logic is duplicated here.  The isolated before source is
never copied over the shared checkout, and existing build outputs are refused.
"""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
GYRO = ROOT / 'fpSup' / 'gyro'
SHELL = ROOT / 'fpSup' / 'fp_usb_shell'
OUT = HERE / 'builds'
VERSION = 'direct-test-20261001'
BANNER = 'fpSup-Gyro-direct!'
FLAVORS = {
    'plain': [],
    'debug': ['--debug'],
    'fast': ['--store-boot', '--loader-hook', '--four-box-bar'],
}

INSPECT = r'''
import hashlib, json, pathlib, re, struct, sys
src, phase, out, baseline = map(pathlib.Path, sys.argv[1:])
sys.path[:0] = [str(src), str(src.parent / 'fp_usb_shell')]
import build_base_card as B
import release_card as R
from armasm import assemble, symbols

def sha(data):
    return hashlib.sha256(data).hexdigest()

result = {'phase': str(phase), 'editions': {}, 'builds': []}
for edition in ('gcsv', 'base'):
    name, defines = B.EDITIONS[edition]
    raw = assemble(src / name, defines)
    syms = symbols(src / name, defines)
    expected, writer_len = B.launch(edition)
    secs = B.sections(edition) + B.hook_sites()
    B.check(secs)
    info = {'raw_blob_bytes': len(raw), 'raw_blob_sha256': sha(raw),
            'launcher_bytes': len(expected), 'writer_bytes': writer_len,
            'symbols': syms, 'product_section_guard': 'passed'}
    if str(phase) == 'before':
        saved = (baseline / (edition + '.bin')).read_bytes()
        assert raw == saved, (edition, 'snapshot baseline mismatch')
        info['snapshot_assembled_blob_match'] = True
    result['editions'][edition] = info
    for flavor in ('plain', 'debug', 'fast'):
        folder = out / f'{phase}-{edition}-{flavor}'
        if not folder.exists():
            continue
        data = (folder / 'fpSup.BIN').read_bytes()
        magic, n, entry, body_size = struct.unpack_from('<4sIII', data)
        assert magic == b'VBIN' and n > 0
        offset = 16 + 8 * n
        sections = []
        for i in range(n):
            address, size = struct.unpack_from('<II', data, 16 + 8*i)
            assert size % 4 == 0
            assert offset + size <= len(data)
            sections.append((address, offset, size, data[offset:offset+size]))
            offset += size
        assert offset == 16 + 8*n + body_size
        assert data[offset:] == b'\0' * (len(data) - offset)
        for address, blob, reason in secs:
            assert any(a == address and p == blob for a, o, z, p in sections), reason
        launchers = [(a, o, z, p) for a, o, z, p in sections if a == 0 and p == expected]
        assert len(launchers) == 1
        launch_offset = launchers[0][1]
        boot_size = len(expected) - writer_len
        table = struct.unpack_from('<' + 'I' * len(B.R.GSUP_ROUTINES), expected, boot_size)
        routine_table = dict(zip(B.R.GSUP_ROUTINES, table))
        required = R.BLOB_ROUTINES + R.EDITION_ROUTINES[edition]
        for routine in required:
            assert 0 < routine_table[routine] < writer_len, routine
            assert routine_table[routine] == syms[routine], routine
        if flavor == 'debug':
            template = src.parent / 'fp_usb_shell' / 'templates' / 'entries.S'
            table_at = entry + symbols(template)['table']
            trampoline = assemble(template)
            assert data[entry:table_at] == trampoline[:symbols(template)['table']]
            own, shell_entry, gyro_entry, terminator = struct.unpack_from('<4I', data, table_at)
            assert own == table_at and gyro_entry == launch_offset and terminator == 0
            assert any(a == 0 and o <= shell_entry < o + z for a, o, z, p in sections)
            entries = [shell_entry, gyro_entry]
        else:
            assert entry == launch_offset
            entries = [entry]
        fixed = [a for a, o, z, p in sections if a != 0]
        assert (0xC072F080 in fixed) == (flavor == 'fast')
        artifacts = {}
        for p in sorted(folder.rglob('*')):
            if p.is_file():
                content = p.read_bytes()
                artifacts[str(p.relative_to(folder))] = {'bytes': len(content), 'sha256': sha(content)}
        result['builds'].append({
            'name': folder.name, 'edition': edition, 'flavor': flavor,
            'section_count': n, 'declared_body_bytes': body_size,
            'container_bytes': len(data), 'launcher_offset': launch_offset,
            'launcher_bytes': len(expected), 'header_entry': entry,
            'entry_order': entries, 'required_routines': list(required),
            'checks': {'sections_exact': True, 'launcher_exact': True,
                       'routine_offsets': True, 'entry_order': True,
                       'aligned_lengths_and_container_bounds': True,
                       'fast_abort_presence': True},
            'artifacts': artifacts})
print(json.dumps(result))
'''


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    names = [f'{p}-{e}-{f}' for p in ('before', 'after')
             for e in ('gcsv', 'base') for f in FLAVORS]
    if any((OUT / name).exists() for name in names):
        raise SystemExit('Refusing to overwrite existing audit build directories')
    OUT.mkdir(parents=True, exist_ok=True)
    report = {'version': VERSION, 'banner': BANNER, 'format_yield': False,
              'camera_or_card_access': False, 'commands': [], 'phases': [], 'pairs': []}
    log_path = HERE / 'build.log'
    report_path = HERE / 'build-report.json'
    with log_path.open('w') as log, tempfile.TemporaryDirectory(prefix='gcsv-direct-before-') as tmp:
        snap = Path(tmp)
        before = snap / 'gyro'
        before.mkdir()
        copied = {}
        for p in GYRO.iterdir():
            if p.is_file() and p.name != '.DS_Store':
                shutil.copy2(p, before / p.name)
                copied[p.name] = sha(p)
        (snap / 'fp_usb_shell').symlink_to(SHELL, target_is_directory=True)
        shutil.copy2(HERE / 'before' / 'gcsv_rows.S', before / 'gcsv_rows.S')
        copied['gcsv_rows.S'] = sha(before / 'gcsv_rows.S')
        report['before_source_sha256'] = copied

        def inspect(src, phase):
            run = subprocess.run([sys.executable, '-B', '-c', INSPECT,
                                  str(src), phase, str(OUT), str(HERE / 'before')],
                                 capture_output=True, text=True)
            log.write(run.stderr)
            log.flush()
            if run.returncode:
                log.write(run.stdout)
                raise RuntimeError(f'{phase} verification failed: {run.stderr}')
            return json.loads(run.stdout)

        # Reject a bad reconstruction before building any package.
        preflight = inspect(before, 'before')
        report['baseline_reconstruction'] = preflight['editions']
        for phase, source in (('before', before), ('after', GYRO)):
            for edition in ('gcsv', 'base'):
                for flavor, options in FLAVORS.items():
                    name = f'{phase}-{edition}-{flavor}'
                    cmd = [sys.executable, '-B', str(source / 'build_base_card.py'),
                           '--edition', edition, '--version', VERSION,
                           '--banner', BANNER, '--out', str(OUT / name), *options]
                    report['commands'].append(cmd)
                    run = subprocess.run(cmd, capture_output=True, text=True)
                    log.write('\n' + name + '\n' + run.stdout + run.stderr)
                    log.flush()
                    if run.returncode:
                        report['failure'] = {'build': name, 'returncode': run.returncode}
                        report_path.write_text(json.dumps(report, indent=2) + '\n')
                        raise RuntimeError(f'{name} failed; see {log_path}')
                    print(f'built {name}', flush=True)
            report['phases'].append(inspect(source, phase))

        for edition in ('gcsv', 'base'):
            for flavor in FLAVORS:
                left = OUT / f'before-{edition}-{flavor}'
                right = OUT / f'after-{edition}-{flavor}'
                same_autorun = (left / 'AutoRun.txt').read_bytes() == (right / 'AutoRun.txt').read_bytes()
                same_payload = (left / 'fpSup.BIN').read_bytes() == (right / 'fpSup.BIN').read_bytes()
                assert same_autorun, (edition, flavor, 'AutoRun unexpectedly changed')
                report['pairs'].append({'edition': edition, 'flavor': flavor,
                                        'autorun_identical': same_autorun,
                                        'payload_identical': same_payload,
                                        'autorun_sha256': sha(left / 'AutoRun.txt'),
                                        'before_payload_sha256': sha(left / 'fpSup.BIN'),
                                        'after_payload_sha256': sha(right / 'fpSup.BIN')})
        report['status'] = 'passed'
        report['limits'] = ['Static build and byte checks only; no camera execution.',
                            'Fast packages are local verification artifacts, not deployed.']
        report_path.write_text(json.dumps(report, indent=2) + '\n')
        log.write('\nAll 12 builds and six AutoRun comparisons passed.\n')
    print(report_path)


if __name__ == '__main__':
    main()
