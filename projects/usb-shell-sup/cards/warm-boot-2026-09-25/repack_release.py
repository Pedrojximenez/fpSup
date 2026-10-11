#!/usr/bin/env python3
"""Repack a released product's sections onto the current loader (test cards only).

    python3 repack_release.py RELEASE_DIR OUT_DIR -- [build_autorun.py args...]

Takes every section of RELEASE_DIR/fpSup.BIN except destination 0 (stage2, which
the loader owns) byte for byte -- the tested bytes, not a rebuild -- and hands
them to fpSup/fp_usb_shell/build_autorun.py --loader as --also-bin, with the
release's own entry as --vshl-entry.  Then checks every release section is in
the new card unchanged.
"""
import pathlib, struct, subprocess, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parents[4]
BA = ROOT / 'fpSup' / 'fp_usb_shell' / 'build_autorun.py'


def sections(raw):
    magic, n, entry, _ = struct.unpack_from('<4sIII', raw)
    assert magic == b'VBIN'
    off, out = 16 + 8 * n, []
    for i in range(n):
        d, l = struct.unpack_from('<II', raw, 16 + 8 * i)
        out.append((d, raw[off:off + l]))
        off += (l + 3) & ~3
    return entry, out


rel, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
extra = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
entry, secs = sections((rel / 'fpSup.BIN').read_bytes())
tmp = pathlib.Path(tempfile.mkdtemp())
cmd = [sys.executable, '-B', str(BA), '--loader', '--out', str(out / 'AutoRun.txt'), *extra]
if entry:
    cmd += ['--vshl-entry', f'0x{entry:08X}']
for i, (d, blob) in enumerate(secs):
    if d == 0:
        continue
    f = tmp / f'{i:03d}_{d:08X}.bin'
    f.write_bytes(blob)
    cmd += ['--also-bin', f'0x{d:08X}:{f}']
out.mkdir(parents=True, exist_ok=True)
subprocess.run(cmd, check=True)
_, got = sections((out / 'fpSup.BIN').read_bytes())
have = {}
for d, b in got:
    have.setdefault(d, []).append(b)
same = sum(1 for d, b in secs if d and b in have.get(d, []))
total = sum(1 for d, _ in secs if d)
print(f'release sections: {same} identical, {total - same} different/missing, of {total}')
if same != total:
    sys.exit('the card does not carry the release unchanged')
