#!/usr/bin/env python3
"""Four USB-shell cards that time their own AutoRun.

The question: how much of the boot does fast start actually save, and how much
does the progress readout cost?  Both have been argued from estimates --
283 ms per `display` was measured once, ~38 ms per `mem set` never was, and the
two cards that produced those seconds did not record where the measurement
started (AUTORUN_STORE_BOOT.md §9).

So the cards measure themselves.  Two samples of the camera's own clock go into
the cave, one as early in the script as a borrowed handler can be called and one
as the last command that runs; their difference is the script's duration and
owes nothing to a stopwatch or to when the camera's own boot began.

    ./build_boot_timing_cards.py --out DIR

writes four cards -- {fast, plain} x {bar, no bar} -- each a directory with
AutoRun.txt and fpSup.BIN.  Nothing but the USB shell is on them.

Then, per card: boot with USB unplugged, plug in, and

    cd fpSup/fp_usb_shell && ./fpsh mem get 0xC072F280,,0x40

The first word is the number of samples; the two after it are the samples.
A fast card needs TWO boots: the first seeds the settings block (and takes the
slow path, so its numbers are the slow path's), the second is the one to read.
"""
import argparse, os, pathlib, re, struct, subprocess, sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
SHELL = REPO / 'fpSup/fp_usb_shell'
STUB = HERE / 'boot_tstamp.S'

# Two stubs, because the one that runs last has to call the abort and the one
# that runs first must not.  Above the abort (0xC072F080 + 152 B) and clear of
# store_boot's scratch (0xC072F700) and the host's one-shot block.
T0_AT = 0xC072F200
T1_AT = 0xC072F240
SLOTS = 0xC072F280              # index, then the samples
ABORT_AT = 0xC072F080           # build_autorun's, where stage2 puts the abort
ECHO_SLOT = 0xC0BAC2F8
ECHO_ORIG = 0xC03D99A0
PAD_TO = 32768
FILLER = '# pad -- see PAD_TO: mode 7 overwrites but does not truncate\n'

# The last of build_autorun's three screen patches: the script's first three
# `mem set` lines, and the last point before the readout starts.
AFTER = 'mem set 0xC03E4698 0xE3A08010'


def assemble(tail):
    sys.path.insert(0, str(SHELL))
    import armasm
    blob = armasm.assemble(STUB, (f'SLOTS=0x{SLOTS:08X}', f'TAIL=0x{tail:08X}'))
    return [w for (w,) in struct.iter_unpack('<I', blob)]


def words_at(addr, words, why):
    out = [f'# --- {why} ---']
    out += [f'mem set 0x{addr + 4*i:08X} 0x{w:08X}' for i, w in enumerate(words)]
    return out


def call(addr, restore=True):
    """Borrow the echo handler, the way --boot-call does."""
    out = [f'mem set 0x{ECHO_SLOT:08X} 0x{addr:08X}', 'echo']
    if restore:
        # Three times: `mem set` drops commands, and a slot left pointing here
        # turns the next `echo` into a branch into whatever is there.
        out += [f'mem set 0x{ECHO_SLOT:08X} 0x{ECHO_ORIG:08X}'] * 3
    return out


def instrument(text, fast):
    """Put the two samples in.  Returns the new script, unpadded."""
    lines = text.splitlines()

    # The stubs and the zeroed slots go in before the first sample, so that
    # nothing between the two samples is instrumentation.
    pre = words_at(T0_AT, assemble(0), 'tstamp, first sample')
    pre += words_at(T1_AT, assemble(ABORT_AT if fast else 0),
                    'tstamp, last sample' + (' -> abort' if fast else ''))
    pre += ['# a warm restart does not clear RAM: start the index at zero',
            f'mem set 0x{SLOTS:08X} 0x00000000']
    pre += ['# --- T0 -------------------------------------------------------']
    pre += call(T0_AT)

    i = lines.index(AFTER)
    lines[i + 1:i + 1] = [''] + pre + ['']

    if fast:
        # The last command that runs on a seeded boot is the `echo` that hits
        # the abort stage2 armed into the slot.  Replace it: point the slot at
        # the stub, which samples and then calls the abort itself.
        echoes = [n for n, l in enumerate(lines) if l.strip() == 'echo']
        if len(echoes) < 2:
            sys.exit('expected at least two `echo` commands on a fast card')
        at = echoes[1]
        lines[at:at + 1] = (['# --- T1, then the abort stage2 armed ----------']
                            + call(T1_AT, restore=False))
    else:
        # A plain card runs to the end, so the last sample goes there.
        lines += ['', '# --- T1 ---------------------------------------------']
        lines += call(T1_AT)
    return '\n'.join(lines) + '\n'


def pad(text):
    if len(text) > PAD_TO:
        sys.exit(f'script is {len(text)} bytes, past {PAD_TO}')
    while len(text) + len(FILLER) <= PAD_TO:
        text += FILLER
    return text + '#' * (PAD_TO - len(text) - 1) + '\n'


def count(text):
    c = [l.strip() for l in text.splitlines()
         if l.strip() and not l.strip().startswith('#')]
    d = sum(1 for l in c if l.startswith('display'))
    m = sum(1 for l in c if l.startswith('mem set'))
    return len(c), d, m


def build(out, fast, nobar):
    name = ('fast' if fast else 'plain') + ('-nobar' if nobar else '-bar')
    d = out / ('card-' + name)
    d.mkdir(parents=True, exist_ok=True)
    banner = f'fpSup-T-{name}!'
    if len(banner) > 24:
        sys.exit(f'banner {banner!r} is too long for the readout')
    env = dict(os.environ)
    if nobar:
        env['FPSUP_NO_BAR'] = '1'
    cmd = [sys.executable, './build_autorun.py', '--loader', '--no-pad',
           '--banner', banner, '--out', str(d / 'AutoRun.txt')]
    if fast:
        cmd.append('--store-boot')
    r = subprocess.run(cmd, cwd=SHELL, env=env, capture_output=True, text=True)
    if r.returncode:
        sys.stderr.write(r.stdout + r.stderr)
        sys.exit(f'{name}: build_autorun failed')

    raw = (d / 'AutoRun.txt').read_text()
    before = count(raw)
    text = pad(instrument(raw, fast))
    (d / 'AutoRun.txt').write_text(text)
    after = count(text)
    print(f'{d.name:20s} banner {banner:22s} '
          f'{before[0]:3d} -> {after[0]:3d} cmds '
          f'(display {before[1]}->{after[1]}, mem set {before[2]}->{after[2]})')
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=pathlib.Path, required=True)
    a = ap.parse_args()
    for fast in (False, True):
        for nobar in (False, True):
            build(a.out, fast, nobar)
    print(f'\nthe BIN is the same on all four -- one copy is in each card dir')
    print(f'read the samples with:  ./fpsh mem get 0x{SLOTS:08X},,0x40')
    print('a fast card: boot twice, read after the second')


if __name__ == '__main__':
    main()
